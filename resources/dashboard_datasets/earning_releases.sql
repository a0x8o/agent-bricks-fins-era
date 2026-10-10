-- Dataset: Earning Releases (datasets/earning_releases)
-- Dashboard: MAG7 Financial You.com Agent (01f1a272be991a68b4b19433b856c87b)
-- Page: Research Library
-- Materialization: ENABLED

SELECT
  file_name,
  document_category,
  file_size,
  file_modification_time
FROM
  alexxx.era_research.earning_releases_data