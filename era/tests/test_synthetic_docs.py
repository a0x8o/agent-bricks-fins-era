"""
Tests for the generated reference documents.

Only one property here really matters: a generated document must be impossible to
mistake for a real filing, at the point where the mistake would actually be made.
That point is not the cover page - it is the retrieved chunk. A vector index
returns a passage from page 3, and if the warning lives only on page 1 the model
sees invented figures with nothing attached to say so.

So the test that counts is `test_the_marker_reaches_every_page`. The rest guard
the inputs to it.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest
import yaml

from era.ingest.companies import SYNTHETIC_MARKER, by_slug, synthetic
from era.tools.redaction import CONF_DIR

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_generator():
    path = REPO_ROOT / "resources" / "generate_synthetic_docs.py"
    spec = importlib.util.spec_from_file_location("generate_synthetic_docs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()
PROFILES = yaml.safe_load(
    (CONF_DIR / "synthetic_profiles.yaml").read_text(encoding="utf-8")
)["profiles"]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def test_every_synthetic_company_has_content_to_write():
    """
    A missing profile used to be an empty document that still got indexed. The
    generator now refuses, and this keeps the shipped manifest honest.
    """
    missing = [c.slug for c in synthetic() if c.slug not in PROFILES]
    assert not missing, f"no profile for: {missing}"


def test_profiles_describe_organisations_the_manifest_knows():
    known = set(by_slug())
    assert not (set(PROFILES) - known), "profile for a company not in the manifest"


def test_each_profile_has_something_worth_retrieving():
    """Empty sections make a document that indexes but cannot answer anything."""
    for slug, profile in PROFILES.items():
        assert len(profile.get("overview", "")) > 200, slug
        assert len(profile.get("segments", [])) >= 2, slug
        assert len(profile.get("risk_factors", [])) >= 3, slug
        assert profile.get("financials"), slug


# ---------------------------------------------------------------------------
# The watermark
# ---------------------------------------------------------------------------

def test_the_markup_carries_the_warning_in_all_the_required_places():
    company = by_slug()["addepar"]
    markup = gen.build_html(company, PROFILES["addepar"], 2025)

    assert f"<title>{SYNTHETIC_MARKER}" in markup, "title"
    assert "NOT A REAL FILING" in markup, "cover banner"
    assert "@top-center" in markup and SYNTHETIC_MARKER in markup, "running header"
    assert company.real_source_note[:40] in markup, "what real disclosure exists"


def test_the_filename_announces_itself():
    """The filename is what appears in a citation, so it has to carry the marker."""
    company = by_slug()["providence"]
    name = f"{company.slug}_{SYNTHETIC_MARKER}_annual-review_2025.pdf"
    assert SYNTHETIC_MARKER in name


def test_manifest_rows_record_the_distinction(tmp_path):
    rows = gen.generate_all(tmp_path, only={"addepar"})
    assert len(rows) == 1
    row = rows[0]
    assert row["synthetic"] is True
    assert row["source_url"] is None, "there is no source to point at"
    assert row["cik"] is None
    assert row["real_source_note"]
    assert SYNTHETIC_MARKER in row["file"]


def test_the_marker_reaches_every_page(tmp_path):
    """
    The property the whole approach rests on. A retriever returns a passage, not a
    document; if a page can be extracted without the warning, then a chunk of
    invented financials can reach the model with nothing marking it.
    """
    pypdf = pytest.importorskip("pypdf")

    gen.generate_all(tmp_path, only={"providence", "munich_re"})
    written = sorted((tmp_path / gen.FOLDER).glob("*.pdf"))
    assert len(written) == 2

    for path in written:
        pages = [(p.extract_text() or "") for p in pypdf.PdfReader(str(path)).pages]
        assert pages, f"{path.name} has no pages"
        unmarked = [i + 1 for i, text in enumerate(pages)
                    if SYNTHETIC_MARKER not in text]
        assert not unmarked, (
            f"{path.name}: pages {unmarked} extract without the {SYNTHETIC_MARKER} "
            f"marker - a chunk from one of them would look like a real filing"
        )


def test_a_company_without_a_profile_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "_profiles", lambda path=None: {"fiscal_year": 2025, "profiles": {}})
    with pytest.raises(SystemExit, match="No profile"):
        gen.generate_all(tmp_path)
