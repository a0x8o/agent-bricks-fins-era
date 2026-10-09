# Agent Bricks Workshop - Lab Instructions

## Overview

This lab will guide you through creating a comprehensive multi-agent system in Databricks using Agent Bricks. You'll build a financial analysis system that can answer complex questions by combining document knowledge with structured data analysis.

## What You'll Build

By the end of this lab, you'll have created:

1. **Knowledge Assistant**: Analyzes financial documents (10-Ks, 10-Qs, annual reports, earnings materials)
2. **Genie Space**: Natural language to SQL agent for ticker/financial data queries
3. **Unity Catalog Function**: Generates Vega-Lite chart specifications for data visualization
4. **Multi-Agent Supervisor**: Orchestrates all agents to answer complex financial questions
5. **Chatbot App**: Full-stack web application with chat UI, persistent history, and Vega-Lite rendering
6. **(Optional) External MCP Server**: Adds real-time web search capabilities via You.com
7. **(Optional) GraphRAG UC functions**: Adds graph-based company knowledge queries (`get_company_summary`, `compare_companies`) over Delta tables — no external graph database, no MCP server

## Architecture

```
┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐
│   Knowledge Assistant   │    │      Genie Space        │    │  Unity Catalog Function │
│                        │    │   (NL to SQL Agent)     │    │  (Vega-Lite Charts)     │
│ - 10-K documents       │    │                        │    │                        │
│ - 10-Q filings         │    │ - Ticker data          │    │ - Chart generation     │
│ - Annual reports       │    │ - Financial tables     │    │ - Data visualization    │
│ - Earnings materials   │    │ - Market data          │    │ - Interactive graphs   │
└─────────────────────────┘    └─────────────────────────┘    └─────────────────────────┘
             │                             │                             │
             └─────────────┐               │               ┌─────────────┘
                           │               │               │
                           ▼               ▼               ▼
                    ┌─────────────────────────────────────────────┐
                    │         Multi-Agent Supervisor              │
                    │                                           │
                    │  Orchestrates all agents to answer        │
                    │  complex financial analysis questions     │
                    └──────────────────┬──────────────────────────┘
                                       │
                              (optional)│
                    ┌──────────────────┼──────────────────┐
                    ▼                                     ▼
     ┌────────────────────────────┐    ┌────────────────────────────┐
     │ You.com search (UC fn / MCP)│    │ GraphRAG UC functions      │
     │                           │    │                            │
     │ Real-time news, market    │    │ get_company_summary,       │
     │ updates (03b free-tier or │    │ compare_companies over     │
     │ 05 MCP with API key)      │    │ graphrag_* Delta tables    │
     └────────────────────────────┘    └────────────────────────────┘

                                       │
                                       ▼
                    ┌─────────────────────────────────────────────┐
                    │         Chatbot App (Databricks App)        │
                    │                                           │
                    │  React + Express full-stack web app with   │
                    │  streaming chat UI, Lakebase persistence,  │
                    │  and Vega-Lite chart rendering             │
                    └─────────────────────────────────────────────┘
```

## Prerequisites

