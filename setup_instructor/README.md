# Instructor Setup

Set up the full financial analysis multi-agent system on Databricks. You can run everything at once or set up each brick individually.

## Prerequisites

- Databricks workspace with serverless compute enabled
- Unity Catalog access with permissions to create schemas, volumes, tables, and functions
- Python environment with `databricks-sdk` installed (for local execution)
- **(Optional)** You.com web search — via UC functions using the free tier (Step 4b, recommended, no API key needed) or MCP server (Step 7, requires API key)

## Step 0: Configure Your Environment

**⚠️ IMPORTANT: Start here!**

Before running any setup, update `../config.py` with your workspace settings:

```python
catalog = "your_catalog_name"
schema = "your_schema_name" 
volume_name = "raw_documents"
sa_name = "Supervisor_Agent_ERA"
```

This configuration determines where:
- Financial data tables will be created
- Documents will be uploaded (UC Volume)
- Genie Spaces will be registered
- Agents and UC Functions will be stored

## Quick Start — Run All

Open `run_all.ipynb` and run each cell in order. This will:

0. Load your configuration from `config.py`
1. **Run `00_tables_setup.ipynb`** — creates the schema, volume, uploads data files, and builds tables (**required before all other steps**)
2. Create the Knowledge Assistant with financial documents
3. Create the Genie Space for SQL queries
4. Register the Vega-Lite UC Function for visualizations
5. Create the Multi-Agent Supervisor (discovers the above artifacts automatically)
6. Deploy the Chatbot App with Lakebase database and all required permissions
7. **(Optional)** Add the You.com MCP server for web search capabilities

> Note: Steps 2-4 may take several minutes to provision. The Supervisor (step 5) requires the KA to be ONLINE before it can be created. Step 6 deploys a full-stack chatbot app (React + Express) connected to the Supervisor Agent. Step 7 requires the Supervisor to exist and a `you-mcp` Unity Catalog connection configured with your You.com API key.

## Individual Setup

Run each notebook in order. Steps 1-4 can be executed independently, but step 5 depends on artifacts from steps 2-4.

| # | File | What it creates |
|---|------|----------------|
| 0 | `../config.py` | **[EDIT FIRST]** Configure catalog, schema, volume names, and supervisor agent name |
| 1 | `00_tables_setup.ipynb` | **[RUN FIRST]** Creates schema, volume, uploads data files, and builds ticker data tables |
| 2 | `01_instructor_setup_ka.ipynb` | Knowledge Assistant with financial document sources (10-K, 10-Q, earnings) |
| 3 | `02_instructor_setup_genie.ipynb` | Genie Space for natural language SQL queries against ticker data |
| 4 | `03_create_vegalite_uc_function_simple.ipynb` | UC Function for generating Vega-Lite chart specs |
| 4b | `03b_create_youdotcom_uc_functions.ipynb` | **(Optional)** You.com web search, content extraction, and research UC functions |
| 4c | `05b_create_ontobricks_graphrag_OPTIONAL.ipynb` | **(Optional)** GraphRAG tables + `get_company_summary` / `compare_companies` UC functions |
| 5 | `04_instructor_setup_sa.ipynb` | Multi-Agent Supervisor that orchestrates the bricks above (discovers 4b/4c if present) |
| 6 | `06_deploy_chatbot_app.ipynb` | Chatbot App with Lakebase DB, connected to the Supervisor Agent |
| 6b | `06b_deploy_chatbot_app_pro_OPTIONAL.ipynb` | **(Optional)** Switches the app to **pro mode** — knowledge-graph view, data explorer, embedded Genie + AI/BI dashboard, and a richer multi-agent "thinking" stream |
| 7 | `05_create_mcp_server_OPTIONAL.ipynb` | **(Optional)** Adds You.com web search MCP server to the Supervisor |

### Pro mode (optional, more fully-featured app)

The chatbot app ships in two flavors, selected by `app_mode` in `../config.py`
(`"simple"` by default). **Simple** is the chat-only experience. **Pro** adds a dockable
workspace panel with:

- an **interactive knowledge graph** (Vega force-directed) over the OntoBricks GraphRAG tables,
- a **data explorer** with charts + KPI tiles over `ticker_data`,
- an **embedded Genie space + AI/BI dashboard**, and
- an animated **multi-agent "thinking"** indicator during long queries.

To enable it: run `05b` (graph tables + UC functions) before `04` — or re-run `04`
afterwards so the Supervisor picks up the graph tools — deploy the app with `06`,
(optionally) run `03c_create_aibi_dashboard_OPTIONAL` (creates + publishes the AI/BI
dashboard for the Dashboard tab), then run `06b_deploy_chatbot_app_pro_OPTIONAL`. That
notebook resolves the SQL warehouse, Genie space, and AI/BI dashboard, writes the pro
environment into the app, grants the app service principal the needed read permissions,
and redeploys. Set `sql_warehouse_id`, `genie_space_id`/`genie_embed_url`, and
`aibi_dashboard_id`/`aibi_embed_url` in `config.py` to pin exactly what is used/embedded.

> **Dashboard tab:** rendered natively in the app from `ticker_data`, the document tables
> and the ERA payload log via the SQL warehouse (`/api/dashboard-data`) - no iframes, so no
> workspace embedding setting is needed. It appears whenever the warehouse is configured.
> The published AI/BI dashboard from `03c` stays useful in the workspace itself.

