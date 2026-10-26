#!/usr/bin/env python3
"""Seed fins.meridian.* with synthetic data + certified views.

Run locally against the workspace:
    DATABRICKS_CONFIG_PROFILE=DEFAULT python scripts/seed_synthetic_data.py

Requires databricks-sql-connector + a default warehouse (DATABRICKS_WAREHOUSE_ID
env or the 'demo' warehouse is used).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import synthetic  # noqa: E402

CATALOG = os.getenv("UC_CATALOG", "fins")
SCHEMA = os.getenv("UC_SCHEMA", "meridian")
WAREHOUSE = os.getenv("DATABRICKS_WAREHOUSE_ID", "00a19186c27fa1de")
T = f"`{CATALOG}`.`{SCHEMA}`"

DDL = {
    "dim_security": f"""CREATE TABLE IF NOT EXISTS {T}.dim_security (
        symbol STRING COMMENT 'Ticker / identifier',
        name STRING COMMENT 'Security display name',
        asset_class STRING COMMENT 'equity|etf|future|fx|crypto',
        sector STRING COMMENT 'GICS-style sector',
        industry STRING COMMENT 'Industry label',
        exchange STRING COMMENT 'Listing exchange',
        currency STRING COMMENT 'Quote currency (ISO 4217)',
        market_cap DOUBLE COMMENT 'Latest market capitalization in quote currency'
    ) COMMENT 'Synthetic security master for the Meridian demo app'""",
    "fact_price_daily": f"""CREATE TABLE IF NOT EXISTS {T}.fact_price_daily (
        symbol STRING COMMENT 'Ticker', trade_date DATE COMMENT 'Trading date',
        open DOUBLE COMMENT 'Open', high DOUBLE COMMENT 'High', low DOUBLE COMMENT 'Low',
        close DOUBLE COMMENT 'Close (raw)', adj_close DOUBLE COMMENT 'Dividend/split-adjusted close',
        volume BIGINT COMMENT 'Shares traded'
    ) COMMENT 'Synthetic daily OHLCV bars, GBM with regime shifts. "Latest" = max(trade_date). Returns should use adj_close.'""",
    "fact_fundamentals_quarterly": f"""CREATE TABLE IF NOT EXISTS {T}.fact_fundamentals_quarterly (
        symbol STRING COMMENT 'Ticker', fiscal_period STRING COMMENT 'Fiscal quarter label (Q1..Q4)',
        period_end DATE COMMENT 'Fiscal period end date',
        revenue DOUBLE, gross_profit DOUBLE, operating_income DOUBLE, net_income DOUBLE,
        eps_diluted DOUBLE COMMENT 'Diluted EPS for the quarter',
        free_cash_flow DOUBLE, total_debt DOUBLE, cash DOUBLE, shares_out BIGINT
    ) COMMENT 'Synthetic quarterly fundamentals, roughly consistent with price level'""",
    "fact_portfolio_positions": f"""CREATE TABLE IF NOT EXISTS {T}.fact_portfolio_positions (
        portfolio_id STRING COMMENT 'Portfolio key (demo-core)',
        symbol STRING COMMENT 'Ticker', as_of_date DATE COMMENT 'Position snapshot date',
        quantity DOUBLE COMMENT 'Shares held', cost_basis DOUBLE COMMENT 'Total cost in USD',
        market_value DOUBLE COMMENT 'Mark-to-market value at as_of_date'
    ) COMMENT 'Synthetic demo portfolio positions'""",
    "fact_news_events": f"""CREATE TABLE IF NOT EXISTS {T}.fact_news_events (
        symbol STRING COMMENT 'Ticker', ts TIMESTAMP COMMENT 'Publication timestamp',
        headline STRING COMMENT 'Headline text', source STRING COMMENT 'News source',
        sentiment_score DOUBLE COMMENT '-1..1 sentiment'
    ) COMMENT 'Synthetic news headlines'""",
    "fact_events": f"""CREATE TABLE IF NOT EXISTS {T}.fact_events (
        symbol STRING COMMENT 'Ticker', event_date DATE COMMENT 'Event date',
        kind STRING COMMENT 'E=earnings, D=dividend',
        detail STRING COMMENT 'Human description',
        sentiment STRING COMMENT 'beat|miss|neutral'
    ) COMMENT 'Corporate event badges for the chart time axis'""",
    "app_genie_audit": f"""CREATE TABLE IF NOT EXISTS {T}.app_genie_audit (
        user_email STRING COMMENT 'End user identity',
        question STRING COMMENT 'Natural-language question',
        conversation_id STRING, message_id STRING,
        status STRING COMMENT 'Genie status or FEEDBACK_<rating>',
        latency_s DOUBLE COMMENT 'Seconds to terminal status',
        row_count BIGINT COMMENT 'Rows in the result (never the rows themselves)',
        sql_hash STRING COMMENT 'SHA-256 of generated SQL (16 chars)',
        created_at TIMESTAMP
    ) COMMENT 'Meridian Genie interaction audit log — metadata only, no result rows'""",
}

VIEWS = {
    "v_returns": f"""CREATE OR REPLACE VIEW {T}.v_returns COMMENT 'Certified total-return windows per symbol on adj_close. "Latest" = max(trade_date).' AS
