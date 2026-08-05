<!--
GRAFTED FILE - MODIFIED FROM ORIGINAL
Source repo   : alexxx-db/agent-bricks-fins-legal
Source path   : docs/DEMO_SCRIPT.md
Source commit : cf640d0 (2026-03-23)
Grafted into  : agent-bricks-fins-era on 2026-08-03
Modifications : provenance header added; see this repo's git history for
                all subsequent changes.
License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
                root of this repository. Provided AS-IS.
-->

# Demo Script: Agent Bricks Chatbot

Use this script to run a **clear, repeatable demo** for a nitpicky audience. It gives ordered steps, sample questions, and expected outcomes so you know what “good” looks like.

---

## Prerequisites (check before presenting)

- [ ] **Workspace**: Databricks workspace with Unity Catalog, Agent Framework, Genie, and (optional) Vector Search.
- [ ] **Data**: Synthetic supply chain + finance tables created (`genie/00-setup-data-genie.ipynb`). For financial document Q&A: files in the finance volume and Vector Search index built (see [VECTOR_SEARCH_AND_RAG.md](VECTOR_SEARCH_AND_RAG.md)).
- [ ] **Genie Spaces**: Supply Chain and Finance Genies created and configured with the UC tables; note Genie Space IDs.
- [ ] **MAS**: Supervisor Agent (MAS) created with instructions from `agent_bricks/mas-genie-agent.md`, including Supply Chain Genie, Finance Genie, and (if using) SEC Finance Knowledge Assistant.
- [ ] **Serving endpoint**: MAS (and KA if used) deployed to a serving endpoint; endpoint is **ONLINE**.
- [ ] **App**: Streamlit app running locally or as a Databricks App, with `SERVING_ENDPOINT` and `MLFLOW_EXPERIMENT_ID` set.

**Quick check**: Open the app, ask “What is the projected ending on hand?” — you should get a supply-chain answer. If you get an error, fix the endpoint or env before the demo.

**Optional sanity check**: Run the notebook **`data/sanity_check_demo`** in Databricks to confirm file counts in the finance volume and row count in the chunks table. See [VECTOR_SEARCH_AND_RAG.md](VECTOR_SEARCH_AND_RAG.md#sanity-check-demo-readiness).

---

## One-page architecture (talking point)

```
User
  │
  ▼
Streamlit Chatbot (this app)
  │  SERVING_ENDPOINT, MLflow experiment
  ▼
Databricks Serving Endpoint (MAS)
  │  Routes by intent
  ▼
┌─────────────────────┬─────────────────────┬─────────────────────────────┐
│ Supply Chain Genie  │  Finance Genie      │  SEC Finance KA (optional)  │
│ Text-to-SQL         │  Text-to-SQL        │  RAG over 10-K/10-Q/8-K     │
│                     │                     │  Vector Search index        │
  ▼                     ▼                     ▼
UC tables             UC tables             UC Volume + chunks table
(inventory, demand,    (sales, COGS,         (finance_docs_chunks →
 supply, suppliers)     distributors)         Vector Search index)
```

**Narrative**: “The user talks to one chatbot. A master agent (MAS) decides whether the question is about supply chain, finance analytics, or financial documents, and routes to the right specialist. Supply Chain and Finance use Genie for SQL over our data; document Q&A uses a Knowledge Assistant backed by a Vector Search index over SEC-style filings.”

---

## Demo flow (ordered steps)

### 1. Open the app and set context

- **Do**: Open the Streamlit app (local or Databricks App). Show the header: endpoint name, user.
- **Say**: “We have one chatbot that can answer supply chain, finance, and SEC-style document questions. The backend routes each question to the right agent.”

**Expected**: App loads; no error banner. Placeholder text like “Ask me anything about your supply chain or finance data…”.

---

### 2. Supply Chain Genie

- **Do**: Type: **“What is the projected ending on hand and stockout risk?”**
- **Expected**: Answer refers to inventory, demand, supply (e.g. projected EOH, stockout risk by DC/SKU). You may see an expandable “Agent: Supply Chain Genie” and/or tool call. No raw errors.

**If it fails**: Endpoint may be down or MAS not routing to Supply Chain Genie; check Genie Space ID and MAS instructions.

---

### 3. Finance Genie

- **Do**: Type: **“What is month-over-month revenue growth by SKU?”**
- **Expected**: Answer includes revenue, growth, SKU (and possibly a table or summary). May show “Agent: Finance Genie” and tool call.

**If it fails**: Same as above; confirm Finance Genie is attached to the MAS and tables exist.

---

### 4. Multi-domain (MAS routing)

- **Do**: Type: **“Which SKUs have the highest revenue and are at stockout risk?”**
- **Expected**: Answer combines revenue (Finance) and stockout/inventory (Supply Chain). May show multiple agents or tool calls. Single coherent answer.

**If it fails**: MAS routing or Genie instructions may need to allow multi-step or chaining; check `agent_bricks/mas-genie-agent.md`.

---

### 5. Financial document Q&A (RAG / KA)

- **Do**: Type: **“What did Apple say about liquidity in the latest 10-Q?”** (or substitute a company you have in the Vector Search index, e.g. AAPL, MSFT).
- **Expected**: Answer is grounded in the ingested filings, with a citation (e.g. company, form type, period, section). No investment advice; professional wording.

**If the KA says it doesn’t have that in the documents**: Suggest rephrasing or narrowing (e.g. “Try: ‘Summarize liquidity and cash flow from the most recent 10-Q for [ticker].’”). Document this as a known limitation if your demo set has no 10-Q for that company.

---

### 6. Feedback and observability (optional)

- **Do**: After any assistant reply, click **👍** or **👎**. Optionally open MLflow (experiment from `MLFLOW_EXPERIMENT_ID`) and show the trace for the last request.
- **Expected**: “Feedback submitted” (or similar). In MLflow, the trace for that request is tagged with the same `client_request_id` the app used.

**If feedback fails**: Check `MLFLOW_EXPERIMENT_ID` and that the app can write to that experiment; see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) troubleshooting.

