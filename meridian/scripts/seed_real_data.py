"""Seed real-world public data into fins.meridian — no API keys needed.

Sources:
  * SEC EDGAR submissions API  -> fact_sec_filings (real filing index per symbol)
  * SEC EDGAR companyfacts     -> fact_sec_financials (real XBRL concepts per quarter)
  * You.com MCP free tier      -> fact_real_news (live headlines per symbol)

Only the 51 listed equities have SEC filings; ETFs / futures / FX / crypto are
skipped for EDGAR but still get You.com news.

Usage:
  python scripts/seed_real_data.py [--skip-news] [--skip-edgar]
"""

from __future__ import annotations

import argparse
import http.client
import json as _json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services import synthetic  # noqa: E402

CATALOG = "fins"
SCHEMA = "meridian"
T = f"`{CATALOG}`.`{SCHEMA}`"
WAREHOUSE = "00a19186c27fa1de"
UA = "Meridian research workspace alex.barreto@climb.ai"  # SEC requires a contact UA
EDGAR_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "8-K", "6-K", "DEF 14A", "4"}

# XBRL concepts we keep — the numbers a fundamentals surface actually needs
CONCEPTS = {
    "Revenues": "Total revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue (ASC 606)",
    "NetIncomeLoss": "Net income",
    "ProfitLoss": "Profit (loss)",
    "OperatingIncomeLoss": "Operating income",
    "EarningsPerShareDiluted": "Diluted EPS",
    "NetCashProvidedByUsedInOperatingActivities": "Operating cash flow",
    "PaymentsToAcquirePropertyPlantAndEquipment": "Capex (PP&E)",
    "StockholdersEquity": "Stockholders' equity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": "Total equity",
    "Assets": "Total assets",
    "Liabilities": "Total liabilities",
    "CashAndCashEquivalentsAtCarryingValue": "Cash & equivalents",
    "LongTermDebtNoncurrent": "Long-term debt",
    "CommonStockSharesOutstanding": "Shares outstanding",
}

DDL = {
    "fact_sec_filings": f"""CREATE TABLE IF NOT EXISTS {T}.fact_sec_filings (
        symbol STRING COMMENT 'Ticker — joins to dim_security.symbol',
        cik INT COMMENT 'SEC CIK of the filer',
        accession STRING COMMENT 'Accession number, unique per filing',
        form_type STRING COMMENT '10-K, 10-Q, 8-K, DEF 14A, 4, 20-F…',
        filing_date DATE COMMENT 'Date filed with the SEC',
        report_date DATE COMMENT 'Period covered by the report',
        primary_document STRING COMMENT 'Primary doc filename in the filing',
        document_url STRING COMMENT 'Direct URL to the primary document on sec.gov',
        description STRING COMMENT 'EDGAR document description',
        source STRING COMMENT 'Always SEC EDGAR',
        ingested_ts TIMESTAMP COMMENT 'When Meridian fetched this row'
    ) COMMENT 'Real SEC EDGAR filing index per symbol — authoritative source for filing existence, dates, and links'""",
    "fact_sec_financials": f"""CREATE TABLE IF NOT EXISTS {T}.fact_sec_financials (
        symbol STRING COMMENT 'Ticker — joins to dim_security.symbol',
        cik INT COMMENT 'SEC CIK of the filer',
        concept STRING COMMENT 'us-gaap XBRL concept name',
        label STRING COMMENT 'Human-readable metric name',
        unit STRING COMMENT 'USD | USD/shares | shares',
        fiscal_year INT COMMENT 'Fiscal year (fy) of the filed fact',
        fiscal_period STRING COMMENT 'Q1|Q2|Q3|Q4|FY per filer calendar',
        period_end DATE COMMENT 'End date of the reported period',
        filed DATE COMMENT 'Date the fact was filed',
        value DOUBLE COMMENT 'Reported value in `unit`',
        form STRING COMMENT 'Filing form the fact came from',
        source STRING COMMENT 'Always SEC EDGAR companyfacts (authoritative XBRL)'
    ) COMMENT 'Real XBRL fundamentals per symbol from SEC companyfacts — revenue, net income, EPS, OCF, capex, balance sheet. Authoritative for fundamentals questions; fact_fundamentals_quarterly is synthetic demo data.'""",
    "fact_real_news": f"""CREATE TABLE IF NOT EXISTS {T}.fact_real_news (
        symbol STRING COMMENT 'Ticker — joins to dim_security.symbol',
        headline STRING COMMENT 'Article headline',
        url STRING COMMENT 'Article URL',
        source STRING COMMENT 'Publisher domain',
        page_age STRING COMMENT 'Published timestamp as reported by search index',
        snippet STRING COMMENT 'Short article excerpt',
        fetched_ts TIMESTAMP COMMENT 'When Meridian fetched this row'
    ) COMMENT 'Live financial-news headlines per symbol fetched from You.com — real current news, unlike synthetic fact_news_events'""",
}

