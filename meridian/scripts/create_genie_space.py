#!/usr/bin/env python3
"""Create/update the Meridian Genie space on fins.meridian.* via the Genie API.

    DATABRICKS_CONFIG_PROFILE=DEFAULT python scripts/create_genie_space.py

Prints the space id — set it as GENIE_SPACE_ID (app.yaml valueFrom: genie-space,
databricks.yml var.genie_space_id).
"""

from __future__ import annotations

import json
import os
import sys

import httpx
from databricks.sdk.core import Config


def _cfg():
    """Resolve auth via the CLI profile (avoids dual-profile token ambiguity)."""
    import json as _json
    import subprocess
    
    profile = os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
    out = subprocess.run(
        ["databricks", "auth", "token", "--profile", profile],
        capture_output=True, text=True, check=True,
    )
    tok = _json.loads(out.stdout)
    desc = subprocess.run(
        ["databricks", "auth", "describe", "--profile", profile, "-o", "json"],
        capture_output=True, text=True, check=True,
    )
    host = _json.loads(desc.stdout)["details"]["host"]
    return Config(host=host, token=tok["access_token"])


CATALOG = os.getenv("UC_CATALOG", "fins")
SCHEMA = os.getenv("UC_SCHEMA", "meridian")
WAREHOUSE = os.getenv("DATABRICKS_WAREHOUSE_ID", "00a19186c27fa1de")
TITLE = "Meridian Financial Analyst"
TABLES = [
    "dim_security", "fact_price_daily", "fact_fundamentals_quarterly",
    "fact_portfolio_positions", "fact_news_events",
    "fact_sec_filings", "fact_sec_financials", "fact_real_news",
    "v_returns", "v_valuation", "v_portfolio_performance",
]

INSTRUCTIONS = """You are Meridian's financial analysis assistant.
Conventions:
- "Latest" always means max(trade_date) — never extrapolate beyond available data.
- Returns are computed on adj_close (dividend-adjusted), not close.
- Fiscal periods are calendar quarters ending period_end.
- Currency is USD for all synthetic symbols.
- Prefer the certified views v_returns (return windows), v_valuation (multiples),
  and v_portfolio_performance (weights/P&L) over recomputing from facts.
- Benchmarks: SPY (broad market), QQQ (Nasdaq-100 proxy).
- Portfolio questions refer to portfolio_id 'demo-core' unless stated otherwise.
- Price/return/portfolio tables and v_* views are SYNTHETIC demo data.
- REAL public data lives in fact_sec_filings (SEC EDGAR filing index),
  fact_sec_financials (real XBRL fundamentals from SEC companyfacts — authoritative
  for fundamentals questions), and fact_real_news (live headlines from You.com).
- For filings, real fundamentals, or current-news questions prefer the fact_sec_*
  and fact_real_news tables over the synthetic fact_* tables, and cite document_url
  or url so the answer links the source.
- fact_sec_financials.value is in `unit` (USD | USD/shares | shares); filter by
  label or concept and fiscal_period (Q1-Q4/FY); newest is max(period_end).
"""

