"""
Tests for the company manifest.

The manifest is the single work list for four separate pipelines - EDGAR download,
synthetic generation, ticker loading, graph construction - so the failures worth
testing are the ones that produce a corpus which builds cleanly and is quietly
wrong: a filer with no CIK to fetch, an ownership edge pointing at a company that
was renamed, a synthetic entry that forgot to say it was synthetic.
"""

from __future__ import annotations

import pytest
import yaml

from era.ingest import companies as mod
from era.ingest.companies import (
    SYNTHETIC_MARKER,
    ManifestError,
    by_slug,
    filers,
    load_companies,
    sectors,
    synthetic,
    synthetic_marker,
    tickers,
)


def _write(tmp_path, doc: dict):
    path = tmp_path / "companies.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def _minimal(**overrides) -> dict:
    company = {
        "slug": "acme",
        "name": "Acme Corp",
        "sector": "Industrials",
        "source": "edgar",
        "cik": 1234,
        "ticker": "ACME",
    }
    company.update(overrides)
    return {"companies": [company]}


# ---------------------------------------------------------------------------
# The shipped manifest
# ---------------------------------------------------------------------------

def test_the_shipped_manifest_loads():
    assert len(load_companies()) >= 25


def test_every_requested_organisation_is_covered():
    """
    The demo was specified by name. If someone edits the manifest and drops one of
    these, the corpus silently stops covering it and nothing else complains.
    """
    names = " | ".join(n.lower() for c in load_companies() for n in c.all_names)
    for requested in (
        "ford motor", "ford direct", "honda financial", "addepar", "pfizer",
        "merck", "ucla health", "dow", "hinge health", "providence",
        "united airlines", "southwest", "deere", "toyota", "henkel",
        "summa", "amgen", "regeneron", "s&p global", "nationwide",
        "slide insurance", "ryan specialty", "munich re", "rockwell", "hunt",
    ):
        assert requested in names, f"{requested!r} is not covered by the manifest"


def test_filers_all_have_a_cik_to_fetch_with():
    assert all(c.cik for c in filers())


def test_synthetic_entries_explain_what_real_disclosure_exists():
    """
    Without this note there is no path back to a real document, and the generated
    one silently becomes the permanent answer.
    """
    for company in synthetic():
        assert len(company.real_source_note) > 40, company.slug


def test_the_two_ownership_edges_resolve():
    """FordDirect and American Honda Finance are the only asserted relationships."""
    index = by_slug()
    edges = {
        (c.slug, rel.type, rel.target)
        for c in load_companies() for rel in c.relationships
    }
    assert ("ford_direct", "joint_venture_of", "ford") in edges
    assert ("honda_financial", "subsidiary_of", "honda_motor") in edges
    for _, _, target in edges:
        assert target in index


def test_tickers_are_not_the_same_list_as_companies():
    """
    The distinction the graph notebook exists to respect: some companies file but
    are not listed, and some are listed but do not file.
    """
    all_companies = load_companies()
    priced = set(tickers(all_companies))
    assert len(priced) < len(all_companies)

    honda = by_slug(all_companies)["honda_financial"]
    assert honda.is_filer and honda.ticker is None, "a filer with no listed equity"

    henkel = by_slug(all_companies)["henkel"]
    assert henkel.is_synthetic and henkel.ticker, "listed abroad, no SEC filing"


def test_sectors_span_more_than_technology():
    """The point of the expansion: the corpus is no longer seven tech companies."""
    assert len(sectors()) >= 10


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_a_filer_without_a_cik_is_rejected(tmp_path):
    path = _write(tmp_path, _minimal(cik=None))
    with pytest.raises(ManifestError, match="no cik"):
        load_companies(path)


def test_a_synthetic_entry_without_a_source_note_is_rejected(tmp_path):
    path = _write(tmp_path, _minimal(source="synthetic", cik=None))
    with pytest.raises(ManifestError, match="real disclosure"):
        load_companies(path)


def test_a_dangling_relationship_is_rejected(tmp_path):
    """A renamed slug must fail loudly rather than drop the edge."""
    path = _write(tmp_path, _minimal(
        relationships=[{"type": "subsidiary_of", "target": "does_not_exist"}]
    ))
    with pytest.raises(ManifestError, match="unknown company"):
        load_companies(path)


def test_duplicate_slugs_are_rejected(tmp_path):
    doc = _minimal()
    doc["companies"].append(dict(doc["companies"][0]))
    with pytest.raises(ManifestError, match="duplicate slugs"):
        load_companies(_write(tmp_path, doc))


def test_duplicate_tickers_are_rejected(tmp_path):
    """Two companies on one ticker would double-count in the price table."""
    doc = _minimal()
    doc["companies"].append({**doc["companies"][0], "slug": "acme2", "name": "Acme Two"})
    with pytest.raises(ManifestError, match="duplicate tickers"):
        load_companies(_write(tmp_path, doc))


def test_an_unknown_source_is_rejected(tmp_path):
    path = _write(tmp_path, _minimal(source="scraped"))
    with pytest.raises(ManifestError, match="unknown source"):
        load_companies(path)


def test_defaults_supply_forms_but_a_company_can_override(tmp_path):
    doc = _minimal()
    doc["defaults"] = {"forms": ["10-K", "10-Q"]}
    doc["companies"].append({
        "slug": "foreign", "name": "Foreign SA", "sector": "Industrials",
        "source": "edgar", "cik": 99, "forms": ["20-F"],
    })
    loaded = by_slug(load_companies(_write(tmp_path, doc)))
    assert loaded["acme"].forms == ("10-K", "10-Q")
    assert loaded["foreign"].forms == ("20-F",)


def test_toyota_and_honda_are_marked_as_20f_filers():
    """They file 20-F; asking EDGAR for a 10-K would return nothing."""
    index = by_slug()
    assert index["toyota"].forms == ("20-F",)
    assert index["honda_motor"].forms == ("20-F",)


# ---------------------------------------------------------------------------
# The watermark
# ---------------------------------------------------------------------------

def test_the_marker_names_the_organisation_and_disclaims_the_figures():
    banner = synthetic_marker(by_slug()["providence"])
    assert SYNTHETIC_MARKER in banner
    assert "Providence" in banner
    assert "NOT A REAL FILING" in banner


def test_conf_dir_resolution_is_shared_with_the_gate():
    """
    The manifest has to be findable both in a checkout and inside a packaged
    model, which is a problem redaction.py already solved.
    """
    assert mod.manifest_path().name == mod.MANIFEST_NAME
    assert mod.manifest_path().exists()
