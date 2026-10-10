-- Dataset: Agent Payload (datasets/egress_audit)
-- Dashboard: MAG7 Financial You.com Agent (01f1a272be991a68b4b19433b856c87b)
-- Page: Agent Operations
-- Materialization: INELIGIBLE (has calculated fields)
--
-- Calculated fields:
--   Avg Duration (ms) = ROUND(AVG(`execution_duration_ms`), 0)
--   P95 Duration (ms) = ROUND(PERCENTILE(`execution_duration_ms`, 0.95), 0)
--   Status Code Label = CAST(`status_code` AS STRING)

WITH endpoint_info AS (
  SELECT
    served_entity_id,
    endpoint_name,
    created_by,
    ROW_NUMBER() OVER (PARTITION BY served_entity_id ORDER BY endpoint_config_version DESC) AS rn
  FROM
    system.serving.served_entities
)
SELECT
  p.databricks_request_id,
  p.request_date,
  p.request_time,
  p.status_code,
  p.execution_duration_ms,
  p.requester AS requester_id,
  CASE
    WHEN p.requester LIKE '%@%' THEN p.requester
    ELSE CONCAT('SP: ', COALESCE(e.endpoint_name, 'unknown'), ' (', LEFT(p.requester, 8), '...)')
  END AS requester,
  e.endpoint_name
FROM
  alexxx.era_research.era_supervisor_payload p
    LEFT JOIN endpoint_info e
      ON p.served_entity_id = e.served_entity_id
      AND e.rn = 1