_equity_symbols = [s[0] for s in synthetic._SECURITIES if s[2] == "equity"]
_all_symbols = [s[0] for s in synthetic._SECURITIES]
_name_of = {s[0]: s[1] for s in synthetic._SECURITIES}

_get_calls = 0


def _cfg():
    from databricks.sdk.core import Config

    tok = _json.loads(subprocess.run(
        ["databricks", "auth", "token", "--profile", "DEFAULT"],
        capture_output=True, text=True, check=True).stdout)
    desc = subprocess.run(
        ["databricks", "auth", "describe", "--profile", "DEFAULT", "-o", "json"],
        capture_output=True, text=True, check=True)
    host = _json.loads(desc.stdout)["details"]["host"]
    return Config(host=host, token=tok["access_token"])


def _get_json(url: str) -> dict:
    global _get_calls
    _get_calls += 1
    time.sleep(0.17)  # stay under EDGAR's 10 req/s and You.com free-tier limits
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    return _json.loads(urllib.request.urlopen(req, timeout=30).read())


def _ticker_cik_map() -> dict[str, int]:
    data = _get_json("https://www.sec.gov/files/company_tickers.json")
    out = {}
    for row in data.values():
        out[row["ticker"].upper()] = int(row["cik_str"])
    return out


def _filing_rows(symbol: str, cik: int, sub: dict) -> list[tuple]:
    rows = []
    recent = sub.get("filings", {}).get("recent", {})
    n = len(recent.get("accessionNumber", []))
    kept = 0
    for i in range(n):
        form = recent["form"][i]
        if form not in EDGAR_FORMS or kept >= 60:
            continue
        kept += 1
        acc = recent["accessionNumber"][i]
        doc = recent["primaryDocument"][i] if i < len(recent.get("primaryDocument", [])) else ""
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}" if doc else ""
        rows.append((symbol, cik, acc, form,
                     recent["filingDate"][i] or None,
                     recent["reportDate"][i] if i < len(recent.get("reportDate", [])) else None,
                     doc, url,
                     (recent["primaryDocDescription"][i] if i < len(recent.get("primaryDocDescription", [])) else ""),
                     "SEC EDGAR"))
    return rows


def _fact_rows(symbol: str, cik: int, facts: dict) -> list[tuple]:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    rows = []
    seen = set()
    for concept, label in CONCEPTS.items():
        node = gaap.get(concept)
        if not node:
            continue
        items = []
        for unit, series in node.get("units", {}).items():
            for f in series:
                if f.get("form") in ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F"):
                    items.append((unit, f))
        # dedupe on (unit, fy, fp, end) preferring latest filed
        best = {}
        for unit, f in items:
            key = (unit, f.get("fy"), f.get("fp"), f.get("end"))
            if key not in best or (f.get("filed") or "") > (best[key][1].get("filed") or ""):
                best[key] = (unit, f)
        ranked = sorted(best.values(),
                        key=lambda uf: (uf[1].get("end") or "", uf[1].get("filed") or ""))[-16:]
        for unit, f in ranked:
            k = (concept, unit, f.get("fy"), f.get("fp"), f.get("end"))
            if k in seen:
                continue
            seen.add(k)
            rows.append((symbol, cik, concept, label, unit,
                         f.get("fy"), f.get("fp"), f.get("end"), f.get("filed"),
                         f.get("val"), f.get("form"), "SEC EDGAR companyfacts"))
    return rows


def _you_news(symbol: str, name: str) -> list[dict]:
    """You.com Search API (X-API-Key from YOU_API_KEY env); falls back to free MCP tier."""
    import os
    key = os.environ.get("YOU_API_KEY")
    if key:
        q = f"{name} ({symbol}) latest financial news"
        url = ("https://api.ydc-index.io/v1/search?query="
               + urllib.request.quote(q) + "&count=6&freshness=month")
        req = urllib.request.Request(url, headers={"X-API-Key": key})
        data = _json.loads(urllib.request.urlopen(req, timeout=30).read())
        res = data.get("results", {})
        news = res.get("news", []) or res.get("web", [])[:4]
        return news[:6]
    return _you_news_mcp(symbol, name)


