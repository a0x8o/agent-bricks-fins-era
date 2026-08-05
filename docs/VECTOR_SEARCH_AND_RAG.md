<!--
GRAFTED FILE - MODIFIED FROM ORIGINAL
Source repo   : alexxx-db/agent-bricks-fins-legal
Source path   : docs/VECTOR_SEARCH_AND_RAG.md
Source commit : cf640d0 (2026-03-23)
Grafted into  : agent-bricks-fins-era on 2026-08-03
Modifications : provenance header added; see this repo's git history for
                all subsequent changes.
License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
                root of this repository. Provided AS-IS.
-->

# Vector Search and RAG for Financial Q&A

This document describes the **Vector Search index** over ingested finance documents (10-K, 10-Q, 8-K) and how to wire it to the **Agent Bricks Knowledge Assistant** so the chatbot can answer **Q&A on financial state/health** (revenue, risk, liquidity, guidance, etc.) with RAG.

---

## Overview

| Step | What | Where |
|------|------|--------|
| 1. Ingest | Files in UC Volume | `/Volumes/main/mfg_agent_bricks_demo/finance_unstructured_data/` (10k/, 10q/, 8k/) |
| 2. Chunk | Build Delta table of text chunks | Job `build_finance_chunks` → table `main.mfg_agent_bricks_demo.finance_docs_chunks` |
| 3. Index | Vector Search Delta Sync index | Endpoint `finance-docs-vs-endpoint`, index `main.mfg_agent_bricks_demo.finance_docs_chunks_index` |
| 4. KA | Knowledge Assistant uses index | Add index as knowledge source to SEC Finance KA; MAS routes financial Q&A to KA |

**End-to-end**: User asks in the Streamlit app → MAS routes to SEC Finance KA → KA retrieves from Vector Search index → answer with citations.

---

## Source table: `finance_docs_chunks`

- **Catalog / schema**: `main.mfg_agent_bricks_demo`
- **Table**: `finance_docs_chunks`
- **Schema**:
  - `id` (STRING, primary key) – unique chunk id (hash of source_path + chunk_index)
  - `content` (STRING) – chunk text (used by Vector Search to compute embeddings)
  - `source_path` (STRING) – e.g. `10k/AAPL_10k_2023-09-30.htm`
  - `document_type` (STRING) – `10k`, `10q`, or `8k`
  - `chunk_index` (INT) – order within the source document
- **Change Data Feed**: Enabled (required for Vector Search Delta Sync).

---

## Embedding model and index

- **Embedding model**: `databricks-gte-large-en` (required for Knowledge Assistant compatibility).
- **Vector Search endpoint**: `finance-docs-vs-endpoint` (type: STANDARD).
- **Index name**: `main.mfg_agent_bricks_demo.finance_docs_chunks_index`
- **Index type**: Delta Sync. Embeddings are computed from the `content` column during sync; no pre-computed embedding column in the table.
- **Sync**: TRIGGERED (run sync from the Vector Search UI or after refreshing the chunks table).

---

## How to build and refresh

### Prerequisites

- Files in the finance volume (run the copy job or Lakeflow pipeline first; see [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md)).
- Serverless compute and Unity Catalog enabled.
- Cluster or job with access to the volume and to the Foundation Model API (for `databricks-gte-large-en`).

### 1. Build chunks (Delta table)

Run the notebook `data/build_finance_chunks` or the job **`[Demo] Build finance chunks for Vector Search`**:

- **Input**: Volume path (default `/Volumes/main/mfg_agent_bricks_demo/finance_unstructured_data`).
- **Output**: Overwrites `main.mfg_agent_bricks_demo.finance_docs_chunks`.
- **Notebook deps**: First cell installs `beautifulsoup4` and `pypdf` via `%pip` (run that cell once, then run all).

Parameters (widgets / job base_parameters):

| Parameter | Default | Description |
|-----------|--------|-------------|
| `volume_path` | `/Volumes/main/.../finance_unstructured_data` | UC Volume path with 10k/, 10q/, 8k/ |
| `catalog` | `main` | Catalog for the chunks table |
| `schema` | `mfg_agent_bricks_demo` | Schema for the chunks table |
| `chunk_size` | `800` | Chunk size in characters |
| `chunk_overlap` | `100` | Overlap between consecutive chunks |

### 2. Create or update Vector Search index

Run the notebook `data/create_vector_search_index` or the job **`[Demo] Create Vector Search index (finance docs)`**:

- Creates the endpoint `finance-docs-vs-endpoint` if it does not exist.
- Creates the Delta Sync index on `finance_docs_chunks` with `embedding_source_column="content"` and `embedding_model_endpoint_name="databricks-gte-large-en"`.
- Trigger a sync from the Vector Search UI (Catalog → table → Vector search index → Sync) so the index is populated.

**One-time**: Endpoint and index creation can be done once; re-run when you change index config or create a new index.

### 3. Wire the Knowledge Assistant

1. In Databricks, open **Agent Bricks** and your **SEC Finance Knowledge Assistant** (or create one using instructions from `agent_bricks/sec-finance-agent.md`).
2. Add **Vector Search index** as a knowledge source:
   - Index: `main.mfg_agent_bricks_demo.finance_docs_chunks_index`
   - Ensure the embedding model used by the index is `databricks-gte-large-en` (already set above).
3. Ensure your **Supervisor Agent (MAS)** includes this KA as an agent so the Streamlit app routes financial document Q&A to it.
4. Deploy the MAS to a **serving endpoint** and set `SERVING_ENDPOINT` in the Streamlit app.

---

## Refreshing after new documents

1. Add new files to the staging path and run the **copy job** (`ingest_unstructured_to_volume`) so the volume has the new 10-K/10-Q/8-K files.
2. Run **`build_finance_chunks`** to overwrite the chunks table with all documents in the volume.
3. **Sync the Vector Search index** (Vector Search UI → index → Sync).
4. No change needed on the KA side; it will query the updated index.

---

## Sanity check (demo readiness)

Run the notebook **`data/sanity_check_demo`** in Databricks to verify: (1) file counts under the finance volume (`10k/`, `10q/`, `8k/`), (2) row count for `finance_docs_chunks`. Use the Vector Search UI to run a test query on the index. See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for sample questions.

---

## Troubleshooting

- **No chunks produced**: Check that the volume path is correct and that subfolders `10k/`, `10q/`, `8k/` exist and contain `.htm`, `.html`, or `.pdf` files.
- **Index creation fails**: Ensure the table has Change Data Feed enabled and that the embedding model endpoint `databricks-gte-large-en` is available (Foundation Model APIs or model serving).
- **KA not finding answers**: Confirm the index has been synced after building chunks; check that the SEC Finance KA has this Vector Search index as a knowledge source and that the MAS routes to this KA for financial questions.
- **Parsing errors**: Some PDFs may fail to parse; the chunking notebook skips or logs them. Check driver logs for "Parse error" messages.

---

## References

- [TASKS_SECOND_DEVELOPER.md](TASKS_SECOND_DEVELOPER.md) – Task 3 (Vector Search + Agent Bricks).
- [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) – Staging and copy to volume.
- [PDF_SOURCES_AND_STAGING.md](PDF_SOURCES_AND_STAGING.md) – Document sources and layout.
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) – Repo and architecture.
- Databricks: [Create vector search endpoints and indexes](https://docs.databricks.com/en/generative-ai/create-query-vector-search.html), [Knowledge Assistant](https://docs.databricks.com/en/generative-ai/agent-framework/knowledge-assistants.html).
