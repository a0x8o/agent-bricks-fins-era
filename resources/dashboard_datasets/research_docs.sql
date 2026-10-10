-- Dataset: Research Documents (datasets/research_docs)
-- Dashboard: MAG7 Financial You.com Agent (01f1a272be991a68b4b19433b856c87b)
-- Page: Research Library
-- Materialization: DISABLED (634 rows, live query is sufficient)
--
-- FIX (2026-10-09): Backtick-quoted digit-prefixed table names (`10k_data`,
-- `10q_data`, `8k_data`) to satisfy the materialization engine's stricter SQL
-- parser. Materialization ultimately disabled due to persistent engine failure.

SELECT
  'Annual Reports' AS source,
  file_path,
  file_name,
  file_size,
  file_modification_time,
  document_category
FROM
  alexxx.era_research.annual_reports_data
UNION ALL
SELECT
  'Earning Transcripts' AS source,
  file_path,
  file_name,
  file_size,
  file_modification_time,
  document_category
FROM
  alexxx.era_research.earning_transcripts_data
UNION ALL
SELECT
  'Earning Releases' AS source,
  file_path,
  file_name,
  file_size,
  file_modification_time,
  document_category
FROM
  alexxx.era_research.earning_releases_data
UNION ALL
SELECT
  '10-K Filings' AS source,
  file_path,
  file_name,
  file_size,
  file_modification_time,
  document_category
FROM
  alexxx.era_research.`10k_data`
UNION ALL
SELECT
  '10-Q Filings' AS source,
  file_path,
  file_name,
  file_size,
  file_modification_time,
  document_category
FROM
  alexxx.era_research.`10q_data`
UNION ALL
SELECT
  '8-K Filings' AS source,
  file_path,
  file_name,
  file_size,
  file_modification_time,
  document_category
FROM
  alexxx.era_research.`8k_data`