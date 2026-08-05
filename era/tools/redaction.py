"""
The egress gate. Every outbound You.com call passes through here.

Three responsibilities, deliberately kept in one module so there is exactly one
place to audit:

    scrub(text)       remove credential- and PII-shaped material, and any literal
                      term listed in conf/sensitive_terms.yaml
    policy_check(...) decide whether this call may leave at all, given the endpoint's
                      data-retention coverage and the sensitivity of the query
    audit(record)     record that the decision happened, without recording the text

DESIGN RULE: THE AUDIT TRAIL NEVER CONTAINS THE QUERY
-----------------------------------------------------
An audit table that stores the outbound text recreates, inside the lakehouse, the
exact exposure the gate exists to prevent - and it does so in a table that is by
design widely readable and long-lived. So the record carries SHA-256 hashes of the
original and scrubbed query plus counts by redaction kind. That is enough to prove
what happened, to correlate a complaint with a call, and to detect a spike in
redactions; it is not enough to reconstruct the question.

The same rule applies to logs. Nothing in this module logs raw query text, and
`ScrubResult` deliberately does not retain the matched values.

WHY THIS IS PYTHON AND NOT SQL
------------------------------
Milestone B pushes domain policy into the UC function, which is the right place for
it. But a SQL UDF cannot maintain a redaction dictionary, cannot refuse a call based
on data-retention posture, and cannot write an audit row - it has no side effects
available. That is the gap this module closes, and it is why the code-first agent
exists at all.
"""

from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Protocol

import yaml

logger = logging.getLogger("era.gate")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CONF_DIR = REPO_ROOT / "conf"

REDACTION_PLACEHOLDER = "[REDACTED:{kind}]"


