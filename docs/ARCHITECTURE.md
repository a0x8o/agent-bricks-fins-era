<!--
GRAFTED FILE - MODIFIED FROM ORIGINAL
Source repo   : alexxx-db/agent-bricks-fins-legal
Source path   : docs/ARCHITECTURE.md
Source commit : cf640d0 (2026-03-23)
Grafted into  : agent-bricks-fins-era on 2026-08-03
Modifications : provenance header added; see this repo's git history for
                all subsequent changes.
License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
                root of this repository. Provided AS-IS.
-->

# Architecture (one page)

One-page view of how the demo fits together. For full context see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) and [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

```
  User
    │
    ▼
  Streamlit Chatbot (app/streamlit-chatbot-app)
    │  SERVING_ENDPOINT, MLFLOW_EXPERIMENT_ID
    │  Responses API (streaming), client_request_id → MLflow feedback
    ▼
  Databricks Serving Endpoint (MAS)
    │  Routes by intent (supply chain / finance analytics / document Q&A)
    ▼
  ┌─────────────────────┬─────────────────────┬─────────────────────────────┐
  │ Supply Chain Genie  │  Finance Genie      │  SEC Finance KA (optional)  │
  │ Text-to-SQL         │  Text-to-SQL        │  RAG over 10-K/10-Q/8-K      │
  │                     │                     │  Vector Search index         │
  ▼                     ▼                     ▼
  UC tables             UC tables            UC Volume + Delta chunks table
  (inventory, demand,   (sales, COGS,         → Vector Search index
   supply, suppliers)     distributors)        (finance_docs_chunks_index)
```

**Data flow (document Q&A):** Staging → ingest job → UC Volume (10k/10q/8k) → chunk job → `finance_docs_chunks` → Vector Search index sync → KA retrieves at query time → MAS returns answer with citations.

**Repo anchors:** Genie instructions `genie/mfg-*.md`; MAS + KA instructions `agent_bricks/*.md`; ingest + chunk jobs in `databricks.yml`; app `app/streamlit-chatbot-app/app.py`.
