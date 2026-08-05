<!--
GRAFTED FILE - MODIFIED FROM ORIGINAL
Source repo   : alexxx-db/agent-bricks-fins-legal
Source path   : docs/PDF_SOURCES_AND_STAGING.md
Source commit : cf640d0 (2026-03-23)
Grafted into  : agent-bricks-fins-era on 2026-08-03
Modifications : provenance header added; see this repo's git history for
                all subsequent changes.
License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
                root of this repository. Provided AS-IS.
-->

# PDF Sources and Staging for RAG

This document lists **publicly available** sources for financial documents used in the Agent Bricks RAG workflow, their **licensing**, the **staging layout**, and the **recommended demo set**.

---

## 1. Primary source: SEC EDGAR

**What it is**: The SEC’s Electronic Data Gathering, Analysis, and Retrieval system. All 10-K, 10-Q, and 8-K (and many exhibits) are filed here.

**URLs**
- Company search: https://www.sec.gov/cgi-bin/browse-edgar
- Company tickers (JSON): https://www.sec.gov/files/company_tickers.json
- Submissions API (per company): `https://data.sec.gov/submissions/CIK{cik}.json` (CIK zero-padded to 10 digits)
- Filing document: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no}/{primary_doc}`

**Licensing**: Public domain. SEC content is not subject to copyright in the United States. See [SEC Privacy and Security Policy](https://www.sec.gov/privacy).

**Rate limits / rules**
- You **must** send a `User-Agent` header with a string that identifies your application and contact (e.g. `MyApp admin@example.com`). See [SEC EDGAR Developer Resources](https://www.sec.gov/developer).
- Do not exceed 10 requests per second; the SEC may block IPs that do.

**Document types we use**
| Type | Description |
|------|-------------|
| 10-K | Annual report |
| 10-Q | Quarterly report |
| 8-K | Current report (often includes earnings releases as exhibits) |

**Format**: Most 10-K/10-Q filings are **HTML** (`.htm`). The ingestion pipeline treats HTML as text source for chunking; it can also convert to PDF if required downstream.

---

## 2. Staging layout

All downloaded or ingested files follow this layout so the pipeline and Vector Search use a consistent structure.

**Staging (local or DBFS before ingestion)**  
Used by the download script and as input to the Lakeflow pipeline:

```
staging_root/
├── 10k/
│   └── {ticker}_10k_{period_end}.htm   # e.g. AAPL_10k_2023-09-30.htm
├── 10q/
│   └── {ticker}_10q_{period_end}.htm   # e.g. AAPL_10q_2024-03-30.htm
├── 8k/
│   └── {ticker}_8k_{filed_date}_{description}.htm
└── manifest.json                       # optional: path, source_url, ticker, document_type, period_end
```

**Target UC Volume (after ingestion)**  
Same structure under the Unity Catalog volume used by the Knowledge Assistant and Vector Search:

```
/Volumes/{catalog}/{schema}/{volume}/
├── 10k/
├── 10q/
├── 8k/
└── (optional) manifest table or manifest.json
```

Default volume: `main.mfg_agent_bricks_demo.finance_unstructured_data` (i.e. `/Volumes/main/mfg_agent_bricks_demo/finance_unstructured_data/`).

---

## 3. Recommended demo set

Use at least **2–3 companies** and **2–3 periods** so the demo shows variety and multi-company comparison.

| Ticker | Company        | CIK     | Suggested filings |
|--------|----------------|--------|--------------------|
| AAPL   | Apple Inc.     | 320193 | Latest 10-K, latest 10-Q |
| MSFT   | Microsoft Corp.| 789019 | Latest 10-K, latest 10-Q |
| NVDA   | NVIDIA Corp.   | 1045810| Latest 10-K, latest 10-Q |

**Minimum for demo**
- At least **2 companies**.
- For each: **1× 10-K**, **1× 10-Q**, and **1× 8-K** (latest available per form).

This gives enough content for RAG questions on revenue, risk, liquidity, and guidance.

---

## 4. How to run the download script

The script `data/scripts/download_sec_filings.py` downloads 10-K, 10-Q, and 8-K from SEC EDGAR into the staging layout.

**Prerequisites**
- Python 3.10+
- `requests` (and optionally `python-dotenv` if you use a `.env` for User-Agent).

**Setup**
```bash
cd data/scripts
pip install requests
```

**Required**
- Set a **User-Agent** that identifies your app and contact. SEC may block requests without it.

  Option A – environment variable:
  ```bash
  export SEC_EDGAR_USER_AGENT="MyCompany RAG Demo admin@mycompany.com"
  ```
  Option B – pass on the command line (see script `--user-agent`).

**Run**
```bash
# Default: AAPL, MSFT; latest 10-K and 10-Q each; writes to ./staging by default
python download_sec_filings.py --output-dir ./staging

# Specific tickers and max filings per type
python download_sec_filings.py --tickers AAPL MSFT NVDA --max-per-type 2 --output-dir ./staging

# Custom User-Agent
python download_sec_filings.py --user-agent "MyApp contact@example.com" --output-dir ./staging
```

**Output**
- Files under `{output-dir}/10k/`, `{output_dir}/10q/`, and `{output_dir}/8k/` with naming `{ticker}_{form}_{period}.htm` (e.g. `AAPL_10k_2023-09-30.htm`, `AAPL_8k_20240315.htm`).
- Optional `manifest.json` in `output_dir` listing path, source_url, ticker, document_type, period_end (if implemented in script).

---

## 5. Optional: other public PDF sources

For **PDF-only** sources (e.g. annual report booklets):

- **Company IR pages**: Many firms publish PDF annual reports at URLs like `https://investors.{company}.com/financials/`. You must respect each site’s terms of use and robots.txt.
- **Aggregators**: Some datasets (e.g. on Hugging Face or academic) bundle SEC or annual report PDFs; use only with clear **attribution and license** and document the source in this file if you add them.

The **Lakeflow ingestion pipeline** reads from the staging layout above (SEC HTML) and can also copy or process PDFs placed in the same folder structure (e.g. `10k/{ticker}_10k_{period}.pdf`) if you add them manually or via another script.

---

## 6. Changelog

| Date       | Change |
|------------|--------|
| (initial)  | SEC EDGAR as primary source; staging layout; demo set (AAPL, MSFT, NVDA); download script usage. |