EXAMPLES = [
    ("What was NVDA's 1-year return?", "SELECT ret_1y FROM fins.meridian.v_returns WHERE symbol = 'NVDA'"),
    ("Top 10 stocks by 1M return", "SELECT r.symbol, d.name, r.ret_1m FROM fins.meridian.v_returns r JOIN fins.meridian.dim_security d USING (symbol) ORDER BY r.ret_1m DESC LIMIT 10"),
    ("Compare AAPL and MSFT YTD return", "SELECT symbol, ret_ytd FROM fins.meridian.v_returns WHERE symbol IN ('AAPL','MSFT')"),
    ("Which sectors drove the portfolio?", "SELECT d.sector, sum(p.market_value) AS value, sum(p.market_value - p.cost_basis) AS pnl FROM fins.meridian.fact_portfolio_positions p JOIN fins.meridian.dim_security d USING (symbol) GROUP BY d.sector ORDER BY pnl DESC"),
    ("Show AAPL quarterly revenue for 3 years", "SELECT period_end, revenue FROM fins.meridian.fact_fundamentals_quarterly WHERE symbol = 'AAPL' ORDER BY period_end DESC LIMIT 12"),
    ("Semiconductor names by FCF yield", "SELECT v.symbol, v.fcf_yield_pct FROM fins.meridian.v_valuation v JOIN fins.meridian.dim_security d USING (symbol) WHERE d.industry = 'Semiconductors' ORDER BY v.fcf_yield_pct DESC"),
    ("Daily closes for TSLA last month", "SELECT trade_date, close FROM fins.meridian.fact_price_daily WHERE symbol = 'TSLA' AND trade_date >= date_sub((SELECT max(trade_date) FROM fins.meridian.fact_price_daily WHERE symbol='TSLA'), 31) ORDER BY trade_date"),
    ("Portfolio weights", "SELECT symbol, weight_pct FROM fins.meridian.v_portfolio_performance WHERE portfolio_id = 'demo-core' ORDER BY weight_pct DESC"),
    ("Largest healthcare positions by market cap", "SELECT symbol, name, market_cap FROM fins.meridian.dim_security WHERE sector = 'Healthcare' ORDER BY market_cap DESC LIMIT 10"),
    ("Did NVDA beat SPY over 6 months?", "SELECT symbol, ret_6m FROM fins.meridian.v_returns WHERE symbol IN ('NVDA','SPY')"),
    ("When did AAPL last file a 10-Q and where is it?", "SELECT form_type, filing_date, report_date, document_url FROM fins.meridian.fact_sec_filings WHERE symbol = 'AAPL' AND form_type = '10-Q' ORDER BY filing_date DESC LIMIT 3"),
    ("NVDA real revenue last 4 quarters (SEC filings)", "SELECT fiscal_period, period_end, value / 1e9 AS revenue_billions_usd FROM fins.meridian.fact_sec_financials WHERE symbol = 'NVDA' AND label = 'Total revenue' AND fiscal_period LIKE 'Q%' ORDER BY period_end DESC LIMIT 4"),
    ("What's the latest real news on LLY?", "SELECT headline, source, page_age, url FROM fins.meridian.fact_real_news WHERE symbol = 'LLY' ORDER BY fetched_ts DESC LIMIT 5"),
]


def main() -> None:
    cfg = _cfg()
    host = cfg.host.rstrip("/")
    headers = cfg.authenticate()
    headers["Content-Type"] = "application/json"

    import uuid
    hexids = sorted(uuid.uuid5(uuid.NAMESPACE_URL, f"meridian-genie-{i}").hex for i in range(len(EXAMPLES) + 10))
    serialized = {
        "version": 1,
        "config": {"sample_questions": [{"id": hexids[i], "question": [q]} for i, (q, _) in enumerate(EXAMPLES[:10])]},
        "data_sources": {
            "tables": [
                {"identifier": f"{CATALOG}.{SCHEMA}.{t}"} for t in sorted(TABLES)
            ]
        },
        "instructions": {
            "text_instructions": [{"id": uuid.uuid5(uuid.NAMESPACE_URL, "meridian-genie-ti").hex, "content": [INSTRUCTIONS]}],
            "example_question_sqls": [
                {"id": hexids[10 + i], "question": [q], "sql": [s]} for i, (q, s) in enumerate(EXAMPLES)
            ],
        },
    }
    payload = {
        "warehouse_id": WAREHOUSE,
        "serialized_space": json.dumps(serialized),
        "title": TITLE,
        "description": "Natural-language analytics over Meridian's synthetic market data (fins.meridian).",
    }

    # update if a space with this title exists
    with httpx.Client(timeout=30, headers=headers) as c:
        r = c.get(f"{host}/api/2.0/genie/spaces", params={"page_size": 100})
        existing = next((s for s in r.json().get("spaces", []) if s.get("title") == TITLE), None)
        if existing:
            sid = existing["space_id"]
            resp = c.patch(f"{host}/api/2.0/genie/spaces/{sid}", json=payload)
            print(f"updated {sid}: {resp.status_code} {resp.text[:400] if resp.status_code >= 400 else ''}")
        else:
            resp = c.post(f"{host}/api/2.0/genie/spaces", json=payload)
            resp.raise_for_status()
            sid = resp.json().get("space_id") or resp.json().get("space", {}).get("space_id")
            print(f"created {sid}")
    print(sid)


if __name__ == "__main__":
    main()
