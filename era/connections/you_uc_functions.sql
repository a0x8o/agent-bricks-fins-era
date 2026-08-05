-- =========================================================================
-- GENERATED FILE - DO NOT EDIT BY HAND.
--
-- Source of truth : conf/domain_denylist.yaml, conf/routing_policy.yaml
-- Regenerate with : python era/connections/render_uc_functions.py
-- Drift guard     : era/tests/test_uc_function_render.py
--
-- Governed You.com tools for the Agent Bricks Multi-Agent Supervisor.
--
-- Prerequisites:
--   1. era/connections/setup_you_http_connection.py  (creates the connections)
--   2. A secret scope holding the You.com key:
--        databricks secrets create-scope era_you
--        databricks secrets put-secret era_you api_key
--
-- NAMING: every function is prefixed era_ on purpose. The repo already ships
-- you_web_search / you_content_extract / you_research from
-- setup_instructor/03b_create_youdotcom_uc_functions.ipynb, which call the
-- free-tier MCP endpoint with no key and no connection. Those stay registered as
-- the Milestone A fallback; these are the governed replacements. Same names would
-- have clobbered the fallback.
--
-- WHAT THIS LAYER DOES AND DOES NOT GIVE YOU:
--   Does     - credential held in UC, per-call parameter control, domain policy
--              pushed to the provider, connection-level lineage in system.access.audit.
--   Does not - request redaction, or an audit row per call. A SQL UDF cannot write
--              to a Delta table, so there are no side effects available here. Full
--              redaction + audit arrive with the code-first agent in Milestone C.
-- =========================================================================

-- -------------------------------------------------------------------------
-- era_you_search - web + news search (fast tier)
--
-- One endpoint returns both: `results.web[]` and `results.news[]`. There is no
-- separate news API, so do not go looking for one.
--
-- MUTUAL EXCLUSIVITY: the Search API rejects a request carrying both
-- include_domains and exclude_domains. The map_filter below enforces exactly one
-- of them structurally - allow-mode when the caller supplies include_domains,
-- otherwise deny-mode with the generated denylist. It is not possible to call this
-- function in a way that sends both.
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION alexxx.era_research.era_you_search(
  query STRING
    COMMENT 'Search keywords. Supports search operators.',
  freshness STRING
    COMMENT 'Recency filter: day, week, month, year, or YYYY-MM-DDtoYYYY-MM-DD. Pass NULL for no filter.',
  result_count INT
    COMMENT 'Max results per section (web and news). Keep this small - every result is crawled and billed. NULL defaults to 5.',
  include_domains STRING
    COMMENT 'Comma-separated allowlist. When supplied the call runs in allow-mode and ONLY these domains are searched. Pass NULL for the default deny-mode, which searches the open web minus the blocked list.'
)
RETURNS STRING
COMMENT 'Governed You.com web and news search. Returns raw JSON with results.web[] and results.news[], or a JSON error envelope on non-200. Use for current events, market reaction and anything after the training cutoff.'
RETURN (
  SELECT
    CASE
      WHEN r.status_code = 200 THEN r.text
      -- Surface the failure as structured JSON rather than an empty string.
      -- WHY: a tool that returns nothing on error invites the model to fill the
      -- gap from memory and present it as a web result. An explicit error lets it
      -- say the search failed.
      ELSE to_json(named_struct(
             'era_error', concat('You.com search returned HTTP ', CAST(r.status_code AS STRING)),
             'body', left(r.text, 500)
           ))
    END
  FROM (
    SELECT http_request(
      conn    => 'you_search_http',
      method  => 'GET',
      path    => '/v1/search',
      headers => map('X-API-Key', secret('era_you','api_key')),
      params  => map_filter(
        map(
          'query',           query,
          'count',           CAST(COALESCE(result_count, 5) AS STRING),
          'freshness',       nullif(trim(COALESCE(freshness, '')), ''),
          'include_domains', CASE WHEN nullif(trim(COALESCE(include_domains, '')), '') IS NOT NULL
                                  THEN include_domains END,
          'exclude_domains', CASE WHEN nullif(trim(COALESCE(include_domains, '')), '') IS NULL
                                  THEN 'zacks.com,fool.com,benzinga.com,investorplace.com,simplywall.st,stocktwits.com,reddit.com,x.com,twitter.com,facebook.com,quora.com,medium.com,substack.com,seekingalpha.com,news.google.com,finance.yahoo.com,msn.com,newsbreak.com,insider.com,businessinsider.com' END
        ),
        (k, v) -> v IS NOT NULL
      )
    ) AS r
  )
);

-- -------------------------------------------------------------------------
-- era_you_contents - full page extraction (fast tier)
--
-- Same host as search (ydc-index.io), POST with a JSON body. Use after a search to
-- read a specific result properly instead of reasoning from a snippet.
--
-- NOT ZDR-COVERED: You.com's zero-data-retention term currently applies to
-- /v1/search only. Anything sent here is retained under standard terms. Do not
-- pass URLs that themselves encode sensitive internal identifiers.
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION alexxx.era_research.era_you_contents(
  urls ARRAY<STRING>
    COMMENT 'URLs to fetch. Keep to the handful you actually intend to cite - each one is a live crawl.'
)
RETURNS STRING
COMMENT 'Fetch clean markdown for specific URLs via You.com Contents. Returns raw JSON, or a JSON error envelope on non-200. Use to read a source before citing it.'
RETURN (
  SELECT
    CASE
      WHEN r.status_code = 200 THEN r.text
      ELSE to_json(named_struct(
             'era_error', concat('You.com contents returned HTTP ', CAST(r.status_code AS STRING)),
             'body', left(r.text, 500)
           ))
    END
  FROM (
    SELECT http_request(
      conn    => 'you_search_http',
      method  => 'POST',
      path    => '/v1/contents',
      headers => map('X-API-Key', secret('era_you','api_key')),
      json    => to_json(named_struct(
                   'urls', urls,
                   'formats', array('markdown', 'metadata')
                 ))
    ) AS r
  )
);

-- -------------------------------------------------------------------------
-- Register with the Multi-Agent Supervisor
--
-- These are ordinary UC functions, so the MAS consumes them exactly the way it
-- already consumes generate_vega_lite_spec. Grant EXECUTE to whichever principal
-- runs the supervisor (and, in Milestone C, to the app service principal).
--
--   GRANT EXECUTE ON FUNCTION alexxx.era_research.era_you_search    TO `<principal>`;
--   GRANT EXECUTE ON FUNCTION alexxx.era_research.era_you_contents  TO `<principal>`;
--
-- The principal also needs USE CONNECTION on the HTTP connections:
--   GRANT USE CONNECTION ON CONNECTION you_search_http TO `<principal>`;
-- -------------------------------------------------------------------------