def _you_news_mcp(symbol: str, name: str) -> list[dict]:
    """One You.com MCP free-tier you-search call; returns the news section."""
    conn = http.client.HTTPSConnection("api.you.com", timeout=45)
    path = "/mcp?profile=free"
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

    def call(body: dict, sid: str | None = None) -> tuple[dict, str | None]:
        h = dict(headers)
        if sid:
            h["Mcp-Session-Id"] = sid
        conn.request("POST", path, body=_json.dumps(body), headers=h)
        r = conn.getresponse()
        raw = r.read().decode("utf-8")
        ct = r.getheader("Content-Type") or ""
        sid2 = r.getheader("Mcp-Session-Id") or sid
        if "text/event-stream" in ct:
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    try:
                        return _json.loads(line[6:]), sid2
                    except _json.JSONDecodeError:
                        continue
            return {}, sid2
        return _json.loads(raw), sid2

    try:
        _, sid = call({"jsonrpc": "2.0", "method": "initialize",
                       "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "meridian-seed", "version": "1.0"}}, "id": 1})
        call({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, sid)
        msg, _ = call({"jsonrpc": "2.0", "method": "tools/call",
                       "params": {"name": "you-search",
                                  "arguments": {"query": f"{name} ({symbol}) latest financial news",
                                                "count": 6, "freshness": "month"}}, "id": 2}, sid)
        text = ""
        for part in msg.get("result", {}).get("content", []):
            if part.get("type") == "text":
                text = part["text"]
                break
        if not text:
            return []
        data = _json.loads(text)
        news = data.get("results", {}).get("news", [])
        if not news:
            news = data.get("results", {}).get("web", [])[:4]
        return news[:6]
    finally:
        conn.close()


def _domain(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else ""


def _sql(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, float):
        return repr(round(v, 6))
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''")[:2000] + "'"


def _insert(cur, table: str, cols: list[str], rows: list[tuple], ts_col: str | None = None) -> None:
    if not rows:
        print(f"  {table}: 0 rows, skipped")
        return
    cur.execute(f"DELETE FROM {T}.{table}")
    ts = f",{ts_col}" if ts_col else ""
    tail = ",current_timestamp()" if ts_col else ""
    values = ["(" + ",".join(_sql(v) for v in r) + tail + ")" for r in rows]
    for i in range(0, len(values), 300):
        cur.execute(f"INSERT INTO {T}.{table} ({','.join(cols)}{ts}) VALUES " + ",".join(values[i:i + 300]))
    print(f"  {table}: {len(rows)} rows")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-news", action="store_true")
    ap.add_argument("--skip-edgar", action="store_true")
    ap.add_argument("--news-file", help="Insert curated news JSON instead of calling You.com")
    args = ap.parse_args()

    from databricks import sql
    cfg = _cfg()
    conn = sql.connect(server_hostname=cfg.host.replace("https://", ""),
                       http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
                       credentials_provider=lambda: cfg.authenticate)
    cur = conn.cursor()
    cur.execute(f"USE CATALOG `{CATALOG}`")
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS `{SCHEMA}`")
    for ddl in DDL.values():
        cur.execute(ddl)

    if not args.skip_edgar:
        print("mapping tickers -> CIK…", flush=True)
        tmap = _ticker_cik_map()
        filings, facts, missing = [], [], []
        for i, sym in enumerate(_equity_symbols, 1):
            cik = tmap.get(sym)
            if not cik:
                missing.append(sym)
                continue
            sub = _get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
            filings += _filing_rows(sym, cik, sub)
            fc = _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
            facts += _fact_rows(sym, cik, fc)
            if i % 10 == 0:
                print(f"  edgar {i}/{len(_equity_symbols)} ({len(filings)} filings, {len(facts)} facts)", flush=True)
        if missing:
            print("no CIK for:", missing)
        _insert(cur, "fact_sec_filings",
                ["symbol", "cik", "accession", "form_type", "filing_date", "report_date",
                 "primary_document", "document_url", "description", "source"],
                filings, ts_col="ingested_ts")
        _insert(cur, "fact_sec_financials",
                ["symbol", "cik", "concept", "label", "unit", "fiscal_year", "fiscal_period",
                 "period_end", "filed", "value", "form", "source"],
                facts)

    if args.news_file:
        items = _json.loads(Path(args.news_file).read_text())
        news = [(r["symbol"], r["headline"], r["url"], r["source"], r["page_age"], r["snippet"]) for r in items]
        _insert(cur, "fact_real_news",
                ["symbol", "headline", "url", "source", "page_age", "snippet"],
                news, ts_col="fetched_ts")
    elif not args.skip_news:
        news = []
        for i, sym in enumerate(_all_symbols, 1):
            try:
                items = _you_news(sym, _name_of[sym])
            except Exception as e:  # one bad call shouldn't kill the run
                print(f"  news {sym}: {type(e).__name__} {e}", flush=True)
                items = []
            for it in items:
                news.append((sym, it.get("title", ""), it.get("url", ""),
                             _domain(it.get("url", "")), str(it.get("page_age", ""))[:40],
                             (it.get("description") or "")[:800]))
            print(f"  news {i}/{len(_all_symbols)} {sym}: {len(items)} items", flush=True)
            time.sleep(0.4)
        _insert(cur, "fact_real_news",
                ["symbol", "headline", "url", "source", "page_age", "snippet"],
                news, ts_col="fetched_ts")

    print("real-data seed complete ✓")


if __name__ == "__main__":
    main()
