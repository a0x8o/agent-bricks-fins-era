# Genie space configuration — Meridian

`scripts/create_genie_space.py` does this via the API (idempotent — updates the
space titled "Meridian Financial Analyst" if it exists). This doc is the manual
fallback / reference.

## Tables & certified views
`fins.meridian`: dim_security, fact_price_daily, fact_fundamentals_quarterly,
fact_portfolio_positions, fact_news_events, v_returns, v_valuation,
v_portfolio_performance. Table/column comments are in the seed DDL — Genie
quality depends on them.

## General instructions (paste verbatim)
> - "Latest" always means max(trade_date) — never extrapolate beyond available data.
> - Returns are computed on adj_close (dividend-adjusted), not close.
> - Fiscal periods are calendar quarters ending period_end.
> - Currency is USD for all synthetic symbols.
> - Prefer certified views v_returns, v_valuation, v_portfolio_performance over recomputing.
> - Benchmarks: SPY (broad market), QQQ (Nasdaq-100 proxy).
> - Portfolio questions refer to portfolio_id 'demo-core' unless stated otherwise.

## Example Q/A pairs
See `EXAMPLES` in create_genie_space.py (10 pairs covering returns, comparisons,
sector rollups, fundamentals trends, portfolio attribution, screening). Add more
through update-space as the eval harness finds gaps.

## Trusted functions
Core metrics ship as views (v_returns/v_valuation/v_portfolio_performance) —
certified logic Genie reuses instead of reinventing. If the workspace supports
UC metric functions, `ret(symbol, window)` belongs there; views cover it today.