- Access to a Databricks workspace with Unity Catalog enabled
- Serverless compute enabled (no cluster required - automatically selected when running cells)
- Permissions to create catalogs, schemas, volumes, tables, functions, and Agent Bricks
- Access to the Databricks UI for monitoring and testing Agent Bricks
- **(Optional)** A [You.com API key](https://documentation.you.com/quickstart#get-your-api-key) for adding web search capabilities via MCP server
- **(Optional)** SQL warehouse the app service principal can use, if you enable pro-mode Graph / Data Explorer tabs

## Setup Scripts Overview

This workshop includes automated setup notebooks in the `setup_instructor/` folder:

- **`config.py`**: **[CONFIGURE FIRST]** Central configuration file for catalog, schema, volume names, and supervisor agent name
- **Table setup notebook**: `setup_instructor/00_tables_setup.ipynb` — schema, volume, uploads `data/`, ticker tables
- **`01_instructor_setup_ka.ipynb`**: Creates Knowledge Assistant with 5 knowledge sources
- **`02_instructor_setup_genie.ipynb`**: Creates Genie space for ticker data analysis
- **`03_create_vegalite_uc_function_simple.ipynb`**: Creates Unity Catalog visualization function
- **`04_instructor_setup_sa.ipynb`**: Creates Multi-Agent Supervisor coordinating all agents
- **`06_deploy_chatbot_app.ipynb`**: Deploys Chatbot App with Lakebase database and all permissions
- **`06b_deploy_chatbot_app_pro_OPTIONAL.ipynb`**: **(Optional)** Switches the app into **pro mode** — adds an interactive knowledge-graph view, a data explorer, an embedded Genie + AI/BI dashboard, and a richer multi-agent "thinking" stream (requires `05b`)
- **`05_create_mcp_server_OPTIONAL.ipynb`**: **(Optional)** Adds You.com web search MCP server to the Supervisor
- **`05b_create_ontobricks_graphrag_OPTIONAL.ipynb`**: **(Optional)** Builds `graphrag_*` tables and registers `get_company_summary` / `compare_companies` UC functions (wired by notebook 04)

These notebooks handle the complex configuration automatically, allowing you to focus on testing and understanding the multi-agent workflows.

## Lab Structure

### Phase 0: Configuration (REQUIRED FIRST STEP)
0. Update `config.py` with your catalog, schema, and volume settings.

- For **Vocareum labs** you'll usually either want to use the default 'dbacademy' catalog, or the default catalog created for the user, e.g. "labuser13875106_1773320552". If    you choose "dbacademy", **the admin/instructor will need to grant 'manage' permissions** to the user(s).

### Phase 1: Data Setup and Infrastructure
1. Run table setup notebook to create ticker data tables
2. Upload financial documents to Unity Catalog volumes
3. Verify data setup

### Phase 2: Knowledge Assistant Creation
4. Create Knowledge Assistant using setup notebook
5. Configure multiple document knowledge sources
6. Test document-based question answering

### Phase 3: Genie Space Setup
7. Create Genie Space for ticker data analysis
8. Configure natural language to SQL capabilities
9. Add sample questions and instructions

### Phase 4: Unity Catalog Function Creation
10. Create Vega-Lite chart generation function
11. Test visualization capabilities
12. Register function for agent use

### Phase 5: Multi-Agent Supervisor Integration
13. Create Multi-Agent Supervisor
14. Configure agent orchestration with all tools
15. Test complex multi-agent workflows

### Phase 6: Chatbot App Deployment
16. Deploy full-stack chatbot app connected to the Supervisor Agent
17. Provision Lakebase database for persistent chat history
18. Test the web-based chat interface

### Phase 7: External MCP Server (Optional)
19. Set up You.com API key and Unity Catalog connection
20. Attach MCP server to the Supervisor Agent
21. Test web search capabilities in multi-agent workflows

### Phase 8: GraphRAG UC functions (Optional)
22. Build a company knowledge graph from `conf/companies.yaml` + ticker data as Delta tables
23. Register `get_company_summary` / `compare_companies` as SQL Unity Catalog functions
24. Re-run notebook 04 so the Supervisor picks them up as function tools
25. Test graph-based queries (company fundamentals, comparisons, ownership)

---

## Phase 0: Configuration (REQUIRED FIRST STEP)

### Step 0.1: Configure Your Environment

**⚠️ CRITICAL: Complete this step before running any other notebooks!**

All data, Genie Spaces, and agents will be created in the catalog, schema, and volume you specify here.

- For **Vocareum labs** you'll usually either want to use the default 'dbacademy' catalog, or the default catalog created for the user, e.g. "labuser13875106_1773320552". If    you choose "dbacademy", **the admin/instructor will need to grant 'manage' permissions** to the user(s)

1. **Open and edit `config.py`**:
   ```python
   # YOUR CONFIGURATION - UPDATE THESE VALUES
   catalog = "main"                             # Your Unity Catalog name
   schema = "brandon_cowen"                     # Your schema name (use your username)
   table = "parsed_data"                        # Table for document metadata
   volume_name = "raw_documents"                # Volume for document storage
   sa_name = "Supervisor_Agent_ERA"            # Supervisor Agent name
   ```

2. **Update with your workspace details**:
   - **`catalog`**: The Unity Catalog where all resources will be created
   - **`schema`**: Your personal schema (typically your username or team name)
   - **`volume_name`**: Name for the UC Volume to store financial documents
   - **`table`**: Name for the metadata table
   - **`sa_name`**: Name for the Multi-Agent Supervisor

3. **What gets created in these locations**:
   - **Financial documents**: Uploaded to `/Volumes/{catalog}/{schema}/{volume_name}/`
   - **Ticker data table**: Created as `{catalog}.{schema}.ticker_data`
   - **UC Function**: Registered as `{catalog}.{schema}.generate_vega_lite_spec`
   - **Genie Space**: Configured to query `{catalog}.{schema}.ticker_data`
   - **Knowledge Assistant**: Uses documents from the volume path
   - **Multi-Agent Supervisor**: References all agents created in your schema
   - **(Optional) GraphRAG tables**: `{catalog}.{schema}.graphrag_vertices` and `{catalog}.{schema}.graphrag_edges`

4. **Verify permissions**:
   - Ensure you have `CREATE` permissions on the catalog
   - Verify you can create schemas, volumes, tables, and functions
   - Check that you have Agent Bricks creation permissions

---

## Phase 1: Data Setup and Infrastructure

### Step 1.1: Review Available Data

Your repository contains the following financial document categories:

```
data/
├── 10k/                    # Annual filings (10-K forms)
├── 10Q/                    # Quarterly filings (10-Q forms)
├── annual_reports/         # Annual shareholder reports
├── earning_releases/       # Earnings press releases
└── earning_transcripts/    # Earnings call transcripts
```

### Step 1.2: Run Table Setup Notebook

**This is your first execution step after configuring `config.py`.**

1. **Open `setup_instructor/00_tables_setup.ipynb`**
   - Creates catalog/schema/volume if missing, uploads `data/`, builds per-folder tables
   - Uses serverless compute (no cluster required)

2. **Run all cells in the notebook**:
   - Creates catalog and schema (if they don't exist)
   - Creates Unity Catalog volume for documents
   - Uploads everything under `data/` to the volume, mirroring the folder structure
   - Builds `ticker_data` from the CSV already in `data/ticker_data/` (Mag7 plus every
     listed company in `conf/companies.yaml` once you have refreshed that CSV)
   - To refresh prices, run `resources/download_ticker_data.py` on Databricks **before**
     `00_tables_setup` — the setup notebook does not call yfinance itself
   - Includes price, volume, and financial metrics

### Step 0.1 (recommended): Build the extended document corpus

The repo ships the original Mag7 filings. The cross-industry corpus is built by two
scripts, driven by `conf/companies.yaml`, before you run the notebook above:

```bash
# Real SEC filings (10-K/10-Q, and 20-F for Toyota and Honda) -> data/edgar_10k, data/edgar_10q
# SEC requires a User-Agent that identifies you with a contact address.
python resources/fetch_filings.py --user-agent "Your Name you@example.com"

# Generated reference documents for organisations that publish no filing -> data/synthetic
python resources/generate_synthetic_docs.py
```

Both write `data/corpus_manifest.json`, which records for every document which filing it
came from (accession number, source URL, checksum) or that it was generated. The PDFs are
gitignored — they are reproducible from the manifest.

**Eight of the organisations publish nothing that can be downloaded**, so their documents
are generated with invented figures: FordDirect and Addepar (private), UCLA Health,
Providence and Summa Health (nonprofits that file no securities reports), Nationwide (a
mutual that suspended SEC reporting in 2010), and Henkel and Munich Re (German issuers).
Every page of those documents is watermarked `SYNTHETIC DOCUMENT - NOT A REAL FILING`, they
are indexed as a separate Knowledge Assistant source, and the agent is instructed to say so
whenever it uses one. Nothing in them should be quoted as fact about the real organisation.

3. **Monitor progress**:
   - Watch for confirmation messages after each step
   - Note any errors (usually permission-related)
   - Verify table row counts in output

### Step 1.3: Verify the Setup

After running the table setup notebook, verify everything was created correctly:

```sql
-- Check that your catalog and schema were created
SHOW CATALOGS LIKE '{your_catalog}';
SHOW SCHEMAS IN {your_catalog} LIKE '{your_schema}';

-- Check the volume and uploaded files
LIST '/Volumes/{your_catalog}/{your_schema}/raw_documents/';

-- Check ticker data table
SELECT * FROM {your_catalog}.{your_schema}.ticker_data LIMIT 10;

-- Count rows and check date range
SELECT 
  COUNT(*) as total_rows,
  COUNT(DISTINCT ticker) as num_companies,
  MIN(date) as earliest_date,
  MAX(date) as latest_date
FROM {your_catalog}.{your_schema}.ticker_data;
```

Expected results:
- 7 distinct tickers (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA)
- Multiple days of historical data
- Complete price and volume information

---

## Phase 2: Knowledge Assistant Creation

### Step 2.1: Create Knowledge Assistant Using Setup Notebook

1. **Open and run the Knowledge Assistant setup notebook**:
   - File: `setup_instructor/01_instructor_setup_ka.ipynb`
   - Open in Databricks workspace
   - Uses serverless compute automatically

2. **What the setup notebook does**:
   - Loads configuration from `config.py`
   - Creates a Knowledge Assistant named `Financial_Analysis_Assistant`
   - Configures 5 separate knowledge sources for better organization:
     - `quarterly_reports_10q`: 10-Q quarterly financial reports
     - `annual_reports_10k`: 10-K annual financial reports
     - `earnings_releases`: Quarterly earnings releases and announcements
     - `annual_reports`: Annual reports and business reviews
     - `earnings_transcripts`: Earnings call transcripts and Q&A sessions
   - Adds example questions to guide users

3. **Knowledge Assistant Configuration**:
   - **Name**: `Financial_Analysis_Assistant`
   - **Description**: `A Knowledge Assistant for analyzing financial documents and providing insights on company performance, earnings, and financial metrics.`
   - **Instructions**: Specialized prompts for financial analysis with proper citation requirements
   - **Document Sources**: 153 financial documents across 5 categories

### Step 2.2: Monitor Setup Progress

1. **Wait for Knowledge Assistant creation** (this may take several minutes):
   - The setup notebook will create the Knowledge Assistant with all 5 knowledge sources
   - Monitor the output for the Knowledge Assistant tile ID
   - Example output: `Tile ID: 84104160-d8aa-490f-9251-047cf93f9e77`
   - Initial status will be `NOT_READY` while documents are being indexed

2. **Document indexing time**:
   - Indexing 153 documents typically takes 5-15 minutes
   - Status will change from `NOT_READY` to `ONLINE` when complete
   - You can continue with other phases while this completes

3. **Verify in Databricks workspace**:
   - Navigate to Machine Learning > Knowledge Assistants
   - Look for `Financial_Analysis_Assistant`
   - Check that the status shows "ONLINE" before testing

4. **Test with sample questions** (once ONLINE):
   ```
   - "What were the key revenue trends in the most recent quarterly report?"
   - "What are the main risk factors mentioned in the 10-K filing?"
   - "How did earnings per share change compared to the previous quarter?"
   - "What guidance did management provide for the upcoming quarter or year?"
   ```

---

## Phase 3: Genie Space Setup

### Step 3.1: Create Genie Space Using Setup Notebook

1. **Open and run the Genie Space setup notebook**:
   - File: `setup_instructor/02_instructor_setup_genie.ipynb`
   - Open in Databricks workspace
   - Uses serverless compute automatically

2. **What the setup notebook does**:
   - Loads configuration from `config.py`
   - Creates a Genie Space named `Financial_Data_Explorer`
   - Automatically detects and uses an available SQL warehouse
   - Configures the Genie space to use your ticker data table (`{catalog}.{schema}.ticker_data`)
   - Adds 7 comprehensive sample questions for financial analysis
   - Includes 5 instructional notes about the data structure
   - Adds 4 SQL examples demonstrating query patterns

3. **Genie Space Configuration**:
   - **Name**: `Financial_Data_Explorer`
   - **Description**: `A Genie space for exploring and analyzing financial ticker data through natural language queries`
   - **Data Source**: `{your_catalog}.{your_schema}.ticker_data`
   - **Sample Questions**: Price trends, volume analysis, company comparisons, performance metrics

### Step 3.2: Monitor Genie Space Creation

1. **Wait for creation** (usually quick, under 1 minute):
   - Monitor the notebook output for the Genie Space ID
   - Example output: `Genie ID: 01f118c553c91bd883197c81add4286c`

2. **Verify in Databricks workspace**:
   - Navigate to Data Intelligence > Genie
   - Look for `Financial_Data_Explorer`
   - Check that it shows your ticker data table as a source

3. **Test with sample queries**:
   ```
   - "What are the latest stock prices for all companies?"
   - "Show me the daily trading volume for Apple over the last week"
   - "Compare the closing prices of NVIDIA and Meta"
   - "Which company had the highest trading volume yesterday?"
   - "What is the average closing price for each company?"
   - "Show me Tesla's price range over the last month"
   - "Which stocks had the biggest price increase this week?"
   ```

---

## Phase 4: Unity Catalog Function Creation

### Step 4.1: Create Vega-Lite Chart Generation Function

1. **Open and run the Unity Catalog Function setup notebook**:
   - File: `setup_instructor/03_create_vegalite_uc_function_simple.ipynb`
   - Open in Databricks workspace
   - Uses serverless compute automatically

2. **What the setup notebook does**:
   - Loads configuration from `config.py`
   - Creates a Unity Catalog function named `generate_vega_lite_spec`
   - Registers it in your catalog and schema: `{catalog}.{schema}.generate_vega_lite_spec`
   - Supports multiple chart types: bar, line, scatter, area, pie
   - Returns valid Vega-Lite v5 specifications as JSON strings
   - Includes robust error handling and data validation
   - Provides tooltip and interactive features

3. **Function Configuration**:
   - **Full Name**: `{your_catalog}.{your_schema}.generate_vega_lite_spec`
   - **Parameters**:
     - `chart_description` (string): Natural language description of the chart
     - `data_sample` (string): JSON data for visualization
   - **Returns**: JSON string containing Vega-Lite specification

### Step 4.2: Test the Unity Catalog Function

1. **Monitor function creation**:
   - The notebook will create and test the function automatically
   - Watch for successful registration message
   - Note the full function name for use in the Supervisor

2. **Verify in Databricks workspace**:
   - Navigate to Catalog > Your Catalog > Your Schema
   - Look for `generate_vega_lite_spec` function
   - Check the function signature and description

3. **Test with sample data** (notebook includes these tests):
   ```sql
   -- Bar chart
   SELECT {catalog}.{schema}.generate_vega_lite_spec(
     'bar chart of sales',
     '[{"category": "Jan", "value": 100}, {"category": "Feb", "value": 150}]'
   );

   -- Line chart
   SELECT {catalog}.{schema}.generate_vega_lite_spec(
     'line chart showing revenue trend',
     '[{"month": "Jan", "revenue": 10000}, {"month": "Feb", "revenue": 15000}]'
   );

   -- Scatter plot
   SELECT {catalog}.{schema}.generate_vega_lite_spec(
     'scatter plot',
     '[{"x": 1, "y": 2}, {"x": 2, "y": 4}, {"x": 3, "y": 6}]'
   );
   ```

---

## Phase 5: Multi-Agent Supervisor Integration

### Step 5.1: Create Multi-Agent Supervisor Using Setup Notebook

**Prerequisites**: Ensure the Knowledge Assistant status is `ONLINE` before proceeding. The Supervisor creation will fail if the KA is still `NOT_READY`.

1. **Open and run the Multi-Agent Supervisor setup notebook**:
   - File: `setup_instructor/04_instructor_setup_sa.ipynb`
   - Open in Databricks workspace
   - Uses serverless compute automatically

2. **What the setup notebook does**:
   - Loads configuration from `config.py`
   - Creates a Multi-Agent Supervisor named from `sa_name` in `config.py`
   - Automatically discovers and configures agents for:
     - **Knowledge Assistant**: Financial document analysis (found by name: `Financial_Analysis_Assistant`)
     - **Genie Space**: SQL queries against ticker data (found by name: `Financial_Data_Explorer`)
     - **Unity Catalog Function**: Chart generation (found by path: `{catalog}.{schema}.generate_vega_lite_spec`)
   - Includes comprehensive instructions for multi-agent coordination
   - Adds sample conversation starters demonstrating multi-tool workflows

3. **Supervisor Configuration**:
   - **Name**: the `sa_name` value from `config.py`
   - **Description**: `A multi-agent supervisor that coordinates financial analysis using Knowledge Assistant for document analysis, Genie for SQL queries, and Unity Catalog functions for data visualization`
   - **Agents**: 3 specialized agents working together
   - **Instructions**: Specialized coordination prompts for financial workflow orchestration

### Step 5.2: Monitor Supervisor Creation

1. **Check prerequisites during execution**:
   - Notebook verifies Knowledge Assistant is ONLINE
   - Discovers Genie Space by name
   - Verifies UC Function exists
   - Reports any missing components

2. **Monitor script output**:
   - Look for the Multi-Agent Supervisor ID
   - Example output: `Multi-Agent Supervisor ID: 93b6cc9b-5689-4586-a0eb-43742e53df61`
   - Initial status will be `NOT_READY` while provisioning
   - Status changes to `ONLINE` when ready (usually 1-2 minutes)

3. **Verify in Databricks workspace**:
   - Navigate to Machine Learning > Agents
   - Look for the supervisor named in `config.py` (`sa_name`)
   - Check that all 3 agents are configured correctly
   - Wait for status to show "ONLINE"

### Step 5.3: Test Multi-Agent Workflows

1. **Wait for supervisor to be ONLINE**:
   - Check the status in Machine Learning > Agents
   - The supervisor status should change from NOT_READY to ONLINE

2. **Test individual agent capabilities**:
   ```
   # Knowledge Assistant tests:
   - "What were Apple's key revenue highlights in their latest quarterly report?"
   - "What are the main risk factors mentioned in Meta's 10-K filing?"
   - "Summarize NVIDIA's guidance from their latest earnings call"

   # Genie Space tests (via Supervisor):
   - "What are the latest stock prices for all companies?"
   - "Which company had the highest trading volume yesterday?"
   - "Compare the closing prices of NVIDIA and Meta"

   # Unity Catalog Function tests:
   - "Create a bar chart showing sample sales data"
   - "Generate a line chart visualization"
   ```

3. **Test multi-agent coordination**:
   ```
   - "What risks did Tesla mention in their latest filing and create a chart showing their stock performance over the last month?"
   - "Compare NVIDIA's recent earnings performance with their guidance and create a visualization of their price trends"
   - "Show me the price trends for Apple over time and explain what their documents say about growth strategy"
   - "Analyze Meta's latest quarterly report and compare it with their actual stock performance data"
   ```

4. **Example workflows the Supervisor can handle**:
   - Document analysis + data visualization
   - Cross-reference document insights with quantitative data
   - Comprehensive analysis combining multiple information sources
   - Generate charts based on both structured data and document mentions

---

## Phase 6: Chatbot App Deployment

### Step 6.1: Deploy the Chatbot App

1. **Open and run the chatbot app deployment notebook**:
   - File: `setup_instructor/06_deploy_chatbot_app.ipynb`
   - Open in Databricks workspace
   - Uses serverless compute automatically

2. **What the deployment notebook does**:
   - Automatically discovers the MAS serving endpoint name from your Supervisor Agent
   - Identifies all sub-agent endpoints (e.g., Knowledge Assistant) for permission grants
   - Creates a Lakebase database instance for persistent chat history
   - Creates the Databricks App with all resource bindings (serving endpoints + database)
   - Deploys the source code from the workspace to the app

3. **App Configuration** (set in `config.py`):
   ```python
   app_name = "agent-bricks-chatbot"           # App name prefix
   lakebase_instance_name = "agent-bricks-lakebase"  # Lakebase instance name prefix
   app_resource_suffix = "workshop"            # Suffix for all resource names
   ```

4. **What gets deployed**:
   - **Databricks App**: `{app_name}-{suffix}` (e.g., `agent-bricks-chatbot-workshop`)
   - **Lakebase Instance**: `{lakebase_instance_name}-{suffix}` (e.g., `agent-bricks-lakebase-workshop`)
   - **Permissions**: `CAN_QUERY` on the MAS endpoint and all sub-agent endpoints, `CAN_CONNECT_AND_CREATE` on Lakebase

### Step 6.2: App Architecture

The chatbot app is a full-stack web application:

```
chatbot-app/
├── client/           # React + Vite frontend
│   └── src/
│       ├── components/   # Chat UI, Vega-Lite renderer, sidebar
│       ├── hooks/        # Streaming, chat history, config
│       └── pages/        # Chat and new chat pages
├── server/           # Express.js backend
│   └── src/
│       ├── routes/       # Chat, history, session, config APIs
│       └── middleware/   # Authentication
├── packages/         # Shared libraries
│   ├── ai-sdk-providers/ # Databricks AI SDK integration
│   ├── auth/             # Databricks authentication
│   ├── core/             # Domain types, schemas
│   ├── db/               # Drizzle ORM + Lakebase
│   └── utils/            # Shared utilities
├── app.yaml          # Databricks app runtime config
└── databricks.yml    # Asset bundle config (parameterized)
```

**Key features**:
- Streaming chat responses from the Multi-Agent Supervisor
- Vega-Lite chart rendering for visualization responses
- Persistent chat history via Lakebase (PostgreSQL)
- Conversation management with sidebar navigation
- Databricks-native authentication (OAuth)

### Step 6.3: Verify and Test the App

1. **Check app status**:
   - Navigate to **Compute > Apps** in your Databricks workspace
   - Look for your app (e.g., `agent-bricks-chatbot-workshop`)
   - Wait for status to show **Running** (may take 2-5 minutes for first deployment)

2. **Access the app**:
   - Click the app URL displayed in the notebook output or workspace UI
   - The URL follows the pattern: `https://{app-name}-{workspace-id}.{region}.databricksapps.com`

3. **Test the chat interface**:
   ```
   - "What were Apple's key revenue highlights in their latest quarterly report?"
   - "Show me a chart of Tesla's stock price trends"
   - "Compare NVIDIA's earnings with their stock performance and visualize it"
   ```

4. **Verify persistent history**:
   - Send a few messages, then refresh the page
   - Previous conversations should appear in the sidebar
   - Chat history is stored in Lakebase and persists across sessions

### Step 6.4: Troubleshooting App Deployment

- **App status "Unavailable"**: The app may still be starting. Wait 2-5 minutes and refresh.
- **"No source code" in app page**: Re-run the deployment cell (Step 5) in the notebook.
- **401 errors during deployment**: Token may have expired. Re-run from cell 1 to refresh the notebook context.
- **Lakebase not ready**: Lakebase provisioning can take a few minutes. The app will work without it initially (using in-memory storage) and switch to persistent storage once Lakebase is online.
- **Chat not responding**: Verify the MAS endpoint is ONLINE in Machine Learning > Agents.

---

## Phase 7: External MCP Server (Optional)

This optional phase adds real-time web search capabilities to your Multi-Agent Supervisor using the [You.com](https://you.com) MCP server. Once configured, the Supervisor can search the internet for current news, market updates, and general knowledge to complement its existing document and data analysis capabilities.

### Step 7.1: Prerequisites — Get a You.com API Key

1. **Sign up for a You.com account**:
   - Visit [documentation.you.com/quickstart](https://documentation.you.com/quickstart#get-your-api-key)
   - Follow the quickstart guide to create an account
   - Generate an API key from your dashboard

2. **Keep your API key handy** — you'll need it to create the Unity Catalog connection in the next step.

### Step 7.2: Create the Unity Catalog Connection

Create an HTTP connection in Unity Catalog named `you-mcp` that points to the You.com MCP endpoint:

1. **Navigate to Catalog > External Data > Connections** in your Databricks workspace
2. **Click "Create connection"** and configure:
   - **Connection name**: `you-mcp`
   - **Connection type**: HTTP
   - **Host**: `https://api.you.com:443/mcp`
   - **Authentication**: Bearer token
   - **Token**: Your You.com API key from Step 7.1
3. **Grant permissions**: Ensure your user (and any workshop participants) has `USE CONNECTION` permission on the `you-mcp` connection

> **Note**: If a `you-mcp` connection already exists in your workspace, you can skip this step. The setup notebook will use the existing connection.

### Step 7.3: Add the MCP Server to Your Supervisor

1. **Open and run the MCP server setup notebook**:
   - File: `setup_instructor/05_create_mcp_server_OPTIONAL.ipynb`
   - Open in Databricks workspace
   - Uses serverless compute automatically

2. **What the setup notebook does**:
   - Loads `sa_name` from `config.py` to identify your Supervisor Agent
   - Dynamically looks up the Supervisor Agent tile ID by name
   - Checks if the `you-mcp` MCP server is already attached
   - If not present, adds a new `You_Web_Search` agent (type: `external-mcp-server`) referencing the `you-mcp` connection
   - Verifies the update was applied successfully
   - The notebook is idempotent — re-running it safely detects the MCP server is already present

3. **Updated Supervisor Configuration**:
   After running this notebook, your Supervisor will have 4 agents:
   - **Financial_Documents_Assistant** (serving-endpoint): Knowledge Assistant
   - **Ticker_Data_Explorer** (genie-space): Genie Space for SQL queries
   - **Chart_Generator** (unity-catalog-function): Vega-Lite visualization
   - **You_Web_Search** (external-mcp-server): You.com web search

### Step 7.4: Test Web Search Capabilities

1. **Wait for the Supervisor to finish updating** (usually under 1 minute)

2. **Test web search queries through the Supervisor**:
   ```
   - "What are the latest news headlines about NVIDIA?"
   - "Search for recent analyst opinions on Tesla stock"
   - "What happened in the stock market today?"
   - "Find recent news about Apple's AI strategy"
   ```

3. **Test combined workflows (web search + existing agents)**:
   ```
   - "Search for the latest news about Meta and compare it with what their 10-K filing says about risks"
   - "What are analysts saying about NVIDIA right now? Also show me their recent stock price trend in a chart."
   - "Find current market sentiment for Tesla and compare it with their actual trading volume data"
   ```

---

## Phase 8: GraphRAG Knowledge Graph (Optional)

This optional phase builds a **graph-backed Retrieval-Augmented Generation (GraphRAG)**
layer entirely within Databricks — no external graph database required. The notebook builds
a knowledge graph over the company universe and exposes it to the Supervisor as **SQL Unity
Catalog functions**.

> **Not an MCP server.** An earlier version deployed a FastMCP server as a Databricks App.
> That path is unusable through the Agent Bricks MCP proxy on streaming requests
> (`httpx.ResponseNotRead`, ML-63338), so the graph is exposed as UC functions instead.

### Why GraphRAG?

Graph structures let the Supervisor answer **relationship-centric** questions that are awkward in flat SQL:
- "What are Ford's fundamentals and recent trading activity?" → Company node properties + TRADED_ON traversal
- "Compare Pfizer, Merck and Amgen side by side" → Multi-node comparison across Company vertices
- "Who owns FordDirect?" → an ownership edge to Ford Motor Company

The graph encodes **Company** nodes (one per organisation in `conf/companies.yaml` plus the
Mag7, with fundamentals where the company is listed), **TradingDay** nodes with
prices/volumes/returns, and edges for trading history (`TRADED_ON`, `NEXT_DAY`), sector and
index membership, return correlation, real ownership (`SUBSIDIARY_OF`,
`JOINT_VENTURE_OF`), and document provenance (`HAS_DOCUMENT_SOURCE`, distinguishing real
filings from generated documents).

**The company universe comes from the manifest, not from `ticker_data`.** A third of these
organisations have no ticker — including American Honda Finance, which files a full 10-K
without listed equity — and deriving the graph from the price table would drop every one of
them.

### Step 8.1: Run the GraphRAG Setup Notebook

1. **Open and run the GraphRAG setup notebook**:
   - File: `setup_instructor/05b_create_ontobricks_graphrag_OPTIONAL.ipynb`
   - Open in Databricks workspace
   - Uses serverless compute automatically

2. **What the setup notebook does**:
   - Loads configuration from `config.py` and the company universe from `conf/companies.yaml`
   - Builds Company vertices for every organisation, joining market data where it exists
   - Builds TradingDay vertices and the TRADED_ON / NEXT_DAY chains from `ticker_data`
   - Writes `{catalog}.{schema}.graphrag_vertices` and `{catalog}.{schema}.graphrag_edges` as Delta tables
   - Appends sector, index, ownership, document-provenance, risk-tier and correlation edges
   - Creates the `get_company_summary` and `compare_companies` UC functions, which accept
     a ticker **or** a company name
   - Runs smoke tests, including one asserting that unlisted companies are not labelled
     high-beta purely because they have no beta

3. **Artifacts created**:
   - **Delta Tables**: `graphrag_vertices` and `graphrag_edges` in your catalog/schema
   - **UC Functions**: `get_company_summary`, `compare_companies` (ticker or company name)

4. **Tools the Supervisor gets** (after notebook 04 discovers them):
   - `get_company_summary(company)` — one organisation: fundamentals + recent trading days
   - `compare_companies(companies)` — side-by-side; names or tickers, comma-separated

### Step 8.2: Wire GraphRAG into the Supervisor

Notebook **04** discovers the two UC functions by full name and registers them as
Supervisor tools (`agent_type: function`). Re-run **`04_instructor_setup_sa.ipynb`**
if the Supervisor already existed before 05b. There is no MCP connection and no
GraphRAG Databricks App in this path.

After wiring, the Supervisor will have up to these tools (depending on optional phases):
- **Financial_Documents_Assistant** (serving-endpoint)
- **Ticker_Data_Explorer** (genie-space)
- **Chart_Generator** (unity-catalog-function)
- **You.com search functions** (unity-catalog-function) — if 03b or Phase 7 completed
- **get_company_summary / compare_companies** (unity-catalog-function) — GraphRAG

### Step 8.3: Test GraphRAG Queries

1. **Test graph queries through the Supervisor**:
   ```
   - "What are NVIDIA's stock fundamentals?"
   - "Compare Apple, Microsoft, and Tesla side by side"
   - "Give me a summary of Meta's recent trading activity"
   - "What does the stock knowledge graph contain?"
   ```

2. **Test combined workflows (GraphRAG + existing agents)**:
   ```
   - "Use the knowledge graph to compare NVDA and AAPL fundamentals, then create a bar chart visualizing the comparison"
   - "What does the graph say about Tesla's recent trading? Cross-reference with their 10-K risk factors."
   - "Get NVIDIA's company summary from the graph and search for the latest analyst opinions to compare"
   ```

---

## Testing Your Complete System

### Current Setup Summary

After completing all phases, you should have:

1. **Data Infrastructure**:
   - Unity Catalog: `{your_catalog}.{your_schema}`
   - Volume: `/Volumes/{your_catalog}/{your_schema}/raw_documents/` — the committed Mag7
     documents, plus (if you ran the corpus scripts) 34 real SEC filings under
     `edgar_10k/` and `edgar_10q/` and 8 generated documents under `synthetic/`
   - Table: `{your_catalog}.{your_schema}.ticker_data` (26 symbols, ~1 year of daily history)

2. **Agent Bricks**:
   - **Knowledge Assistant**: `Financial_Analysis_Assistant` (ONLINE)
   - **Genie Space**: `Financial_Data_Explorer` (configured)
   - **UC Function**: `{catalog}.{schema}.generate_vega_lite_spec` (registered)
   - **Multi-Agent Supervisor**: `sa_name` from `config.py` (ONLINE)
   - **Chatbot App**: `agent-bricks-chatbot-workshop` (RUNNING) with Lakebase persistence
   - **(Optional) MCP Server**: `You_Web_Search` via `you-mcp` connection (web search)
   - **(Optional) GraphRAG**: `graphrag_vertices` / `graphrag_edges` tables + the
     `get_company_summary` and `compare_companies` UC functions (company knowledge graph)

### Comprehensive Test Questions

Try these end-to-end test questions with your Multi-Agent Supervisor:

1. **Document Analysis**:
   ```
   - "What were the key revenue trends in Apple's most recent quarterly report?"
   - "What are the main risk factors mentioned in Tesla's 10-K filing?"
   - "Summarize NVIDIA's guidance from their latest earnings call"
   - "Compare the growth strategies mentioned in Meta and Google's annual reports"
   ```

2. **Data Analysis** (via Genie through Supervisor):
   ```
   - "Which company had the highest trading volume yesterday?"
   - "Compare the closing prices of NVIDIA and Meta over the last week"
   - "What is the average closing price for each company this month?"
   - "Show me the top 3 companies by recent trading volume"
   ```

3. **Visualization** (via UC Function):
   ```
   - "Create a bar chart comparing market caps"
   - "Generate a line chart showing revenue trends"
   - "Show me a scatter plot of price vs volume"
   ```

4. **Multi-Agent Coordination** (the real power):
   ```
   - "What risks did Tesla mention in their latest filing? Also show me their stock price trends over the last month in a chart."
   - "Analyze Apple's earnings performance mentioned in their documents and compare it with their actual stock price movements. Create a visualization."
   - "Compare NVIDIA's guidance from earnings calls with their actual stock performance and create a visual representation."
   - "What growth strategies does Meta mention in their reports? Show me how this correlates with their stock performance using a chart."
   ```

5. **Web Search + Multi-Agent** (if Phase 7 completed):
   ```
   - "Search for the latest analyst ratings on NVIDIA and compare with what their earnings documents say about growth"
   - "What's in the news about Apple today? Cross-reference with their recent stock price data and create a chart."
   - "Find current market sentiment for the Magnificent 7 stocks and show me their comparative trading volumes"
   - "Search for recent AI industry news and relate it to NVIDIA's latest quarterly performance from their filings"
   ```

6. **GraphRAG + Multi-Agent** (if Phase 8 completed):
   ```
   - "Use the knowledge graph to get NVIDIA's fundamentals and compare with their latest earnings call commentary"
   - "Compare AAPL, MSFT, and TSLA using the stock graph, then create a visualization of their market caps"
   - "What does the graph say about Meta's recent trading? Search the web for current analyst sentiment to compare."
   - "Get a company summary for all Magnificent 7 stocks from the knowledge graph"
   ```

### Success Criteria

Your multi-agent system should be able to:

- ✅ Answer document-based questions using the Knowledge Assistant
- ✅ Perform quantitative analysis using the Genie Space
- ✅ Create interactive Vega-Lite visualizations using the UC Function
- ✅ Coordinate between agents for complex, multi-faceted questions
- ✅ Provide synthesized insights combining documents and data
- ✅ Generate charts alongside textual analysis
- ✅ Cite sources and explain reasoning for all conclusions
- ✅ Provide a web-based chat interface via the deployed Chatbot App
- ✅ Persist conversation history across sessions via Lakebase
- ✅ Render Vega-Lite charts directly in the chat UI
- ✅ **(Optional)** Search the web for real-time information via the You.com MCP server
- ✅ **(Optional)** Combine web search results with document analysis and data queries
- ✅ **(Optional)** Query a stock knowledge graph for company fundamentals and trading data via GraphRAG
- ✅ **(Optional)** Combine graph queries with document analysis, data queries, and visualizations

---

## Troubleshooting

### Common Issues

1. **Configuration errors**:
   - **Symptom**: `NameError: name 'catalog' is not defined`
   - **Solution**: Ensure you updated `config.py` and the notebook loaded it correctly
   - **Check**: Run cells in order - configuration cells must run before setup cells

2. **Knowledge Assistant not ready**:
   - **Symptom**: KA status shows `NOT_READY`, Supervisor creation fails
   - **Solution**: Wait 5-15 minutes for document indexing to complete
   - **Check**: Navigate to Machine Learning > Knowledge Assistants and verify status
   - **Note**: You can proceed with Phases 3-4 while waiting

3. **Genie Space queries failing**:
   - **Symptom**: "Table not found" or permission errors
   - **Solution**: Verify `ticker_data` table exists in your catalog/schema
   - **Check**: Run `SELECT * FROM {catalog}.{schema}.ticker_data LIMIT 10;`

4. **Multi-Agent Supervisor discovery issues**:
   - **Symptom**: "KA endpoint not found" or "Genie space not found"
   - **Solution**: Verify asset names match exactly (case-sensitive)
   - **Check**: Asset names in notebooks must match what's created
   - **Note**: Supervisor discovers agents by name, not ID

5. **Permission errors**:
   - **Symptom**: "Access denied" when creating resources
   - **Solution**: Verify Unity Catalog permissions
   - **Check**: Ensure CREATE permissions on catalog/schema for tables, volumes, functions

6. **Serverless compute issues**:
   - **Symptom**: `%run` commands fail with "File not found"
   - **Solution**: Use `dbutils.notebook.run()` instead for cross-notebook execution
   - **Note**: Serverless compute uses IPython magic, not Databricks `%run`

7. **MCP server connection issues** (Phase 7):
   - **Symptom**: "Connection not found" or authentication errors when running `05_create_mcp_server_OPTIONAL`
   - **Solution**: Verify the `you-mcp` Unity Catalog connection exists and is configured with a valid You.com API key
   - **Check**: Navigate to Catalog > External Data > Connections and look for `you-mcp`
   - **API key**: Obtain one at [documentation.you.com/quickstart](https://documentation.you.com/quickstart#get-your-api-key)

8. **Supervisor Agent not found** (Phase 7/8):
   - **Symptom**: `AssertionError: Supervisor Agent '<sa_name>' not found`
   - **Solution**: Run Phase 5 first to create the Supervisor, or verify `sa_name` in `config.py` matches the existing Supervisor name

9. **GraphRAG functions missing** (Phase 8):
   - **Symptom**: Supervisor has no company-summary / compare tools
   - **Solution**: Confirm 05b created `{catalog}.{schema}.get_company_summary` and re-run notebook 04
   - **Check**: `SHOW FUNCTIONS IN {catalog}.{schema} LIKE 'get_company_summary'`

10. **GraphRAG functions return empty results** (Phase 8):
    - **Symptom**: Tools respond but return no data
    - **Solution**: Verify `graphrag_vertices` and `graphrag_edges` tables exist and are populated
    - **Check**: `SELECT COUNT(*) FROM `{catalog}`.`{schema}`.graphrag_vertices;`

### Getting Help

- Check Databricks documentation for Agent Bricks
- Review Unity Catalog permissions and setup
- Test individual components before integration
- Monitor agent status and error messages in the UI
- Verify `config.py` settings match your workspace

---

## Next Steps and Extensions

After completing this lab, consider these enhancements:

1. **Add more data sources**:
   - Earnings estimates and analyst reports
   - Real-time news feeds
   - Economic indicators and market data
   - Additional financial metrics tables

2. **Extend with more agents**:
   - Sector-specific analysis agents
   - Risk assessment specialists
   - ESG (Environmental, Social, Governance) analysis
   - Compliance and regulatory review agents

3. **Build automated workflows**:
   - Scheduled financial monitoring reports
   - Alert systems for significant market changes
   - Regular portfolio analysis updates
   - Automated report generation

4. **Enhance data pipelines**:
   - Real-time ticker data ingestion
   - Automated document collection and upload
   - Data quality validation and monitoring
   - Historical data expansion

5. **Add more external MCP servers**:
   - If you completed Phase 7, you already have web search via You.com
   - If you completed Phase 8, the Supervisor can call GraphRAG UC functions over the company graph
   - Explore additional MCP servers from the [Databricks Marketplace](https://docs.databricks.com/en/generative-ai/mcp/external-mcp/) for more external tool integrations
   - Consider building [custom MCP servers](https://docs.databricks.com/en/generative-ai/mcp/custom-mcp/) hosted as Databricks Apps for organization-specific APIs

## Workshop Files Reference

Your completed workshop includes these working components:

```
agent-bricks-workshop/
├── config.py                              # ⚠️ CONFIGURE FIRST - catalog/schema/volume/sa_name settings
├── LAB_INSTRUCTIONS.md                    # This file - full lab guide
├── setup_instructor/
│   ├── 00_tables_setup.ipynb              # ✅ Schema, volume, data upload, ticker tables
│   ├── 01_instructor_setup_ka.ipynb       # ✅ Knowledge Assistant creation
│   ├── 02_instructor_setup_genie.ipynb    # ✅ Genie space for ticker data
│   ├── 03_create_vegalite_uc_function_simple.ipynb  # ✅ Unity Catalog function
│   ├── 04_instructor_setup_sa.ipynb       # ✅ Multi-Agent Supervisor
│   ├── 06_deploy_chatbot_app.ipynb        # ✅ Chatbot App + Lakebase deployment
│   ├── 05_create_mcp_server_OPTIONAL.ipynb  # 🔧 (Optional) You.com MCP server
│   ├── 05b_create_ontobricks_graphrag_OPTIONAL.ipynb  # 🔧 (Optional) GraphRAG UC functions
│   └── README.md                          # Setup documentation
├── chatbot-app/                              # Full-stack chatbot application
│   ├── client/                            # React + Vite frontend
│   ├── server/                            # Express.js backend
│   ├── packages/                          # Shared libraries (AI SDK, auth, DB, etc.)
│   ├── app.yaml                           # Databricks app runtime config
│   └── databricks.yml                     # Asset bundle config (parameterized)
├── resources/
│   ├── data_setup_functions.py            # Helper functions for data setup
│   ├── download_ticker_data.py            # Optional ticker CSV refresh (yfinance)
│   ├── brick_setup_functions.py           # Agent Bricks helper functions
│   ├── fetch_filings.py                   # EDGAR corpus builder
│   ├── generate_synthetic_docs.py         # Watermarked synthetic PDFs
│   └── grant_app_mas_permissions.py       # Re-bind MAS + sub-agent CAN_QUERY after app bundle deploy
└── data/
    ├── 10k/, 10Q/, annual_reports/        # 153 financial documents
    ├── earning_releases/, earning_transcripts/
```

**Execution Order**:
1. **First**: Update `config.py` with your catalog/schema/volume/sa_name/app settings
2. **Second**: Run `setup_instructor/00_tables_setup.ipynb`
3. **Then**: Run setup notebooks 01-04 in `setup_instructor/` (in order)
4. **Deploy App**: Run `06_deploy_chatbot_app` to deploy the chatbot with Lakebase
5. **(Optional)**: Run `05_create_mcp_server_OPTIONAL` after completing step 3 and setting up a `you-mcp` UC connection
6. **(Optional)**: Run `05b_create_ontobricks_graphrag_OPTIONAL` after completing step 3 (no external API key required)

**Congratulations!** You've built a comprehensive financial analysis multi-agent system that can analyze documents, query data, generate visualizations, search the web, query a stock knowledge graph, and coordinate complex analytical workflows.
