-- Dataset: P/E Ratios Latest (datasets/pe_ratios)
-- Dashboard: MAG7 Financial You.com Agent (01f1a272be991a68b4b19433b856c87b)
-- Page: Valuation Metrics
-- Materialization: ENABLED

SELECT
  company_name,
  'Trailing P/E' AS metric,
  pe_trailing AS value
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
UNION ALL
SELECT
  company_name,
  'Forward P/E' AS metric,
  pe_forward AS value
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