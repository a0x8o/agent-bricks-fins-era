"""
Download real SEC filings for every `source: edgar` company in the manifest.

    python resources/fetch_filings.py --out data --user-agent "You you@example.com"

Runs locally or on Databricks. Output lands in `data/edgar_10k/` and
`data/edgar_10q/`, which `00_tables_setup` uploads to the volume alongside the
committed Mag7 corpus.

WHY THE FILINGS BECOME PDFs
---------------------------
EDGAR serves 10-Ks as HTML with inline XBRL. The rest of this corpus is PDF, the
Knowledge Assistant already indexes PDFs from this volume, and a mixed-format
corpus is one more thing to debug during a workshop. So each filing is rendered to
PDF on the way in. The text survives the round trip - a 3 MB Rockwell 10-K becomes
a 190-page PDF whose text extracts cleanly - and page numbers become real anchors
that citations can point at.

WHY THESE FILES ARE NOT IN GIT
------------------------------
They are large, they are reproducible by re-running this script, and they go stale
every quarter. The manifest is the artifact worth committing; the PDFs are cache.

SEC RULES THIS SCRIPT FOLLOWS
-----------------------------
EDGAR requires a User-Agent identifying you with a contact address, and asks for
no more than 10 requests a second. Both are honoured below - the rate limit
deliberately, because an IP that ignores it gets blocked, and a blocked IP breaks
the workshop for everyone sharing the network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from era.ingest.companies import Company, filers, load_companies  # noqa: E402

logger = logging.getLogger("era.fetch")

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"

# SEC permits 10 requests/second. Six leaves headroom for anyone else on the same
# network and still fetches the whole universe in well under a minute.
MIN_INTERVAL_S = 1 / 6

# Which manifest form maps to which corpus folder. Annual filings share a folder
# whether they are 10-K or 20-F, because to a reader asking "what does the latest
# annual report say" the distinction is a filing-status detail.
FOLDERS = {"10-K": "edgar_10k", "20-F": "edgar_10k", "10-Q": "edgar_10q"}


class Fetcher:
    """A rate-limited EDGAR client. One instance per run."""

    def __init__(self, user_agent: str):
        if "@" not in user_agent:
            raise ValueError(
                "SEC requires a User-Agent identifying you with a contact address, "
                'e.g. "Jane Smith jane@example.com". Pass --user-agent.'
            )
        self._ua = user_agent
        self._last = 0.0

    def _get(self, url: str) -> bytes:
        wait = MIN_INTERVAL_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        request = urllib.request.Request(url, headers={"User-Agent": self._ua})
        return urllib.request.urlopen(request, timeout=60).read()

    def latest_filings(self, company: Company, per_form: int) -> list[dict]:
        """
        The most recent `per_form` filings of each form the company files.

        Reads the submissions feed rather than guessing URLs, so a company that
        renames its primary document - as they all eventually do - still resolves.
        """
        data = json.loads(self._get(SUBMISSIONS.format(cik=company.cik)))
        recent = data["filings"]["recent"]
        wanted = {form: per_form for form in company.forms}
        out = []
        for form, date, accession, doc, report_date in zip(
            recent["form"],
            recent["filingDate"],
            recent["accessionNumber"],
            recent["primaryDocument"],
            recent["reportDate"],
        ):
            if wanted.get(form, 0) <= 0 or not doc:
                continue
            wanted[form] -= 1
            out.append(
                {
                    "form": form,
                    "filing_date": date,
                    "report_date": report_date or date,
                    "accession": accession,
                    "url": ARCHIVE.format(
                        cik=company.cik,
                        accession=accession.replace("-", ""),
                        doc=doc,
                    ),
                }
            )
            if all(v <= 0 for v in wanted.values()):
                break
        missing = [form for form, remaining in wanted.items() if remaining >= per_form]
        if missing:
            # Not fatal: Nationwide Life is the reminder that a registrant can stop
            # filing a form and still look perfectly healthy in the manifest.
            logger.warning(
                "%s (CIK %s): no %s found in the submissions feed",
                company.slug, company.cik, ", ".join(missing),
            )
        return out

    def document(self, url: str) -> bytes:
        return self._get(url)


def _render_pdf(html: bytes, source_url: str, destination: pathlib.Path) -> None:
    """
    Render filing HTML to PDF.

    The base URL is set to the filing's own directory so relative image and style
    references resolve against EDGAR instead of the local filesystem. Missing
    logos still warn and are skipped; that is cosmetic and does not affect text.
    """
    import plutoprint

    book = plutoprint.Book(plutoprint.PAGE_SIZE_LETTER)
    book.load_data(
        html,
        mime_type="text/html",
        base_url=source_url.rsplit("/", 1)[0] + "/",
    )
    book.write_to_pdf(str(destination))


def fetch_all(
    out_root: pathlib.Path,
    user_agent: str,
    per_form: int = 1,
    only: set[str] | None = None,
) -> list[dict]:
    fetcher = Fetcher(user_agent)
    companies = [c for c in filers(load_companies()) if not only or c.slug in only]
    manifest_rows: list[dict] = []

    for company in companies:
        try:
            filings = fetcher.latest_filings(company, per_form)
        except (urllib.error.URLError, KeyError) as exc:
            logger.error("%s: could not read submissions feed (%s)", company.slug, exc)
            continue

        for filing in filings:
            folder = out_root / FOLDERS.get(filing["form"], "edgar_other")
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{company.slug}_{filing['form']}_{filing['report_date']}.pdf"
            destination = folder / name

            if destination.exists():
                logger.info("%s: already have %s", company.slug, name)
            else:
                try:
                    html = fetcher.document(filing["url"])
                    _render_pdf(html, filing["url"], destination)
                except Exception as exc:  # noqa: BLE001 - one bad filing must not stop the run
                    logger.error("%s: %s failed (%s)", company.slug, name, exc)
                    continue
                logger.info(
                    "%s: %s (%.1f MB html -> %.1f MB pdf)",
                    company.slug, name, len(html) / 1e6,
                    destination.stat().st_size / 1e6,
                )

            manifest_rows.append(
                {
                    "slug": company.slug,
                    "company": company.name,
                    "sector": company.sector,
                    "ticker": company.ticker,
                    "cik": company.cik,
                    "form": filing["form"],
                    "report_date": filing["report_date"],
                    "filing_date": filing["filing_date"],
                    "accession": filing["accession"],
                    "source_url": filing["url"],
                    "file": f"{FOLDERS.get(filing['form'], 'edgar_other')}/{name}",
                    "synthetic": False,
                    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                }
            )

    return manifest_rows


def write_corpus_manifest(rows: list[dict], out_root: pathlib.Path) -> pathlib.Path:
    """
    Merge new rows into corpus_manifest.json.

    Merged rather than overwritten so a run limited to `--only` does not erase the
    record of everything else, and so the synthetic generator's rows survive.
    """
    path = out_root / "corpus_manifest.json"
    existing = {}
    if path.exists():
        existing = {r["file"]: r for r in json.loads(path.read_text(encoding="utf-8"))}
    existing.update({r["file"]: r for r in rows})
    merged = sorted(existing.values(), key=lambda r: r["file"])
    path.write_text(json.dumps(merged, indent=1) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="data", help="Corpus root (default: data)")
    p.add_argument("--user-agent", default="",
                   help='Required by SEC, e.g. "Jane Smith jane@example.com". '
                        "Falls back to $SEC_USER_AGENT.")
    p.add_argument("--per-form", type=int, default=1,
                   help="How many of each form to fetch per company (default: 1)")
    p.add_argument("--only", default="", help="Comma-separated slugs, for re-fetching one company")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    import os
    user_agent = args.user_agent or os.environ.get("SEC_USER_AGENT", "")
    if not user_agent:
        p.error('SEC requires a contact User-Agent. Pass --user-agent "Name email@example.com" '
                "or set SEC_USER_AGENT.")

    out_root = pathlib.Path(args.out).resolve()
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    rows = fetch_all(out_root, user_agent, per_form=args.per_form, only=only)
    path = write_corpus_manifest(rows, out_root)
    print(f"\n{len(rows)} filings in the corpus. Manifest: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
