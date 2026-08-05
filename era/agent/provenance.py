"""
Claim tagging and citation validation.

The accelerator's core promise is that a blended answer never hides which parts came
from governed internal data and which came from the open web. This module is where
that promise is checked rather than hoped for.

THE CONTRACT
------------
The synthesis prompt (see prompts.py) requires every material claim to carry exactly
one tag:

    [IV:<lineage>]   internal-verified - came from KA or Genie, lineage identifies
                     the table or document it came from
    [EC:<n>]         external-cited    - came from the web, n indexes the Sources list
    [INF]            inferred          - the model's own reasoning over the above,
                     asserted by no source
    [OPS]            operational       - a statement about the system rather than the
                     subject ("that request was blocked by policy"). Asserts nothing
                     about the world, so it needs no evidence

followed by a Sources section:

    ## Sources
    [1] Title - https://example.com/page (retrieved 2026-08-04T09:15:00Z)

WHY VALIDATE INSTEAD OF TRUSTING THE TAGS
-----------------------------------------
A model asked to cite will cite. It will also, under pressure, invent a plausible
citation, reuse a number that points at the wrong source, or tag its own inference as
verified. Every one of those produces output that looks *more* trustworthy than an
honest untagged answer, which is precisely what makes it dangerous. So each tag is
resolved back to evidence the tools actually returned:

    [EC:n] must point at a source whose URL a web tool really returned
    [IV:x] must name lineage an internal tool really produced
    [INF]  is always structurally valid - it claims no support, which is the point
    [OPS]  likewise: it describes the system, not the subject matter

An answer that fails validation is a failing answer, not a warning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Tag(str, Enum):
    INTERNAL_VERIFIED = "internal-verified"
    EXTERNAL_CITED = "external-cited"
    INFERRED = "inferred"
    # ERA ADDITION beyond the three specified labels.
    #
    # WHY it had to exist: "That request was blocked by policy" is a sentence about
    # the system, not a claim about the world. With only three tags it is
    # unrepresentable - it is not internal, not external, and calling it inference
    # would be a lie about where it came from. Left untagged it counts as an
    # unlabelled material claim, so an agent that correctly refused a sensitive
    # question scored *worse* on provenance than one that answered it, and the
    # release gate blocked the deploy for doing the right thing.
    #
    # A control that punishes correct behaviour gets weakened until it stops
    # objecting. So operational statements get their own tag: they assert nothing
    # about the subject, need no evidence, and are always structurally valid.
    OPERATIONAL = "operational"


class ViolationKind(str, Enum):
    UNTAGGED_CLAIM = "untagged_claim"
    DANGLING_CITATION = "dangling_citation"
    FABRICATED_SOURCE = "fabricated_source"
    UNKNOWN_LINEAGE = "unknown_lineage"
    UNUSED_SOURCE = "unused_source"
    MALFORMED_SOURCE = "malformed_source"


@dataclass(frozen=True)
class Source:
    index: int
    title: str
    url: str
    retrieved_at: str | None = None


@dataclass(frozen=True)
class Claim:
    text: str
    tag: Tag | None
    reference: str | None = None   # lineage for IV, source index for EC
    line: int = 0


@dataclass(frozen=True)
class Violation:
    kind: ViolationKind
    detail: str
    claim: str | None = None

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.kind.value}: {self.detail}"


@dataclass
class Evidence:
    """What the tools actually returned this turn. The ground truth for validation."""

    internal_lineage: set[str] = field(default_factory=set)
    external_urls: set[str] = field(default_factory=set)

    def add_internal(self, lineage: str) -> None:
        if lineage:
            self.internal_lineage.add(lineage.strip())

    def add_external(self, url: str) -> None:
        if url:
            self.external_urls.add(_normalise_url(url))


@dataclass
class ParsedAnswer:
    claims: tuple[Claim, ...]
    sources: tuple[Source, ...]
    prose: str


@dataclass
class ProvenanceReport:
    ok: bool
    citation_coverage: float
    violations: tuple[Violation, ...]
    counts: dict[str, int]

    @property
    def summary(self) -> str:
        parts = [f"{k}={v}" for k, v in sorted(self.counts.items())]
        return (
            f"{'PASS' if self.ok else 'FAIL'} "
            f"coverage={self.citation_coverage:.0%} "
            f"{' '.join(parts)} "
            f"violations={len(self.violations)}"
        )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"\[(IV:(?P<lineage>[^\]]+)|EC:(?P<idx>\d+)|INF|OPS)\]")
_SOURCE_RE = re.compile(
    r"^\s*\[(?P<idx>\d+)\]\s*(?P<title>.*?)\s*[-–]\s*(?P<url>https?://\S+)"
    r"(?:\s*\(retrieved\s+(?P<ts>[^)]+)\))?\s*$"
)
_SOURCES_HEADING_RE = re.compile(r"^\s*#{0,6}\s*sources\s*:?\s*$", re.I)

# A line is a material claim if it asserts something. Headings, bullets that only
# introduce a list, and questions are not claims.
_TRIVIAL_RE = re.compile(r"^\s*(#{1,6}\s|[-*]\s*$|\|)")


def _normalise_url(url: str) -> str:
    """Trailing slashes and fragments are not identity. Everything else is."""
    url = url.strip().rstrip(".,;)")
    url = url.split("#", 1)[0]
    return url[:-1] if url.endswith("/") else url


def _is_material(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _TRIVIAL_RE.match(line):
        return False
    if _SOURCES_HEADING_RE.match(line) or _SOURCE_RE.match(line):
        return False
    if stripped.endswith("?"):
        return False
    # Require some substance - a three word fragment is a transition, not a claim.
    words = re.findall(r"[A-Za-z][A-Za-z'\-]+", stripped)
    return len(words) >= 4


def parse_answer(text: str) -> ParsedAnswer:
    """Split an answer into tagged claims and its Sources list."""
    claims: list[Claim] = []
    sources: list[Source] = []
    prose_lines: list[str] = []

    in_sources = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _SOURCES_HEADING_RE.match(raw):
            in_sources = True
            continue

        if in_sources:
            match = _SOURCE_RE.match(raw)
            if match:
                sources.append(
                    Source(
                        index=int(match.group("idx")),
                        title=match.group("title").strip(),
                        url=_normalise_url(match.group("url")),
                        retrieved_at=(match.group("ts") or "").strip() or None,
                    )
                )
            elif raw.strip():
                # A non-empty line in the Sources block that does not parse is a
                # malformed citation, surfaced later as a violation.
                sources.append(Source(index=-1, title=raw.strip(), url=""))
            continue

        prose_lines.append(raw)
        if not _is_material(raw):
            continue

        found = list(_TAG_RE.finditer(raw))
        cleaned = _TAG_RE.sub("", raw).strip()
        if not found:
            claims.append(Claim(text=cleaned, tag=None, line=lineno))
            continue

        for match in found:
            token = match.group(0)
            if token == "[INF]":
                claims.append(Claim(text=cleaned, tag=Tag.INFERRED, line=lineno))
            elif token == "[OPS]":
                claims.append(Claim(text=cleaned, tag=Tag.OPERATIONAL, line=lineno))
            elif match.group("lineage") is not None:
                claims.append(
                    Claim(
                        text=cleaned,
                        tag=Tag.INTERNAL_VERIFIED,
                        reference=match.group("lineage").strip(),
                        line=lineno,
                    )
                )
            else:
                claims.append(
                    Claim(
                        text=cleaned,
                        tag=Tag.EXTERNAL_CITED,
                        reference=match.group("idx"),
                        line=lineno,
                    )
                )

    return ParsedAnswer(
        claims=tuple(claims), sources=tuple(sources), prose="\n".join(prose_lines).strip()
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(parsed: ParsedAnswer, evidence: Evidence, *, require_full_coverage: bool = True) -> ProvenanceReport:
    """
    Resolve every tag back to evidence the tools actually produced.

    `require_full_coverage` exists for the critique node, which may want the report
    on a draft without failing it outright. The release gate uses the default.
    """
    violations: list[Violation] = []
    by_index = {s.index: s for s in parsed.sources if s.index >= 0}

    for source in parsed.sources:
        if source.index < 0 or not source.url:
            violations.append(
                Violation(
                    ViolationKind.MALFORMED_SOURCE,
                    f"unparseable Sources entry: {source.title[:80]!r}",
                )
            )

    counts = {t.value: 0 for t in Tag}
    counts["untagged"] = 0

    for claim in parsed.claims:
        if claim.tag is None:
            counts["untagged"] += 1
            violations.append(
                Violation(
                    ViolationKind.UNTAGGED_CLAIM,
                    f"line {claim.line}: material claim carries no provenance tag",
                    claim.text[:160],
                )
            )
            continue

        counts[claim.tag.value] += 1

        if claim.tag is Tag.EXTERNAL_CITED:
            idx = int(claim.reference) if claim.reference and claim.reference.isdigit() else -1
            source = by_index.get(idx)
            if source is None:
                violations.append(
                    Violation(
                        ViolationKind.DANGLING_CITATION,
                        f"line {claim.line}: [EC:{claim.reference}] has no matching Sources entry",
                        claim.text[:160],
                    )
                )
            elif source.url not in evidence.external_urls:
                # The citation points somewhere no tool ever went. This is the
                # fabrication case and it is the reason this module exists.
                violations.append(
                    Violation(
                        ViolationKind.FABRICATED_SOURCE,
                        f"line {claim.line}: cites {source.url} which no web tool returned",
                        claim.text[:160],
                    )
                )

        elif claim.tag is Tag.INTERNAL_VERIFIED:
            lineage = (claim.reference or "").strip()
            if lineage not in evidence.internal_lineage:
                violations.append(
                    Violation(
                        ViolationKind.UNKNOWN_LINEAGE,
                        f"line {claim.line}: claims lineage {lineage!r} which no internal tool produced",
                        claim.text[:160],
                    )
                )

    cited_indexes = {
        int(c.reference)
        for c in parsed.claims
        if c.tag is Tag.EXTERNAL_CITED and c.reference and c.reference.isdigit()
    }
    for source in parsed.sources:
        if source.index >= 0 and source.index not in cited_indexes:
            # Not fatal, but a listed-yet-uncited source pads the appearance of
            # sourcing without supporting anything.
            violations.append(
                Violation(
                    ViolationKind.UNUSED_SOURCE,
                    f"source [{source.index}] is listed but never cited",
                )
            )

    material = len(parsed.claims)
    tagged = material - counts["untagged"]
    coverage = 1.0 if material == 0 else tagged / material

    fatal = [v for v in violations if v.kind is not ViolationKind.UNUSED_SOURCE]
    ok = not fatal if require_full_coverage else not [
        v for v in fatal if v.kind is not ViolationKind.UNTAGGED_CLAIM
    ]

    return ProvenanceReport(
        ok=ok, citation_coverage=coverage, violations=tuple(violations), counts=counts
    )


def check(answer: str, evidence: Evidence, **kwargs) -> ProvenanceReport:
    """parse + validate in one call."""
    return validate(parse_answer(answer), evidence, **kwargs)