WITH d AS (SELECT symbol, trade_date, adj_close FROM {T}.fact_price_daily),
ref AS (SELECT symbol, max(trade_date) AS d0 FROM d GROUP BY symbol),
cut AS (
  SELECT r.symbol, r.d0,
    max(CASE WHEN d.trade_date <  r.d0 THEN d.trade_date END) AS td_1d,
    max(CASE WHEN d.trade_date <= date_sub(r.d0,7)   THEN d.trade_date END) AS td_1w,
    max(CASE WHEN d.trade_date <= date_sub(r.d0,31)  THEN d.trade_date END) AS td_1m,
    max(CASE WHEN d.trade_date <= date_sub(r.d0,93)  THEN d.trade_date END) AS td_3m,
    max(CASE WHEN d.trade_date <= date_sub(r.d0,186) THEN d.trade_date END) AS td_6m,
    max(CASE WHEN d.trade_date <  date_trunc('YEAR', r.d0) THEN d.trade_date END) AS td_ytd,
    max(CASE WHEN d.trade_date <= date_sub(r.d0,365) THEN d.trade_date END) AS td_1y,
    min(d.trade_date) AS td_5y
  FROM ref r JOIN d ON d.symbol = r.symbol
  GROUP BY r.symbol, r.d0
)
SELECT r.symbol,
  l.adj_close AS last, p.adj_close AS prev_close, r.d0 AS as_of,
  round((l.adj_close / p.adj_close - 1) * 100, 2) AS ret_1d,
  round((l.adj_close / w.adj_close - 1) * 100, 2) AS ret_1w,
  round((l.adj_close / m.adj_close - 1) * 100, 2) AS ret_1m,
  round((l.adj_close / q.adj_close - 1) * 100, 2) AS ret_3m,
  round((l.adj_close / s.adj_close - 1) * 100, 2) AS ret_6m,
  round((l.adj_close / y.adj_close - 1) * 100, 2) AS ret_ytd,
  round((l.adj_close / o.adj_close - 1) * 100, 2) AS ret_1y,
  round((l.adj_close / f.adj_close - 1) * 100, 2) AS ret_5y
FROM cut r
JOIN d l ON l.symbol = r.symbol AND l.trade_date = r.d0
LEFT JOIN d p ON p.symbol = r.symbol AND p.trade_date = r.td_1d
LEFT JOIN d w ON w.symbol = r.symbol AND w.trade_date = r.td_1w
LEFT JOIN d m ON m.symbol = r.symbol AND m.trade_date = r.td_1m
LEFT JOIN d q ON q.symbol = r.symbol AND q.trade_date = r.td_3m
LEFT JOIN d s ON s.symbol = r.symbol AND s.trade_date = r.td_6m
LEFT JOIN d y ON y.symbol = r.symbol AND y.trade_date = r.td_ytd
LEFT JOIN d o ON o.symbol = r.symbol AND o.trade_date = r.td_1y
LEFT JOIN d f ON f.symbol = r.symbol AND f.trade_date = r.td_5y""",
    "v_valuation": f"""CREATE OR REPLACE VIEW {T}.v_valuation COMMENT 'Certified valuation multiples vs latest price' AS
