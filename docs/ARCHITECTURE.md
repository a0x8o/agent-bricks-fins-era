<!--
This page describes *this* repo. Earlier drafts were grafted from a
manufacturing/legal Streamlit demo and named the wrong app, Genies, and ingest path.
-->

# Architecture (one page)

Two serving stories share this repository. They are not interchangeable.

```
  Workshop path (Layer A — what attendees hit)
  --------------------------------------------
  User
    │
    ▼
  Chatbot App (React + Express, Databricks Apps)
    │  DATABRICKS_SERVING_ENDPOINT = Agent Bricks MAS
    │  Lakebase (ai_chatbot) for chat history
    ▼
  Multi-Agent Supervisor  (config.sa_name)
    ├─ Knowledge Assistant   (filings on the UC volume)
    ├─ Genie space           (ticker_data)
    ├─ generate_vega_lite_spec
    ├─ get_company_summary / compare_companies   (GraphRAG UC functions, not MCP)
    └─ You.com UC functions or optional you-mcp

  ERA path (Layers B/C — additive, not the app default)
  -----------------------------------------------------
  python -m era.agent.log_and_deploy --deploy
    → UC model {catalog}.{schema}.era_supervisor
    → serving endpoint era-supervisor
    → plan / act / synthesize / critique
    → redaction gate + provenance tags
    → databricks bundle run era_release_gate   (must exit 0)
```

**Do not repoint the workshop app at `era-supervisor` until Milestone A is
verified.** `log_and_deploy.py` never overwrites `mas-*-endpoint`. The chatbot
already speaks the ResponsesAgent streaming contract; cutover is an env change
plus `databricks bundle run grant_app_mas_permissions` is *not* that cutover —
that job only restores CAN_QUERY on Agent Bricks children after an app bundle
deploy.

## GraphRAG

SQL Unity Catalog functions over `graphrag_vertices` / `graphrag_edges`. An
earlier FastMCP-on-Apps design failed through the Agent Bricks MCP proxy on
streaming requests (`httpx.ResponseNotRead`, ML-63338).

## Company universe

One list: `conf/companies.yaml`. 26 organisations, 19 tickers, 18 EDGAR filers
— those counts are different on purpose. Synthetic documents are watermarked on
every page.

## Repo anchors

- Workshop: `setup_instructor/`, `config.py`, `chatbot-app/`
- ERA: `era/`, `conf/release_gate.yaml`, `resources/era.yml`
- Corpus: `conf/companies.yaml`, `resources/fetch_filings.py`, `resources/generate_synthetic_docs.py`
