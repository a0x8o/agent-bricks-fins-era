<!--
GRAFTED FILE - MODIFIED FROM ORIGINAL
Source repo   : alexxx-db/agent-bricks-fins-legal
Source path   : docs/DEVELOPER_GUIDE.md
Source commit : cf640d0 (2026-03-23)
Grafted into  : agent-bricks-fins-era on 2026-08-03
Modifications : provenance header added; see this repo's git history for
                all subsequent changes.
License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
                root of this repository. Provided AS-IS.
-->

# Developer Guide: Databricks Agent Bricks Demo

**Purpose**: This guide lets a new developer (including remote teammates) understand the codebase, run everything locally, change behavior, and fix issues **without constant back-and-forth**. Read it top to bottom once, then use the table of contents and microinstructions as reference.

**If your assignment is RAG, ingestion, Vector Search, or demo polish:** use **[TASKS_SECOND_DEVELOPER.md](TASKS_SECOND_DEVELOPER.md)** as your task list; use this guide for repo and architecture context.

---

## Table of contents

1. [Who this is for](#1-who-this-is-for)
2. [Glossary](#2-glossary)
3. [What this project does (use cases)](#3-what-this-project-does-use-cases)
4. [Architecture overview](#4-architecture-overview)
5. [Repository map (every file)](#5-repository-map-every-file)
6. [Data and schema](#6-data-and-schema)
7. [Onboarding: run the app in 30 minutes](#7-onboarding-run-the-app-in-30-minutes)
8. [Configuration reference](#8-configuration-reference)
9. [Component deep-dives](#9-component-deep-dives)
10. [Microinstructions (copy-paste tasks)](#10-microinstructions-copy-paste-tasks)
11. [FAQ: "I want to… where do I go?"](#11-faq-i-want-to-where-do-i-go)
12. [Troubleshooting](#12-troubleshooting)
13. [Where to get help](#13-where-to-get-help)

---

## 1. Who this is for

- **New developers** joining the project (local or remote).
- **Anyone** who needs to: run the app, add an agent, change Genie instructions, fix a bug, or deploy.
- **You** if you prefer written instructions over ad-hoc explanations.

**You do not need** prior Databricks experience, but you need:
- Python 3.10+.
- Access to a Databricks workspace (URL, credentials, and permissions listed below).
- Ability to run notebooks in Databricks and run Python/Streamlit on your machine.

**Required workspace permissions:**
- Unity Catalog: CREATE SCHEMA, CREATE TABLE, CREATE VOLUME on the target catalog
- Agent Framework: access to create/manage Knowledge Assistants and Supervisor Agents
- Genie Spaces: ability to create and configure Genie Spaces
- Model Serving: CAN_MANAGE on serving endpoints (or CAN_QUERY for app-only use)
- Vector Search: ability to create endpoints and indexes
- MLflow: write access to experiments (for tracing and feedback)
- Compute: access to create or use job clusters (for data pipeline jobs)

---

## 2. Glossary

| Term | Meaning |
|------|--------|
| **Agent Bricks** | Databricks’ pre-built AI “tiles”: Knowledge Assistants (KA), Genie Spaces, and Supervisor Agents (MAS). This repo uses all three. |
| **KA (Knowledge Assistant)** | Document-based Q&A: indexes PDFs/text in a Unity Catalog Volume, answers questions with RAG. Example: SEC Finance agent. |
| **Genie Space** | Text-to-SQL: user asks in natural language, Genie generates and runs SQL on Unity Catalog tables. We have Supply Chain and Finance Genies. |
| **MAS (Supervisor Agent)** | Multi-agent orchestrator: routes a user question to the right sub-agent (e.g. Supply Chain Genie vs Finance Genie), then returns one synthesized answer. Example: MAS Genie agent. |
| **Serving endpoint** | A deployed Databricks model/agent you call via API. The Streamlit app talks to one endpoint (usually the MAS). |
| **Unity Catalog (UC)** | Databricks’ catalog/schema/table (and volume) layer. All demo tables and some PDFs live in UC. |
| **EOH** | Ending on hand: projected inventory balance (used in supply chain). |
| **DC** | Distribution center (warehouse). |
| **SKU** | Stock-keeping unit (product identifier). |
| **Client request ID** | Unique ID generated per chat request; used to tag the MLflow trace so feedback (👍/👎) attaches to the right trace. |
| **MLflow trace** | One record per request in MLflow: inputs, outputs, tool calls, and optional feedback. |
| **Responses API** | Databricks API for chat/completion with streaming; the app uses it via `WorkspaceClient().serving_endpoints.get_open_ai_client().responses.create()`. |

---

## 3. What this project does (use cases)

**End-to-end flow**

1. **Data**: Synthetic supply chain + finance tables (and optionally PDFs) are created in Unity Catalog.
2. **Genie**: Two Genie Spaces turn natural language into SQL over those tables (Supply Chain, Finance).
3. **Agents**: A Supervisor Agent (MAS) routes questions to the right Genie (or chains both). A Knowledge Assistant (KA) answers from SEC-style documents.
4. **Serving**: The MAS (and optionally the KA) are deployed as a **serving endpoint**.
5. **App**: A Streamlit chatbot calls that endpoint, streams answers, and records feedback (👍/👎) to MLflow.

**Who “uses” it**

- **Business user**: Opens the Streamlit app, asks things like “What is stockout risk?” or “Month-over-month revenue by SKU?” and gets answers (and can give feedback).
- **You (developer)**: Change data, Genie instructions, agent instructions, or the app; run tests; deploy.

**Concrete use cases**

- Supply chain: projected EOH, stockout risk, inventory by DC/SKU, inbound plans.
- Finance: revenue, COGS, margin, ASP, MoM/YoY growth by SKU/distributor/region.
- Multi-domain: e.g. “Which SKUs have highest revenue and are at stockout risk?” (MAS chains Supply Chain + Finance).
- SEC/legal: Q&A over 10-K/10-Q, earnings releases, call transcripts (KA).

---

## 4. Architecture overview

```
  User
    │
    ▼
  Streamlit app (app/streamlit-chatbot-app)
    │  SERVING_ENDPOINT, MLFLOW_EXPERIMENT_ID; Responses API (streaming); client_request_id → MLflow
    ▼
  Databricks Serving Endpoint (MAS)
    │  Routes by intent
    ▼
  ┌─────────────────────┬─────────────────────┬─────────────────────────────┐
  │ Supply Chain Genie  │  Finance Genie      │  SEC Finance KA (optional)  │
  │ Text-to-SQL         │  Text-to-SQL        │  RAG over 10-K/10-Q/8-K      │
  │                     │                     │  Vector Search index         │
  ▼                     ▼                     ▼
  UC tables             UC tables            UC Volume + finance_docs_chunks
  (inventory, demand,   (sales, COGS,         → Vector Search index
   supply, suppliers)     distributors)        (main....finance_docs_chunks_index)
```

**Important**: The app does **not** create its own MLflow trace. Only the serving endpoint creates a trace. The app generates a `client_request_id`, then (after the stream ends) finds the endpoint’s trace and tags it with that ID so feedback can be attached later.

---

## 5. Repository map (every file)

**Root**

| File | Purpose |
|------|--------|
| `README.md` | High-level overview, quick start, troubleshooting. Start here. |
| `CLAUDE.md` | Instructions for AI assistants working in this repo (structure, commands, patterns). |
| `.claude/skills/databricks-agent-bricks/SKILL.md` | Agent Bricks “skill”: how to create/manage KA, Genie, MAS; references MCP tools and workflows. |
| `.claude/skills/databricks-agent-bricks/1-knowledge-assistants.md` | KA patterns: docs, instructions, examples, updating content. |
| `.claude/skills/databricks-agent-bricks/2-supervisor-agents.md` | MAS patterns: descriptions, routing, example questions, fallbacks. |
| `databricks.yml` | Databricks Asset Bundle: bundle name, targets (e.g. `dev` workspace), parameterized catalog/schema/endpoint variables. Used by `databricks bundle deploy`. |

**genie/**

| File | Purpose |
|------|--------|
| `00-setup-data-genie.ipynb` | **Run in Databricks.** Creates schema, volume, and synthetic UC tables (suppliers, inventory_positions, demand_forecast_daily, supply_plan_inbound, product_master, distributors, cogs_reference, sales_orders, contract_texts). Widgets: `uc_catalog`, `uc_schema`, `uc_volume`. |
| `mfg-supply-chain-genie.md` | Instructions + SQL patterns for the **Supply Chain Genie**: tables, grain, EOH/stockout definitions, guardrails, example queries. Paste/copy into Genie Space configuration. |
| `mfg-finance-genie.md` | Instructions + SQL patterns for the **Finance Genie**: revenue, COGS, margin, ASP, MoM/YoY, guardrails. Paste/copy into Genie Space configuration. |
| `genie-sql-queries.ipynb` | Example Genie SQL queries; reference only. |

**agent_bricks/**

| File | Purpose |
|------|--------|
| `mas-genie-agent.md` | **MAS (Supervisor) instructions**: description, Supply Chain vs Finance Genie descriptions, routing rules, instruction guidelines, example questions. Used to configure the Master Agent that routes to Genie Spaces. |
| `sec-finance-agent.md` | **KA instructions** for SEC/legal Q&A: description, guardrails, knowledge sources, response guidelines, citation rules, example prompts. Used to configure the Knowledge Assistant. |

**data/**

| File | Purpose |
|------|--------|
| `00-download-unstructured-data.ipynb` | **Run in Databricks.** Prepares or copies unstructured data (e.g. 10-Q, annual reports, call transcripts, earnings releases) into a UC Volume for the SEC/KA. |
| `ingest_to_volume.py` | **Notebook.** Copy 10k/10q/8k from staging path into the finance UC Volume. Run as job `ingest_unstructured_to_volume`. |
| `build_finance_chunks.py` | **Notebook.** Chunk PDF/HTML from the finance volume into Delta table `finance_docs_chunks` for Vector Search. Run as job `build_finance_chunks`. |
| `create_vector_search_index.py` | **Notebook.** Create Vector Search endpoint and Delta Sync index on `finance_docs_chunks`. Run as job `create_vector_search_index` or once manually. |
| `sanity_check_demo.py` | **Notebook.** Demo sanity check: file counts in finance volume, chunks table row count; run before presenting. See `docs/DEMO_SCRIPT.md`. |

**app/streamlit-chatbot-app/**

| File | Purpose |
|------|--------|
| `app.py` | Main Streamlit UI: chat input, streaming display, tool-call/agent-name expanders, 👍/👎 feedback, session state. Requires `SERVING_ENDPOINT`; uses `model_serving_utils.get_agent` and `log_user_feedback`. |
| `model_serving_utils.py` | `SimpleResponsesAgent`: calls Databricks Responses API (streaming), generates `client_request_id`, no client-side trace. `get_agent(endpoint_name)`, `log_user_feedback(client_request_id, thumbs_up, ...)`. |
| `app.yaml` | Databricks App spec: command `streamlit run app.py`, env (SERVING_ENDPOINT from resource, MLFLOW_*, etc.). |
| `requirements.txt` | Python deps: mlflow, openai, streamlit, databricks-sdk, python-dotenv. |
| `test_no_manual_tracing.py` | Asserts only **one** trace per request (endpoint trace only). Needs `SERVING_ENDPOINT`, `MLFLOW_EXPERIMENT_ID`. |
| `test_client_request_id.py` | Asserts client_request_id is set, trace is findable by it, and feedback logs. Needs same env. |
| `test_no_manual_span.py` | Exploratory: different ways to get trace ID without manual span. |
| `test_trace_capture.py` | Exploratory: how trace ID is captured from endpoint (legacy; may use old API). |
| `test_response_id_for_feedback.py` | Exploratory: using response ID for feedback. |

**app/** (other)

| File | Purpose |
|------|--------|
| `query_model_example.ipynb` | Example notebook for querying a model; reference only. |

**docs/**

| File | Purpose |
|------|--------|
| `DEVELOPER_GUIDE.md` | This file. |
| `TASKS_SECOND_DEVELOPER.md` | Task list for second developer: PDF sourcing, Lakeflow ingestion, Vector Search, demo readiness. |
| `INGESTION_PIPELINE.md` | Staging layout, Lakeflow pipeline, copy job, volume output. |
| `PDF_SOURCES_AND_STAGING.md` | Public PDF sources (SEC EDGAR), staging layout, demo set. |
| `VECTOR_SEARCH_AND_RAG.md` | Vector Search index, chunks table, wiring KA to index, refresh steps. |
| `DEMO_SCRIPT.md` | Demo runbook: prerequisites, ordered steps, sample questions, expected outcomes. |
| `ARCHITECTURE.md` | One-page architecture diagram (User → App → MAS → Genie/KA → data). |

---

## 6. Data and schema

**Location**: Catalog `main`, schema `mfg_agent_bricks_demo` (configurable in `00-setup-data-genie.ipynb`).

**Supply chain tables**

| Table | Purpose |
|-------|--------|
| `suppliers` | Supplier master: supplier_id, supplier_name, tier, country. |
| `inventory_positions` | Daily snapshot: dc_id, sku, as_of_date, on_hand_units, safety_stock. |
| `demand_forecast_daily` | Forecast: sku, region, dc_id, demand_date, forecast_units. |
| `supply_plan_inbound` | Inbound: sku, supplier_id, dc_id, ship_date, eta_date, inbound_units. |

**Finance tables**

| Table | Purpose |
|-------|--------|
| `product_master` | SKU metadata: sku, product_family, launch_date, price_tier. |
| `distributors` | Distributor dimension: distributor_id, region, channel. |
| `cogs_reference` | Unit COGS by sku, effective_date. |
| `sales_orders` | Transactions: order_date, sku, distributor_id, region, units, unit_price. |

**Other**

| Asset | Purpose |
|-------|--------|
| `contract_texts` | Contract narratives (Markdown/HTML). |
| UC Volume (e.g. `finance_unstructured_data`) | PDFs for KA: 10-K, 10-Q, annual reports, call transcripts, earnings releases. Filled by ingest job or `00-download-unstructured-data.ipynb`. |
| `finance_docs_chunks` | Delta table of chunked text from the finance volume; source for Vector Search index. Built by `build_finance_chunks` job. |
| Vector Search index (e.g. `finance_docs_chunks_index`) | RAG index over `finance_docs_chunks`; add as knowledge source to SEC Finance KA. See `docs/VECTOR_SEARCH_AND_RAG.md`. |

**Grain and keys**

- Supply chain: reconcile at **sku, dc_id, date** (daily). Join inventory `as_of_date`, demand `demand_date`, inbound `eta_date` on date.
- Finance: typical grain **month** via `date_trunc('month', order_date)`; join cogs with “latest” cost per SKU (e.g. `MAX(effective_date)`).

---

## 7. Onboarding: run the app in 30 minutes

Follow in order. If a step fails, go to [§12 Troubleshooting](#12-troubleshooting).

### 7.1 Clone and Python

```bash
git clone <repo-url>
cd agent-bricks-fins-legal
python3 --version   # must be 3.10+
cd app/streamlit-chatbot-app
pip install -r requirements.txt
```

### 7.2 Databricks CLI and profile

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com
databricks auth profiles   # note your profile name, e.g. DEFAULT or a named profile
```

### 7.3 Create data (in Databricks)

1. Open the workspace in the browser.
2. Import or open `genie/00-setup-data-genie.ipynb`.
3. Set widgets if needed: `uc_catalog` (e.g. `main`), `uc_schema` (e.g. `mfg_agent_bricks_demo`), `uc_volume` (e.g. `finance_unstructured_data`).
4. Run all cells. Confirm tables exist in `main.mfg_agent_bricks_demo`.

(Optional) For SEC/KA: run `data/00-download-unstructured-data.ipynb` and put PDFs in the volume.

### 7.4 Create Genie Spaces (in Databricks)

1. In the UI, create two Genie Spaces (e.g. “Supply Chain Genie”, “Finance Genie”).
2. Attach the correct UC tables to each.
3. Copy instructions and SQL patterns from `genie/mfg-supply-chain-genie.md` and `genie/mfg-finance-genie.md` into each Space’s configuration.
4. Note each Genie Space **ID** (needed for the MAS).

### 7.5 Create and deploy the MAS (in Databricks)

1. Create a Supervisor Agent (MAS). Add two agents: one pointing to the Supply Chain Genie (by Genie space ID), one to the Finance Genie.
2. Paste in instructions from `agent_bricks/mas-genie-agent.md` (description, routing, guidelines).
3. Deploy the MAS to a **serving endpoint**. Note the **endpoint name**.
4. In the endpoint or experiment UI, note the **experiment ID** where traces are logged (numeric).

### 7.6 Environment for local app

From the **repo root** create `.env` (or export in shell):

```bash
# Required
SERVING_ENDPOINT=<your-mas-endpoint-name>
MLFLOW_EXPERIMENT_ID=<experiment-id-from-endpoint>
DATABRICKS_CONFIG_PROFILE=<your-databricks-cli-profile>

# Optional
DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
MLFLOW_TRACKING_URI=databricks
```

### 7.7 Run the app

```bash
cd app/streamlit-chatbot-app
source ../../.env   # or export variables manually
streamlit run app.py
```

Open `http://localhost:8501`. Ask e.g. “What is the projected ending on hand and stockout risk?” or “Month-over-month revenue growth by SKU.”

### 7.8 Run tests (optional)

```bash
cd app/streamlit-chatbot-app
export SERVING_ENDPOINT=<your-endpoint>
export MLFLOW_EXPERIMENT_ID=<your-experiment-id>
python test_no_manual_tracing.py
python test_client_request_id.py
```

---

## 8. Configuration reference

### 8.1 Environment variables (local)

| Variable | Required | Description |
|----------|----------|-------------|
| `SERVING_ENDPOINT` | Yes | Name of the Databricks serving endpoint (usually the MAS). |
| `MLFLOW_EXPERIMENT_ID` | Yes (for feedback/tests) | Experiment ID where the endpoint writes traces. Must match endpoint config. |
| `DATABRICKS_CONFIG_PROFILE` | Yes (for SDK) | Databricks CLI profile name used by the SDK for auth. |
| `DATABRICKS_HOST` | Optional | Workspace URL; often inferred from profile. |
| `MLFLOW_TRACKING_URI` | Optional | Set to `databricks` to use workspace MLflow. |
| `MLFLOW_REGISTRY_URI` | Optional | e.g. `databricks-uc` for UC registry. |

`.env` is loaded by `app.py` via `python-dotenv` (from repo root or current working directory, depending on where you run Streamlit).

### 8.2 app.yaml (Databricks Apps)

- `command`: `["streamlit", "run", "app.py"]`
- `env.SERVING_ENDPOINT`: from resource `valueFrom: "serving-endpoint"`.
- `env.MLFLOW_EXPERIMENT_ID`: workspace-specific; set to the endpoint’s experiment ID.
- `env.MLFLOW_TRACKING_URI`: `databricks`.

When deploying to Databricks Apps, set `MLFLOW_EXPERIMENT_ID` in `app.yaml` to your endpoint’s experiment.

### 8.3 databricks.yml

- `bundle.name`: `databricks-agent-bricks-demo-examples`
- `targets.dev`: workspace host in `databricks.yml` (default placeholder `https://your-workspace.cloud.databricks.com`). Replace with your workspace URL or set `DATABRICKS_HOST` at deploy time.

---

## 9. Component deep-dives

### 9.1 Genie (text-to-SQL)

- **What it is**: A Databricks feature that turns natural language into SQL over UC tables and runs it.
- **What we have**: Two Genie Spaces, configured by the markdown files in `genie/`.
- **To change behavior**: Edit `genie/mfg-supply-chain-genie.md` or `genie/mfg-finance-genie.md`, then update the corresponding Genie Space in the UI (paste instructions, add certified queries if needed).
- **Important**: No system table for Genie spaces; use the UI or `find_genie_by_name`-style tooling to get space IDs.

### 9.2 Agent Bricks (KA and MAS)

- **KA**: Document Q&A. Instructions in `agent_bricks/sec-finance-agent.md`. Data: PDFs in a UC Volume. Create/update via `manage_ka` (see `.claude/skills/databricks-agent-bricks/SKILL.md`).
- **MAS**: Orchestrator. Instructions in `agent_bricks/mas-genie-agent.md`. Sub-agents: Genie space IDs or endpoint names. Create/update via `manage_mas`. Descriptions and routing instructions are critical for good routing.

### 9.3 Streamlit app (app.py)

- **Startup**: Loads `.env`, checks `SERVING_ENDPOINT` (shows error + `st.stop()` if missing), sets MLflow experiment, creates `agent = get_agent(SERVING_ENDPOINT)`.
- **Per message**: Builds `ResponsesAgentRequest` from `st.session_state.messages`, calls `agent.predict_stream(request)`, consumes events (`response.output_text.delta`, `response.output_item.done` with `function_call`, `function_call_output`, `message`), renders markdown with expandable tool calls/outputs and agent name, accumulates full text.
- **After stream**: Gets `client_request_id` and optional `trace_id` from the agent, appends them to session state, appends assistant message. Feedback uses `trace_id` when available, else looks up trace by `client_request_id` tag (set by server when it receives `X-Client-Request-ID`).
- **Feedback**: On 👍/👎, `log_user_feedback(client_request_id, thumbs_up, user_id=...)` looks up the trace by `client_request_id` and calls `mlflow.log_feedback`.

### 9.4 model_serving_utils.py

- **SimpleResponsesAgent**: Wraps `WorkspaceClient().serving_endpoints.get_open_ai_client().responses.create(..., stream=True)`. Generates `client_request_id` per request, does not create an MLflow trace. Filters out `function_call_output` stream events to avoid Pydantic issues; tool output is still shown via `response.output_item.done` in the app.
- **get_agent(endpoint_name)**: Returns a `SimpleResponsesAgent(model=endpoint_name)`.
- **log_user_feedback(client_request_id, thumbs_up, ...)**: Uses `MlflowClient().search_traces` and finds the trace whose tag or info has that `client_request_id`, then `mlflow.log_feedback(...)`.

---

## 10. Microinstructions (copy-paste tasks)

Use these when you need to do a specific task without re-reading the whole guide.

---

### Add a new Genie Space (e.g. “Inventory Genie”)

1. In Databricks, create a new Genie Space and attach the UC tables it should query.
2. In the repo, add `genie/my-inventory-genie.md` with: Purpose, Data tables, Join keys, Definitions, Guardrails, SQL queries (do not include in Instructions).
3. In the UI, paste the “Instructions” part into the Genie Space configuration; add certified SQL if needed.
4. Note the Genie Space ID. To expose it via the chatbot: add it as a new agent in the MAS (Supervisor Agent) and update `agent_bricks/mas-genie-agent.md` with routing rules and an example question.

---

### Change MAS routing (e.g. new sub-agent or new rule)

1. Edit `agent_bricks/mas-genie-agent.md`: update “Routing Instructions” and “Example Questions” and any agent descriptions.
2. In Databricks, open the Supervisor Agent that backs your serving endpoint; update its instructions (and agent list if you added/removed agents) to match the file.
3. Redeploy or save; no app code change unless you add a new endpoint.

---

### Change what the Supply Chain Genie can do (e.g. new metric)

1. Edit `genie/mfg-supply-chain-genie.md`: add the definition, calculation rules, and (if needed) a SQL example under “SQL Queries (do not include in Instructions)”.
2. In Databricks, open the Supply Chain Genie Space; paste updated instructions and add any new certified query.
3. No app or MAS change needed.

---

### Change what the Finance Genie can do

1. Edit `genie/mfg-finance-genie.md` (same idea as Supply Chain).
2. Update the Finance Genie Space in the UI from the updated file.
3. No app or MAS change needed.

---

### Add or change the SEC/KA (Knowledge Assistant)

1. Edit `agent_bricks/sec-finance-agent.md` (guardrails, sources, response guidelines).
2. In Databricks, update the KA tile: use `manage_ka` with `action="create_or_update"` and the same `tile_id` and updated `instructions` (or name/volume_path if needed). See `.claude/skills/databricks-agent-bricks/SKILL.md` and `1-knowledge-assistants.md`.
3. If the KA is a sub-agent of the MAS, ensure the MAS still points at the correct KA tile/endpoint.
4. For **Vector Search–backed RAG**: add the Vector Search index (`main.mfg_agent_bricks_demo.finance_docs_chunks_index`) as a knowledge source to the KA. See `docs/VECTOR_SEARCH_AND_RAG.md`.

---

### Add or refresh Vector Search / RAG for financial Q&A

1. Ensure the finance volume has 10-K/10-Q/8-K files (run ingest job; see `docs/INGESTION_PIPELINE.md`).
2. Run job **Build finance chunks for Vector Search** (notebook `data/build_finance_chunks`) to (over)write `finance_docs_chunks`.
3. Run job **Create Vector Search index** (notebook `data/create_vector_search_index`) or create/update the index once in the UI; then **trigger a sync** on the index.
4. In the KA tile, add the Vector Search index as a knowledge source (use `databricks-gte-large-en` for the index). See `docs/VECTOR_SEARCH_AND_RAG.md`.

---

### Run the app locally from a clean clone

```bash
cd agent-bricks-fins-legal
echo 'SERVING_ENDPOINT=your-endpoint-name
MLFLOW_EXPERIMENT_ID=your-experiment-id
DATABRICKS_CONFIG_PROFILE=your-profile' > .env
cd app/streamlit-chatbot-app
pip install -r requirements.txt
source ../../.env
streamlit run app.py
```

Then open `http://localhost:8501`.

---

### Run tests with correct env

```bash
cd app/streamlit-chatbot-app
export SERVING_ENDPOINT=your-endpoint-name
export MLFLOW_EXPERIMENT_ID=your-experiment-id
python test_no_manual_tracing.py
python test_client_request_id.py
```

---

### Find the experiment ID for your endpoint

In the Databricks UI: go to the serving endpoint, open its details, find the “Experiment” or “MLflow experiment” field. Or use CLI if available, e.g.:

```bash
databricks serving-endpoints get <endpoint-name>
```

Look for an experiment ID in the output and set `MLFLOW_EXPERIMENT_ID` to that value.

---

### Deploy the Streamlit app as a Databricks App

1. Ensure the app’s serving endpoint resource exists in the workspace and the app has CAN_QUERY.
2. In `app/streamlit-chatbot-app/app.yaml`, set `MLFLOW_EXPERIMENT_ID` to your endpoint’s experiment ID.
3. Deploy via Databricks Apps (UI or CI/CD as per your org). The app will get `SERVING_ENDPOINT` from the resource and use the service principal for MLflow.

---

### Add a new UC table and use it in a Genie

1. Create the table (e.g. in a notebook): `CREATE TABLE main.mfg_agent_bricks_demo.my_new_table (...);`
2. In the Genie Space, add the table to the allowed set and (if needed) update the Genie instructions in `genie/mfg-*.md` (tables list, join keys, definitions).
3. Paste the updated instructions into the Genie Space in the UI and add certified queries if useful.

---

## 11. FAQ: "I want to… where do I go?"

| I want to… | Where to look / what to do |
|------------|----------------------------|
| Run the chatbot locally | §7 Onboarding, §8.1 env vars, microinstruction “Run the app locally from a clean clone”. |
| Create or change the data | `genie/00-setup-data-genie.ipynb`, §6 Data and schema. |
| Change Supply Chain logic or SQL | `genie/mfg-supply-chain-genie.md`, then Genie Space in UI. §9.1, microinstruction “Change what the Supply Chain Genie can do”. |
| Change Finance logic or SQL | `genie/mfg-finance-genie.md`, then Genie Space in UI. §9.2, microinstruction “Change what the Finance Genie can do”. |
| Change how the MAS routes questions | `agent_bricks/mas-genie-agent.md`, then Supervisor Agent in UI. §9.2, microinstruction “Change MAS routing”. |
| Change SEC/legal Q&A behavior | `agent_bricks/sec-finance-agent.md`, then KA tile (manage_ka). §9.2, microinstruction “Add or change the SEC/KA”. |
| Refresh financial document Q&A (Vector Search) | `docs/VECTOR_SEARCH_AND_RAG.md`. Run job `build_finance_chunks`, sync the index, ensure KA has the index as knowledge source. |
| Add a new Genie Space | §10 microinstruction “Add a new Genie Space”. |
| Fix “Unable to determine serving endpoint” | Set `SERVING_ENDPOINT` in `.env` or environment; §12 Troubleshooting. |
| Fix duplicate traces or wrong experiment | Set `MLFLOW_EXPERIMENT_ID` to the endpoint’s experiment; §12 Troubleshooting. |
| Understand feedback (👍/👎) flow | §9.3 (app.py) and §9.4 (log_user_feedback). |
| Run or fix tests | §7.8, §8.1; test docstrings in §5; §12 Troubleshooting. |
| Deploy the app to Databricks | §10 “Deploy the Streamlit app as a Databricks App”, `app/streamlit-chatbot-app/README.md`. |

---

## 12. Troubleshooting

**App shows “Unable to determine serving endpoint”**  
- Set `SERVING_ENDPOINT` in `.env` (repo root) or in the environment before `streamlit run app.py`.  
- If deployed as Databricks App, ensure the app has a serving endpoint resource named `serving-endpoint` with CAN_QUERY.

**Two traces per request (duplicate traces)**  
- The endpoint writes to one experiment; the app must use the same one. Set `MLFLOW_EXPERIMENT_ID` to the **endpoint’s** experiment ID (see §10 “Find the experiment ID”). Update `.env` locally or `app.yaml` when deployed.

**Authentication errors (e.g. 403, invalid token)**  
- Run `databricks auth login --host https://<workspace>.cloud.databricks.com`.  
- Set `DATABRICKS_CONFIG_PROFILE` to the profile you use.  
- Confirm the profile has access to the workspace, Unity Catalog, and the serving endpoint.

**Feedback not attaching to the right trace**  
- Ensure `MLFLOW_EXPERIMENT_ID` matches the endpoint experiment.  
- Run `python test_client_request_id.py`; it checks that the trace is found by `client_request_id` and that feedback is logged.  
- In MLflow, check that the trace has a tag or field `client_request_id` matching what the app stores.

**Tests fail with “Set SERVING_ENDPOINT” or “Set MLFLOW_EXPERIMENT_ID”**  
- Export both (or put them in `.env` and source it) before running the test scripts. See §7.8 and §8.1.

**Genie returns wrong or no SQL**  
- Check table permissions and that the Genie Space is attached to the right schema/tables.  
- Refine instructions and certified queries in the Genie Space using the content of `genie/mfg-*.md`.

**MAS routes to the wrong agent**  
- Improve agent **descriptions** and **routing instructions** in `agent_bricks/mas-genie-agent.md` and in the MAS configuration in the UI. Descriptions are the main signal for routing.

---

## 13. Where to get help

- **This guide**: Use the table of contents and FAQ; use microinstructions for repeatable tasks.  
- **README.md** and **app/streamlit-chatbot-app/README.md**: Quick start and app-specific setup.  
- **CLAUDE.md**: For AI-assisted editing (structure, commands, patterns).  
- **`.claude/skills/databricks-agent-bricks/`**: SKILL.md, 1-knowledge-assistants.md, 2-supervisor-agents.md — Agent Bricks patterns and best practices.  
- **Databricks docs**: [Agent Framework](https://docs.databricks.com/aws/en/generative-ai/agent-framework/), [Genie](https://docs.databricks.com/aws/en/genie/), [MLflow Tracing](https://mlflow.org/docs/latest/tracing.html), [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/).  
- **Your team**: If something is workspace- or org-specific (permissions, endpoint names, deployment process), ask a teammate or check internal runbooks.

---

*End of Developer Guide. Keep this file next to the repo and update it when you add new components or change flows.*