WITH f AS (
  SELECT symbol, period_end, revenue, net_income, eps_diluted, free_cash_flow, shares_out,
         row_number() OVER (PARTITION BY symbol ORDER BY period_end DESC) rn
  FROM {T}.fact_fundamentals_quarterly
),
r AS (SELECT symbol, last, as_of FROM {T}.v_returns)
SELECT r.symbol, r.last, r.as_of,
  round(r.last / nullif(f.eps_diluted * 4, 0), 2) AS pe_ttm,
  round(r.last / nullif(f.revenue * 4 / f.shares_out, 0), 2) AS ps_ttm,
  round(f.free_cash_flow * 4 / nullif(r.last * f.shares_out, 0) * 100, 2) AS fcf_yield_pct
FROM r JOIN f ON f.symbol = r.symbol AND f.rn = 1""",
    "v_portfolio_performance": f"""CREATE OR REPLACE VIEW {T}.v_portfolio_performance COMMENT 'Certified position weights, P&L, contribution' AS
SELECT p.portfolio_id, p.symbol, p.quantity, p.cost_basis, p.market_value,
  r.last, round(r.last * p.quantity - p.cost_basis, 2) AS unrealized_pnl,
  round(p.market_value / sum(p.market_value) OVER (PARTITION BY p.portfolio_id) * 100, 2) AS weight_pct
FROM {T}.fact_portfolio_positions p
JOIN {T}.v_returns r ON r.symbol = p.symbol""",
}


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
    from databricks.sdk.core import Config

    return Config(host=host, token=tok["access_token"])


def main() -> None:
    from databricks import sql

    cfg = _cfg()
    conn = sql.connect(
        server_hostname=cfg.host.replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
        credentials_provider=lambda: cfg.authenticate,
    )
    cur = conn.cursor()
    cur.execute(f"USE CATALOG `{CATALOG}`")
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS `{SCHEMA}`")

    tables = ["dim_security", "fact_price_daily", "fact_fundamentals_quarterly",
              "fact_portfolio_positions", "fact_news_events", "fact_events", "app_genie_audit"]
    for name in tables:
        print(f"creating {name}…", flush=True)
        cur.execute(DDL[name])

    for name in ["dim_security", "fact_price_daily", "fact_fundamentals_quarterly",
                 "fact_portfolio_positions", "fact_news_events", "fact_events"]:
        df = synthetic.table(name)
        print(f"seeding {name}: {len(df)} rows…", flush=True)
        cur.execute(f"DELETE FROM {T}.{name}")
        # chunked INSERT — keeps each statement small
        cols = ",".join(df.columns)
        rows = []
        for tup in df.itertuples(index=False, name=None):
            vals = []
            for v in tup:
                if v is None or (isinstance(v, float) and v != v):
                    vals.append("NULL")
                elif isinstance(v, (int,)):
                    vals.append(str(v))
                elif isinstance(v, float):
                    vals.append(repr(round(v, 6)))
                else:
                    s = str(v)
                    if hasattr(v, "date"):
                        s = str(v.date() if callable(getattr(v, "date", None)) else v)[:19]
                    vals.append("'" + s.replace("'", "''")[:500] + "'")
            rows.append("(" + ",".join(vals) + ")")
        for i in range(0, len(rows), 400):
            cur.execute(f"INSERT INTO {T}.{name} ({cols}) VALUES " + ",".join(rows[i:i + 400]))
        print(f"  {name} done", flush=True)

    for name, ddl in VIEWS.items():
        print(f"creating view {name}…", flush=True)
        cur.execute(ddl)

    print("seed complete ✓")


if __name__ == "__main__":
    main()
