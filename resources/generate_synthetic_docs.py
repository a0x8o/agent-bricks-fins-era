"""
Write the generated documents for organisations that publish no filing.

    python resources/generate_synthetic_docs.py --out data

Eight of the twenty-six organisations in the manifest cannot be downloaded from
anywhere: FordDirect and Addepar are private, UCLA Health, Providence and Summa
are nonprofits that file no securities reports, Henkel and Munich Re report in
Germany rather than to the SEC, and Nationwide suspended periodic reporting in
2010. Content comes from conf/synthetic_profiles.yaml.

THE WATERMARK IS THE POINT OF THIS FILE
---------------------------------------
This project's claim is that every sentence of an answer can be traced to the
evidence behind it. A generated document that reads like a real filing, attributed
to a real organisation, quietly breaks that claim - it would be indistinguishable
from evidence once it is a chunk in a vector index.

So the marker is applied in four places, and each one covers a different failure:

  filename        - visible in the citation itself, which is what a reader sees
  cover page      - visible to a human who opens the document
  running header  - lands in EVERY extracted page, so any chunk the retriever
                    returns carries the warning into the model's context even
                    when the cover page is nowhere near the retrieved passage
  corpus manifest - visible to anything reading the corpus programmatically

The running header is the one that actually matters at retrieval time. Do not
remove it to make the documents look tidier.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import pathlib
import sys

import yaml

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from era.ingest.companies import (  # noqa: E402
    SYNTHETIC_MARKER,
    Company,
    load_companies,
    synthetic,
    synthetic_marker,
)
from era.tools.redaction import CONF_DIR  # noqa: E402

logger = logging.getLogger("era.synthetic")

PROFILES_NAME = "synthetic_profiles.yaml"
FOLDER = "synthetic"

STYLESHEET = """
@page {
  size: letter;
  margin: 1.05in 0.95in 0.95in 0.95in;
  @top-center {
    content: "%(marker)s DOCUMENT - NOT A REAL FILING - %(company)s";
    font: 7.5pt "Helvetica", sans-serif;
    color: #b00020;
    letter-spacing: 0.04em;
  }
  @bottom-right {
    content: "Page " counter(page) " of " counter(pages);
    font: 8pt "Helvetica", sans-serif;
    color: #555;
  }
  @bottom-left {
    content: "%(marker)s - illustrative figures";
    font: 7.5pt "Helvetica", sans-serif;
    color: #b00020;
  }
}
body { font: 10.5pt/1.45 "Georgia", serif; color: #111; }
h1 { font: bold 20pt "Helvetica", sans-serif; margin: 0 0 2pt; }
h2 { font: bold 12.5pt "Helvetica", sans-serif; margin: 20pt 0 6pt;
     border-bottom: 1px solid #ccc; padding-bottom: 3pt; }
h3 { font: bold 10.5pt "Helvetica", sans-serif; margin: 12pt 0 3pt; }
.tagline { font: italic 11pt "Georgia", serif; color: #444; margin: 0 0 18pt; }
.warning { border: 2.5px solid #b00020; background: #fff5f6; color: #7a0016;
           padding: 12pt 14pt; margin: 14pt 0 20pt; font: 10pt "Helvetica", sans-serif; }
.warning strong { display: block; font-size: 12pt; margin-bottom: 5pt;
                  letter-spacing: 0.06em; }
table { width: 100%%; border-collapse: collapse; margin: 8pt 0 4pt; }
th, td { text-align: left; padding: 4.5pt 6pt; border-bottom: 1px solid #ddd;
         font: 10pt "Helvetica", sans-serif; }
th { background: #f4f4f4; font-weight: bold; }
td.value { text-align: right; font-variant-numeric: tabular-nums; }
.note { font: 9pt "Helvetica", sans-serif; color: #555; margin-top: 4pt; }
.provenance { border-top: 2px solid #b00020; margin-top: 26pt; padding-top: 10pt;
              font: 9pt "Helvetica", sans-serif; color: #444; }
"""


def _profiles(path: pathlib.Path | None = None) -> dict:
    doc = yaml.safe_load((path or CONF_DIR / PROFILES_NAME).read_text(encoding="utf-8")) or {}
    return doc


def _rows(mapping: dict, label: str) -> str:
    body = "".join(
        f"<tr><td>{html.escape(str(k))}</td>"
        f"<td class='value'>{html.escape(str(v))}</td></tr>"
        for k, v in (mapping or {}).items()
    )
    return f"<table><tr><th>{html.escape(label)}</th><th class='value'>Value</th></tr>{body}</table>"


def build_html(company: Company, profile: dict, fiscal_year: int) -> str:
    """Render one document. Every section is optional except the warnings."""
    e = html.escape
    banner = synthetic_marker(company)

    segments = "".join(
        f"<h3>{e(s['name'])}</h3><p>{e(s['description'].strip())}</p>"
        for s in profile.get("segments", [])
    )
    risks = "".join(
        f"<h3>{e(r['title'])}</h3><p>{e(r['text'].strip())}</p>"
        for r in profile.get("risk_factors", [])
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{SYNTHETIC_MARKER} - {e(company.name)} Annual Business Review {fiscal_year}</title>
<style>{STYLESHEET % {"marker": SYNTHETIC_MARKER, "company": e(company.name)}}</style>
</head><body>

<h1>{e(company.name)}</h1>
<p class="tagline">{e(profile.get('tagline', ''))} &mdash; Annual Business Review, fiscal year {fiscal_year}</p>

<div class="warning">
  <strong>{SYNTHETIC_MARKER} DOCUMENT &mdash; NOT A REAL FILING</strong>
  {e(banner)}
  <p style="margin:8pt 0 0">Business descriptions below reflect publicly known
  context about how this organisation operates. <strong>Every figure is
  invented</strong> and exists only so that this demo has something specific to
  retrieve and compare. Do not quote any number in this document as a fact about
  {e(company.name)}.</p>
</div>

<h2>1. Business Overview</h2>
<p>{e(profile.get('overview', '').strip())}</p>

<h2>2. Business Segments</h2>
{segments}

<h2>3. Risk Factors</h2>
{risks}

<h2>4. Financial Highlights <span style="font-weight:normal;font-size:9pt;color:#b00020">({SYNTHETIC_MARKER} &mdash; invented figures)</span></h2>
{_rows(profile.get('financials'), 'Measure')}
<p class="note">These figures are illustrative and were generated for this demo.
{e(company.name)} did not publish them.</p>

<h2>5. Operating Metrics <span style="font-weight:normal;font-size:9pt;color:#b00020">({SYNTHETIC_MARKER} &mdash; invented figures)</span></h2>
{_rows(profile.get('operating_metrics'), 'Measure')}
<p class="note">These figures are illustrative and were generated for this demo.</p>

<h2>6. Outlook</h2>
<p>{e(profile.get('outlook', '').strip())}</p>

<div class="provenance">
  <strong>Why this document exists.</strong>
  {e(company.real_source_note)}
  <p style="margin-top:7pt">Because no such document could be obtained, this one
  was generated for the Agent Bricks ERA demonstration corpus. It is marked
  {SYNTHETIC_MARKER} in its filename, on this page, in the header of every page,
  and in the corpus manifest.</p>
</div>

</body></html>"""


def generate_all(out_root: pathlib.Path, only: set[str] | None = None) -> list[dict]:
    doc = _profiles()
    fiscal_year = doc.get("fiscal_year", 2025)
    profiles = doc.get("profiles") or {}

    companies = [c for c in synthetic(load_companies()) if not only or c.slug in only]
    missing = [c.slug for c in companies if c.slug not in profiles]
    if missing:
        # Loud, because the alternative is an empty document that still looks like
        # a successful run and still gets indexed.
        raise SystemExit(
            f"No profile in {PROFILES_NAME} for: {', '.join(missing)}. "
            f"Add one, or change the company's source away from 'synthetic'."
        )

    folder = out_root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    import plutoprint

    for company in companies:
        name = f"{company.slug}_{SYNTHETIC_MARKER}_annual-review_{fiscal_year}.pdf"
        destination = folder / name
        markup = build_html(company, profiles[company.slug], fiscal_year)

        book = plutoprint.Book(plutoprint.PAGE_SIZE_LETTER)
        book.load_data(markup.encode("utf-8"), mime_type="text/html", base_url="")
        book.write_to_pdf(str(destination))
        logger.info("%s: %s (%.0f KB)", company.slug, name, destination.stat().st_size / 1e3)

        rows.append(
            {
                "slug": company.slug,
                "company": company.name,
                "sector": company.sector,
                "ticker": company.ticker,
                "cik": None,
                "form": "SYNTHETIC-ANNUAL-REVIEW",
                "report_date": f"{fiscal_year}-12-31",
                "filing_date": None,
                "accession": None,
                "source_url": None,
                "file": f"{FOLDER}/{name}",
                "synthetic": True,
                "real_source_note": company.real_source_note,
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            }
        )

    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="data", help="Corpus root (default: data)")
    p.add_argument("--only", default="", help="Comma-separated slugs")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out_root = pathlib.Path(args.out).resolve()
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    rows = generate_all(out_root, only=only)

    from fetch_filings import write_corpus_manifest

    path = write_corpus_manifest(rows, out_root)
    print(f"\n{len(rows)} generated documents. Manifest: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
