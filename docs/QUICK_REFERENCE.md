<!--
GRAFTED FILE - MODIFIED FROM ORIGINAL
Source repo   : alexxx-db/agent-bricks-fins-legal
Source path   : docs/QUICK_REFERENCE.md
Source commit : cf640d0 (2026-03-23)
Grafted into  : agent-bricks-fins-era on 2026-08-03
Modifications : provenance header added; see this repo's git history for
                all subsequent changes.
License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
                root of this repository. Provided AS-IS.
-->

# Quick reference

One-page cheat sheet. For full explanations see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).

## Env (local)

**Conda (recommended):** `conda env create -f environment.yml && conda activate agent-bricks-fins-legal`

**Or** install from `app/streamlit-chatbot-app/requirements.txt` and `data/scripts/requirements.txt`.

```bash
export SERVING_ENDPOINT=your-endpoint-name
export MLFLOW_EXPERIMENT_ID=your-experiment-id
export DATABRICKS_CONFIG_PROFILE=your-profile
```

Or use `.env` in repo root with the same variables.

## Commands

```bash
# App
cd app/streamlit-chatbot-app && streamlit run app.py

# Tests (set env first)
cd app/streamlit-chatbot-app
python test_no_manual_tracing.py
python test_client_request_id.py

# Bundle (if used)
databricks bundle deploy
```

## Where to edit what

| Change | File(s) | Then |
|--------|--------|------|
| Supply Chain Genie behavior | `genie/mfg-supply-chain-genie.md` | Update Genie Space in Databricks UI |
| Finance Genie behavior | `genie/mfg-finance-genie.md` | Update Genie Space in Databricks UI |
| MAS routing / instructions | `agent_bricks/mas-genie-agent.md` | Update Supervisor Agent in Databricks UI |
| SEC/KA instructions | `agent_bricks/sec-finance-agent.md` | Update KA tile (manage_ka) |
| Vector Search / RAG (financial Q&A) | `docs/VECTOR_SEARCH_AND_RAG.md`, `data/build_finance_chunks.py`, `data/create_vector_search_index.py` | Run chunks job → sync index → add index to KA |
| Chat UI / feedback flow | `app/streamlit-chatbot-app/app.py` | Restart Streamlit |
| Endpoint client / feedback API | `app/streamlit-chatbot-app/model_serving_utils.py` | Restart Streamlit |
| App deployment config | `app/streamlit-chatbot-app/app.yaml` | Redeploy app |
| Demo data | `genie/00-setup-data-genie.ipynb` | Run notebook in Databricks |

## Data location

- **Catalog / schema**: `main.mfg_agent_bricks_demo` (unless changed in `00-setup-data-genie.ipynb`).
- **Tables**: suppliers, inventory_positions, demand_forecast_daily, supply_plan_inbound, product_master, distributors, cogs_reference, sales_orders, contract_texts.
- **Unstructured (KA)**: UC Volume e.g. `main.mfg_agent_bricks_demo.finance_unstructured_data`; chunks table `finance_docs_chunks`; Vector Search index `finance_docs_chunks_index` (see `docs/VECTOR_SEARCH_AND_RAG.md`).

## Glossary (minimal)

- **MAS** = Supervisor Agent (routes to Genie/KA).
- **Genie** = text-to-SQL over UC tables.
- **KA** = Knowledge Assistant (document Q&A).
- **client_request_id** = per-request ID used to tag the MLflow trace for feedback.

## Demo

- **Demo script**: [docs/DEMO_SCRIPT.md](DEMO_SCRIPT.md) — steps, sample questions, expected outcomes.
- **Architecture (one page)**: [docs/ARCHITECTURE.md](ARCHITECTURE.md).
- **Sanity check**: Run notebook `data/sanity_check_demo` in Databricks before presenting.

## Help

- Full guide: [docs/DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
- README: [README.md](../README.md)
- App details: [app/streamlit-chatbot-app/README.md](../app/streamlit-chatbot-app/README.md)
