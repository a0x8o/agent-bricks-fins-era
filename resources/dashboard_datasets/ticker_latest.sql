-- Dataset: Ticker Latest Date (datasets/ticker_latest)
-- Dashboard: MAG7 Financial You.com Agent (01f1a272be991a68b4b19433b856c87b)
-- Pages: Market Overview, Valuation Metrics
-- Materialization: ENABLED

SELECT
  *
FROM
  alexxx.era_research.ticker_data
WHERE
  Date
    = (
      SELECT
        MAX(Date)
      FROM
        alexxx.era_research.ticker_data
    )