> **GraphRAG note:** `05b` builds the `graphrag_*` tables (used by the pro Graph tab) and
> creates two **SQL UC functions** (`get_company_summary`, `compare_companies`) that the
> Supervisor uses as tools (wired in by `04`, granted by `06`). This replaces the earlier
> external-MCP-server-on-Apps approach, which is unusable through the Agent Bricks MCP
> proxy on streaming requests (`httpx.ResponseNotRead`; tracked in ML-63338). SQL UC
> function tools register reliably, exactly like the chart and web-search tools.

Steps 2-4 are independent and can be run in any order. Steps 4b and 4c are optional and add web search (You.com free tier, no API key) and GraphRAG tools. Step 5 discovers the artifacts from steps 2-4c automatically by name, so run the optional ones **before** it. If you add one later, re-run step 5: it updates the existing Supervisor in place rather than creating a second one. Step 6 deploys the chatbot app and requires the Supervisor from step 5. Step 7 is optional and requires the Supervisor from step 5 to already exist.

### Step 4b: You.com Web Search UC Functions (Optional)

Adds three UC functions that call the [You.com MCP server](https://docs.you.com/build-with-agents/mcp-server) free tier, giving your Supervisor Agent real-time web search, content extraction, and research capabilities — **no API key, no signup, no billing required**.

**Why UC functions instead of the MCP approach (Step 7)?**
- **Free tier** — no API key, no signup, no billing needed
- No need to configure a Unity Catalog connection with bearer token authentication
- No Databricks secret scopes to manage
- Native UC function integration with the Supervisor Agent

**Prerequisites:**
1. USAGE + CREATE permissions on your catalog.schema
2. That's it! No API key needed.
3. **Run `03b_create_youdotcom_uc_functions.ipynb`** — creates the UC functions; step 5 (`04`) wires them into the Supervisor

**Functions created:**
| Function | Description |
|----------|-------------|
| `you_web_search` | Web and news search with filtering by recency, country |
| `you_content_extract` | Full page content extraction from URLs (markdown/HTML) |
| `you_research` | Deep web research with content from multiple sources |

> **Note:** Run step 4b **before** step 5 — `04` discovers the functions by name when it builds the Supervisor. If the Supervisor already exists, re-run `04` after 4b; it updates the Supervisor in place.

### Step 6: Chatbot App Deployment

The chatbot app (`06_deploy_chatbot_app.ipynb`) deploys a full-stack web application that provides a chat UI for your Multi-Agent Supervisor:

- **Frontend**: React + Vite with streaming responses, Vega-Lite chart rendering, and chat history
- **Backend**: Express.js server with Vercel AI SDK for Databricks agent integration
- **Database**: Lakebase (managed PostgreSQL) for persistent chat history
- **Permissions**: Automatically grants `CAN_QUERY` on the MAS endpoint and all sub-agent endpoints

**What the notebook does:**
1. Discovers the MAS serving endpoint name automatically
2. Identifies all sub-agent endpoints for permission grants
3. Creates a Lakebase database instance for chat history
4. Creates the Databricks App with all resource bindings
5. Deploys source code from the workspace

**Configuration** (set in `config.py`):
```python
app_name = "agent-bricks-chatbot"           # App name prefix
lakebase_instance_name = "agent-bricks-lakebase"  # Lakebase instance name prefix
app_resource_suffix = "workshop"            # Suffix for all resource names
```

The app will be available at `https://{app_name}-{suffix}-{workspace_id}.{region}.databricksapps.com` once deployed.

### Step 7 Prerequisites (Optional MCP Server)

To add web search capabilities via the You.com MCP server:

1. **Get a You.com API key**: Sign up and obtain your key at [documentation.you.com/quickstart](https://documentation.you.com/quickstart#get-your-api-key)
2. **Create a Unity Catalog connection** named `you-mcp`:
   - Type: HTTP
   - URL: `https://api.you.com:443/mcp`
   - Authentication: Bearer token using your You.com API key
3. **Run `05_create_mcp_server_OPTIONAL.ipynb`** to attach the MCP server to your Supervisor Agent

## Configuration

All notebooks read from `../config.py` for catalog, schema, volume, and supervisor agent name settings. Make sure to update this file with your workspace-specific values before running any setup.

## Troubleshooting

- **Config not found**: Make sure `../config.py` exists and contains `catalog`, `schema`, `volume_name`, and `sa_name` variables.
- **Permission errors**: Verify you have CREATE permissions on your catalog/schema for tables, volumes, and functions.
- **Timeout errors**: Brick creation API calls can take minutes. A timeout usually means the request was submitted successfully — check the Databricks workspace UI for status.
- **KA endpoint not found**: The Knowledge Assistant needs to finish provisioning (status: ONLINE) before the Supervisor can reference it. Wait 5-15 minutes for document indexing, then re-run step 5.
- **MCP server not found**: Ensure the `you-mcp` Unity Catalog connection exists and is configured with a valid You.com API key. See [Step 6 Prerequisites](#step-6-prerequisites-optional-mcp-server) above.
- **Serverless compute issues**: If using `%run` commands on serverless, use `dbutils.notebook.run()` instead for cross-notebook execution.