---

## Sample questions (copy-paste)

| # | Question | What to show |
|---|----------|--------------|
| 1 | What is the projected ending on hand and stockout risk? | Supply Chain Genie |
| 2 | What is month-over-month revenue growth by SKU? | Finance Genie |
| 3 | Which SKUs have the highest revenue and are at stockout risk? | MAS multi-domain |
| 4 | What did [Company] say about liquidity in the latest 10-Q? | SEC/KA + Vector Search |
| 5 | Summarize revenue and margin from the last earnings release for [Company]. | SEC/KA + Vector Search |

Use companies you actually have in the Vector Search index (e.g. AAPL, MSFT — see [PDF_SOURCES_AND_STAGING.md](PDF_SOURCES_AND_STAGING.md) and [VECTOR_SEARCH_AND_RAG.md](VECTOR_SEARCH_AND_RAG.md)).

---

## Known limitations (mention if asked)

- **Document Q&A**: Only as good as the ingested set (companies, form types, periods). If no 10-Q for a company, the KA will say so or suggest rephrasing.
- **Synthetic data**: Supply chain and finance tables are synthetic; good for flow and SQL, not for real business numbers.
- **Feedback**: Requires MLflow experiment ID and permissions; feedback attaches to the trace for that request.

---

## If something breaks during the demo

- **“Unable to determine serving endpoint”**: Set `SERVING_ENDPOINT` (and redeploy if using Databricks App).
- **“The assistant is temporarily unavailable”**: Endpoint may be starting or down; wait a minute or check endpoint status in the workspace.
- **Empty or irrelevant answer**: Check that data and (for RAG) the Vector Search index are built and synced; see [VECTOR_SEARCH_AND_RAG.md](VECTOR_SEARCH_AND_RAG.md) and [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md).
- **Wrong agent (e.g. supply chain question answered by finance)**: Refine MAS routing and agent descriptions in `agent_bricks/mas-genie-agent.md`.

For full troubleshooting: [DEVELOPER_GUIDE.md §12](DEVELOPER_GUIDE.md#12-troubleshooting).
