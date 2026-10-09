"""
The company universe, loaded from conf/companies.yaml.

Every part of the corpus pipeline reads its work list from here: which registrants
to download from EDGAR, which organisations need a synthetic document written,
which tickers to price, and which nodes and edges the graph gets. Keeping one list
is what stops the four from drifting apart - the previous setup derived its graph
from whatever happened to be in the ticker table, so anything without a listed
share price silently vanished from the graph.

WHY `synthetic` IS A FIRST-CLASS FIELD AND NOT A NAMING CONVENTION
-----------------------------------------------------------------
Eight of these organisations have no filing to download - they are private,
nonprofit, foreign-listed, or have suspended reporting. Their documents are
generated. Because this project's whole claim is that an answer can be traced back
to its evidence, a generated document that is indistinguishable from a real filing
would be worse than no document at all. So the distinction is carried in the data
model, and `synthetic_marker()` gives every downstream writer the same watermark
to stamp.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any

import yaml

from era.tools.redaction import CONF_DIR

MANIFEST_NAME = "companies.yaml"

# Stamped into the title, the running header and the filename of every generated
# document, and into the corpus manifest row. One constant so a reader who greps
# for it finds every place a synthetic document announces itself.
SYNTHETIC_MARKER = "SYNTHETIC"


@dataclasses.dataclass(frozen=True)
class Relationship:
    """A directed, factual edge - ownership, not inference."""

    type: str
    target: str


@dataclasses.dataclass(frozen=True)
class Company:
    slug: str
    name: str
    sector: str
    source: str
    aliases: tuple[str, ...] = ()
    industry: str = ""
    cik: int | None = None
    ticker: str | None = None
    sic: int | None = None
    forms: tuple[str, ...] = ("10-K",)
    relationships: tuple[Relationship, ...] = ()
    real_source_note: str = ""
    note: str = ""

    @property
    def is_synthetic(self) -> bool:
        return self.source == "synthetic"

    @property
    def is_filer(self) -> bool:
        return self.source == "edgar"

    @property
    def all_names(self) -> tuple[str, ...]:
        """Name plus aliases - what an entity matcher should look for."""
        return (self.name, *self.aliases)


class ManifestError(ValueError):
    """The manifest is wrong in a way that would produce a broken corpus."""


def manifest_path(path: str | pathlib.Path | None = None) -> pathlib.Path:
    return pathlib.Path(path) if path else CONF_DIR / MANIFEST_NAME


def _company(raw: dict[str, Any], defaults: dict[str, Any]) -> Company:
    rels = tuple(
        Relationship(type=r["type"], target=r["target"])
        for r in (raw.get("relationships") or [])
    )
    forms = raw.get("forms") or defaults.get("forms") or ["10-K"]
    return Company(
        slug=raw["slug"],
        name=raw["name"],
        sector=raw.get("sector", ""),
        source=raw.get("source", "edgar"),
        aliases=tuple(raw.get("aliases") or ()),
        industry=raw.get("industry", ""),
        cik=raw.get("cik"),
        ticker=raw.get("ticker"),
        sic=raw.get("sic"),
        forms=tuple(forms),
        relationships=rels,
        real_source_note=(raw.get("real_source_note") or "").strip(),
        note=(raw.get("note") or "").strip(),
    )


def load_companies(path: str | pathlib.Path | None = None) -> tuple[Company, ...]:
    """
    Read and validate the manifest.

    Validation is strict on purpose. Every failure it catches - a filer with no
    CIK, an edge pointing at a company that was renamed, a duplicated ticker -
    produces a corpus that builds successfully and is quietly wrong, which is the
    expensive kind of wrong to find later.
    """
    doc = yaml.safe_load(manifest_path(path).read_text(encoding="utf-8")) or {}
    defaults = doc.get("defaults") or {}
    raw_companies = doc.get("companies") or []
    if not raw_companies:
        raise ManifestError("manifest lists no companies")

    companies = tuple(_company(raw, defaults) for raw in raw_companies)
    _validate(companies)
    return companies


def _validate(companies: tuple[Company, ...]) -> None:
    slugs = [c.slug for c in companies]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise ManifestError(f"duplicate slugs: {sorted(dupes)}")

    known = set(slugs)
    for c in companies:
        if c.source not in ("edgar", "synthetic"):
            raise ManifestError(f"{c.slug}: unknown source {c.source!r}")
        if c.is_filer and not c.cik:
            raise ManifestError(f"{c.slug}: source is edgar but no cik is set")
        if c.is_synthetic and not c.real_source_note:
            raise ManifestError(
                f"{c.slug}: synthetic entries must record what real disclosure "
                f"exists, so the document can be replaced with a real one later"
            )
        for rel in c.relationships:
            if rel.target not in known:
                raise ManifestError(
                    f"{c.slug}: relationship {rel.type} points at unknown "
                    f"company {rel.target!r}"
                )

    tickers = [c.ticker for c in companies if c.ticker]
    dupe_tickers = {t for t in tickers if tickers.count(t) > 1}
    if dupe_tickers:
        raise ManifestError(f"duplicate tickers: {sorted(dupe_tickers)}")


# ---------------------------------------------------------------------------
# Work lists. Each answers one downstream question.
# ---------------------------------------------------------------------------


def filers(companies: tuple[Company, ...] | None = None) -> tuple[Company, ...]:
    """What the EDGAR fetcher downloads."""
    return tuple(c for c in (companies or load_companies()) if c.is_filer)


def synthetic(companies: tuple[Company, ...] | None = None) -> tuple[Company, ...]:
    """What the synthetic generator writes."""
    return tuple(c for c in (companies or load_companies()) if c.is_synthetic)


def tickers(companies: tuple[Company, ...] | None = None) -> tuple[str, ...]:
    """
    What the ticker loader prices.

    Not the same as the company list and not the same as the filer list: American
    Honda Finance files a 10-K with no ticker, while Henkel and Munich Re have
    ADR tickers but no SEC filing.
    """
    return tuple(c.ticker for c in (companies or load_companies()) if c.ticker)


def by_slug(companies: tuple[Company, ...] | None = None) -> dict[str, Company]:
    return {c.slug: c for c in (companies or load_companies())}


def sectors(companies: tuple[Company, ...] | None = None) -> dict[str, tuple[Company, ...]]:
    """Companies grouped by sector - the basis for peer edges in the graph."""
    grouped: dict[str, list[Company]] = {}
    for c in companies or load_companies():
        grouped.setdefault(c.sector, []).append(c)
    return {sector: tuple(members) for sector, members in grouped.items()}


def synthetic_marker(company: Company) -> str:
    """The one-line banner a generated document must carry."""
    return (
        f"{SYNTHETIC_MARKER} DOCUMENT - NOT A REAL FILING. Generated for the "
        f"Agent Bricks ERA demo. {company.name} publishes no such report; the "
        f"figures and statements below are illustrative and must not be used as "
        f"evidence about the real organisation."
    )