class Sensitivity(str, Enum):
    """Ordered. Comparison is by rank, not string value."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"

    @property
    def rank(self) -> int:
        return {"public": 0, "internal": 1, "confidential": 2}[self.value]

    def __ge__(self, other: "Sensitivity") -> bool:  # type: ignore[override]
        return self.rank >= other.rank

    def __gt__(self, other: "Sensitivity") -> bool:  # type: ignore[override]
        return self.rank > other.rank


# ---------------------------------------------------------------------------
# Detectors
#
# Ordering matters: the more specific patterns run first so that, for example, a
# Databricks PAT is labelled as such rather than being swallowed by the generic
# long-token rule.
#
# Each entry is (kind, pattern, implied_sensitivity, escalates).
#
# THE `escalates` FLAG IS THE IMPORTANT PART
# ------------------------------------------
# There are two genuinely different reasons to redact, and conflating them makes
# the gate useless in opposite directions.
#
#   escalates=False - the match is a stray identifier. Removing it neutralises it,
#                     and the remaining question is ordinary. "outlook for
#                     [REDACTED:email] holdings" is still a perfectly good search.
#                     Escalating here would refuse the call *after* successfully
#                     cleaning it, which makes redaction pointless and teaches
#                     people to route around the gate.
#
#   escalates=True  - the match tells us the SUBJECT is sensitive, not just that a
#                     stray token appeared. A live credential in a research question
#                     means something is wrong upstream. A configured codename means
#                     the fact of asking is itself the disclosure - and the scrubbed
#                     remainder ("how is [REDACTED:term] viewed") is a useless query
#                     anyway. Refuse and audit; do not send a hollowed-out request.
# ---------------------------------------------------------------------------

_DETECTORS: tuple[tuple[str, re.Pattern[str], Sensitivity, bool], ...] = (
    # Credentials. Presence signals a problem beyond the token itself.
    ("databricks_pat", re.compile(r"\bdapi[0-9a-f]{32,}\b", re.I), Sensitivity.CONFIDENTIAL, True),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), Sensitivity.CONFIDENTIAL, True),
    ("private_key", re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----"), Sensitivity.CONFIDENTIAL, True),
    ("bearer_token", re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._\-]{16,}"), Sensitivity.CONFIDENTIAL, True),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"), Sensitivity.CONFIDENTIAL, True),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), Sensitivity.CONFIDENTIAL, True),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"), Sensitivity.CONFIDENTIAL, True),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), Sensitivity.CONFIDENTIAL, True),

    # Regulated identifiers. Redaction removes them, but their presence in an
    # outbound research question is itself the signal worth stopping on.
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), Sensitivity.CONFIDENTIAL, True),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), Sensitivity.CONFIDENTIAL, True),
    # Card numbers: 13-19 digits with optional separators. Luhn-checked below to
    # avoid redacting every long number (order ids, CUSIPs, timestamps).
    ("card_number", re.compile(r"\b(?:\d[ \-]?){13,19}\b"), Sensitivity.CONFIDENTIAL, True),

    # Contact details. Genuinely neutralised by removal.
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), Sensitivity.INTERNAL, False),
    ("phone", re.compile(r"(?<!\d)(?:\+\d{1,3}[ .\-]?)?(?:\(\d{3}\)|\d{3})[ .\-]\d{3}[ .\-]\d{4}(?!\d)"), Sensitivity.INTERNAL, False),

    # Internal topology. Maps the estate for anyone watching, but stripping the
    # name leaves a usable question behind.
    ("internal_host", re.compile(r"\b[\w.\-]+\.(?:internal|corp|local|intranet)\b", re.I), Sensitivity.INTERNAL, False),
    ("uc_three_part_name", re.compile(r"\b[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]{3,}\b(?!\.)", re.I), Sensitivity.INTERNAL, False),
)


def _luhn_ok(digits: str) -> bool:
    """Standard Luhn check, used to keep the card detector from firing on any long number."""
    total, alt = 0, False
    for ch in reversed(digits):
        if not ch.isdigit():
            return False
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


@dataclass(frozen=True)
class Redaction:
    """What was removed - never the value that was removed."""

    kind: str
    count: int


@dataclass
class ScrubResult:
    text: str
    redactions: tuple[Redaction, ...] = ()
    implied_sensitivity: Sensitivity = Sensitivity.PUBLIC

    @property
    def total_redactions(self) -> int:
        return sum(r.count for r in self.redactions)

    @property
    def clean(self) -> bool:
        return self.total_redactions == 0


def _load_sensitive_terms() -> list[str]:
    path = CONF_DIR / "sensitive_terms.yaml"
    if not path.exists():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    terms: list[str] = []
    for key, value in doc.items():
        if key == "version" or not isinstance(value, list):
            continue
        terms.extend(t for t in value if isinstance(t, str) and t.strip())
    # Longest first so "Project Northstar" wins over a bare "Northstar" entry.
    return sorted(set(terms), key=len, reverse=True)


def scrub(text: str, extra_terms: Iterable[str] | None = None) -> ScrubResult:
    """
    Remove credential- and PII-shaped material and any configured sensitive term.

    Returns the cleaned text plus counts by kind. The matched values are discarded
    immediately and never stored on the result - holding them would just relocate
    the exposure into whatever logs or traces the result flows through.
    """
    if not text:
        return ScrubResult(text="")

    counts: dict[str, int] = {}
    worst = Sensitivity.PUBLIC
    out = text

    # Configured literal terms first: they are the most specific knowledge we have.
    terms = list(_load_sensitive_terms())
    if extra_terms:
        terms = sorted(set(terms) | {t for t in extra_terms if t}, key=len, reverse=True)
    for term in terms:
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.I)
        out, n = pattern.subn(REDACTION_PLACEHOLDER.format(kind="term"), out)
        if n:
            counts["term"] = counts.get("term", 0) + n
            worst = max(worst, Sensitivity.CONFIDENTIAL, key=lambda s: s.rank)

    for kind, pattern, implied, escalates in _DETECTORS:
        def _replace(match: re.Match[str], _kind: str = kind) -> str:
            value = match.group(0)
            if _kind == "card_number":
                digits = re.sub(r"[ \-]", "", value)
                # Not a card number: leave it alone rather than mangling real data.
                if len(digits) < 13 or not _luhn_ok(digits):
                    return value
            if _kind == "uc_three_part_name" and not _looks_like_uc_name(value):
                return value
            counts[_kind] = counts.get(_kind, 0) + 1
            return REDACTION_PLACEHOLDER.format(kind=_kind)

        before = counts.get(kind, 0)
        out = pattern.sub(_replace, out)
        # Only escalating detectors raise the sensitivity the ZDR rule sees. A
        # redacted email has been dealt with; a redacted credential has not.
        if counts.get(kind, 0) > before and escalates:
            worst = max(worst, implied, key=lambda s: s.rank)

    redactions = tuple(Redaction(kind=k, count=v) for k, v in sorted(counts.items()))
    return ScrubResult(text=out, redactions=redactions, implied_sensitivity=worst)


_COMMON_DOTTED_FALSE_POSITIVES = {"www", "com", "org", "net", "io", "co", "gov", "edu"}


def _looks_like_uc_name(value: str) -> bool:
    """
    Distinguish `catalog.schema.table` from `finance.yahoo.com` and `v1.2.3`.

    WHY: the three-part-name detector is the one most likely to fire on ordinary
    text. Being wrong here mangles legitimate queries, which trains people to
    disable the gate - a worse outcome than the leak it prevents.
    """
    parts = value.split(".")
    if len(parts) != 3:
        return False
    if any(p.lower() in _COMMON_DOTTED_FALSE_POSITIVES for p in parts):
        return False
    if any(p.isdigit() for p in parts):
        return False
    # Real catalog/schema/table names are short identifiers. A long opaque segment
    # means this is some other dotted token (a malformed JWT, a hash) that an
    # earlier, more specific detector did not claim. It still gets redacted by
    # whichever rule matches - but mislabelling it here would put a misleading
    # kind in the audit trail, and the audit trail is the thing we reason from.
    if any(len(p) > 40 for p in parts):
        return False
    return True


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EndpointPolicy:
    name: str
    zdr_covered: bool
    tier: str


@dataclass
class GateDecision:
    allowed: bool
    reason: str
    endpoint: str
    scrubbed_query: str = ""
    redactions: tuple[Redaction, ...] = ()
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    domain_mode: str = "deny"
    domains: tuple[str, ...] = ()
    zdr_covered: bool = False

    def __bool__(self) -> bool:
        return self.allowed


class PolicyError(RuntimeError):
    """Raised when the gate refuses a call. Carries no query text."""


def _load(name: str) -> dict:
    return yaml.safe_load((CONF_DIR / name).read_text(encoding="utf-8")) or {}


def _flatten_domains(name: str) -> tuple[str, ...]:
    doc = _load(name)
    return tuple(
        item
        for key, value in doc.items()
        if key != "version" and isinstance(value, list)
        for item in value
        if isinstance(item, str)
    )


def policy_check(
    endpoint: str,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    domain_mode: str | None = None,
) -> GateDecision:
    """
    Decide whether a call to `endpoint` may leave, before any text is considered.

    The ZDR rule is the substantive one. You.com's zero-data-retention term covers
    /v1/search only; Research, Finance Research and Contents are not covered. Sending
    a confidential question to a non-covered endpoint is a retention decision made by
    accident, so the gate makes it explicitly and refuses by default.
    """
    policy = _load("routing_policy.yaml")
    endpoints = policy.get("endpoints", {})
    if endpoint not in endpoints:
        return GateDecision(
            allowed=False,
            reason=f"unknown endpoint '{endpoint}' - not declared in routing_policy.yaml",
            endpoint=endpoint,
            sensitivity=sensitivity,
        )

    spec = endpoints[endpoint]
    zdr_covered = bool(spec.get("zdr_covered"))
    zdr_cfg = policy.get("zero_data_retention", {})
    account_enabled = bool(zdr_cfg.get("account_enabled"))
    threshold = Sensitivity(zdr_cfg.get("refuse_non_zdr_above_sensitivity", "internal"))

    # An endpoint is only genuinely covered if the ACCOUNT has ZDR and the endpoint
    # is in scope. account_enabled defaults to false until You.com confirms in
    # writing, so the safe path is the default path.
    effective_zdr = zdr_covered and account_enabled

    if not effective_zdr and sensitivity.rank >= threshold.rank:
        why = (
            "account ZDR not confirmed" if zdr_covered and not account_enabled
            else f"endpoint '{endpoint}' is outside You.com's ZDR scope"
        )
        return GateDecision(
            allowed=False,
            reason=(
                f"refusing {sensitivity.value} query to a non-ZDR endpoint ({why}). "
                f"Raise conf/routing_policy.yaml:zero_data_retention once the "
                f"agreement covers it, or lower the query's sensitivity."
            ),
            endpoint=endpoint,
            sensitivity=sensitivity,
            zdr_covered=effective_zdr,
        )

    mode = domain_mode or policy.get("domain_mode", {}).get("default", "deny")
    if mode not in ("allow", "deny"):
        return GateDecision(
            allowed=False,
            reason=f"invalid domain_mode '{mode}' - must be allow or deny",
            endpoint=endpoint,
            sensitivity=sensitivity,
        )

    domains = _flatten_domains(
        "domain_allowlist.yaml" if mode == "allow" else "domain_denylist.yaml"
    )

    return GateDecision(
        allowed=True,
        reason="ok",
        endpoint=endpoint,
        sensitivity=sensitivity,
        domain_mode=mode,
        domains=domains,
        zdr_covered=effective_zdr,
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class AuditRecord:
    """
    One outbound decision. Contains no query text by construction - there is no
    field it could go in.
    """

    ts: str
    endpoint: str
    allowed: bool
    reason: str
    query_sha256: str
    scrubbed_sha256: str
    redaction_counts: dict[str, int]
    sensitivity: str
    domain_mode: str
    zdr_covered: bool
    principal: str
    cost_usd: float | None = None
    latency_ms: int | None = None
    request_id: str | None = None

    def as_row(self) -> dict:
        return {
            "ts": self.ts,
            "endpoint": self.endpoint,
            "allowed": self.allowed,
            "reason": self.reason,
            "query_sha256": self.query_sha256,
            "scrubbed_sha256": self.scrubbed_sha256,
            "redaction_counts": self.redaction_counts,
            "sensitivity": self.sensitivity,
            "domain_mode": self.domain_mode,
            "zdr_covered": self.zdr_covered,
            "principal": self.principal,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
        }


class AuditSink(Protocol):
    def write(self, record: AuditRecord) -> None: ...


@dataclass
class InMemoryAuditSink:
    """Default sink. Also what the tests assert against."""

    records: list[AuditRecord] = field(default_factory=list)

    def write(self, record: AuditRecord) -> None:
        self.records.append(record)


class DeltaAuditSink:
    """
    Append to CATALOG.SCHEMA.egress_audit.

    Requires an active Spark session, so it is only usable inside Databricks. It is
    not the default: an audit sink that raises on import would make the gate
    untestable, and a gate that is hard to test is a gate that gets bypassed.
    """

    def __init__(self, catalog: str, schema: str, table: str = "egress_audit", spark=None):
        self.full_name = f"{catalog}.{schema}.{table}"
        self._spark = spark

    def _session(self):
        if self._spark is None:
            from pyspark.sql import SparkSession  # imported lazily - not available locally

            self._spark = SparkSession.builder.getOrCreate()
        return self._spark

    def write(self, record: AuditRecord) -> None:
        spark = self._session()
        df = spark.createDataFrame([record.as_row()])
        df.write.mode("append").saveAsTable(self.full_name)


_default_sink: AuditSink = InMemoryAuditSink()


def set_audit_sink(sink: AuditSink) -> None:
    global _default_sink
    _default_sink = sink


def get_audit_sink() -> AuditSink:
    return _default_sink


def audit(
    decision: GateDecision,
    original_query: str,
    *,
    principal: str | None = None,
    cost_usd: float | None = None,
    latency_ms: int | None = None,
    request_id: str | None = None,
    sink: AuditSink | None = None,
) -> AuditRecord:
    """Record the decision. Hashes only."""
    record = AuditRecord(
        ts=datetime.now(timezone.utc).isoformat(),
        endpoint=decision.endpoint,
        allowed=decision.allowed,
        reason=decision.reason,
        query_sha256=_sha256(original_query),
        scrubbed_sha256=_sha256(decision.scrubbed_query),
        redaction_counts={r.kind: r.count for r in decision.redactions},
        sensitivity=decision.sensitivity.value,
        domain_mode=decision.domain_mode,
        zdr_covered=decision.zdr_covered,
        principal=principal or os.environ.get("DATABRICKS_CLIENT_ID", "unknown"),
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        request_id=request_id,
    )
    (sink or _default_sink).write(record)
    return record


# ---------------------------------------------------------------------------
# The single entry point
# ---------------------------------------------------------------------------


def gate(
    query: str,
    endpoint: str,
    *,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    domain_mode: str | None = None,
    extra_terms: Iterable[str] | None = None,
    principal: str | None = None,
    request_id: str | None = None,
    sink: AuditSink | None = None,
) -> GateDecision:
    """
    Scrub, decide, audit. Returns the decision; callers must check `.allowed`.

    Use `require()` instead if you want a refusal to raise rather than be checked -
    that is the safer default for tool code, because an ignored return value here
    means an ungoverned call.

    Note the ordering: scrubbing runs FIRST, and its findings can escalate the
    query's sensitivity. A question the caller labelled `public` that turns out to
    contain a Databricks token is not a public question, and the ZDR rule must see
    the escalated value rather than the claimed one.
    """
    scrubbed = scrub(query, extra_terms=extra_terms)
    effective = max(sensitivity, scrubbed.implied_sensitivity, key=lambda s: s.rank)

    decision = policy_check(endpoint, sensitivity=effective, domain_mode=domain_mode)
    decision.scrubbed_query = scrubbed.text
    decision.redactions = scrubbed.redactions
    decision.sensitivity = effective

    audit(decision, query, principal=principal, request_id=request_id, sink=sink)

    if not decision.allowed:
        logger.warning("egress refused for endpoint=%s: %s", endpoint, decision.reason)
    elif not scrubbed.clean:
        logger.info(
            "egress allowed for endpoint=%s with %d redaction(s): %s",
            endpoint, scrubbed.total_redactions,
            {r.kind: r.count for r in scrubbed.redactions},
        )
    return decision


def require(query: str, endpoint: str, **kwargs) -> GateDecision:
    """gate(), but a refusal raises PolicyError instead of returning falsy."""
    decision = gate(query, endpoint, **kwargs)
    if not decision.allowed:
        raise PolicyError(decision.reason)
    return decision
