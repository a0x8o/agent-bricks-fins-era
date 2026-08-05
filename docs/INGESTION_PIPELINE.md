<!--
GRAFTED FILE - MODIFIED FROM ORIGINAL
Source repo   : alexxx-db/agent-bricks-fins-legal
Source path   : docs/INGESTION_PIPELINE.md
Source commit : cf640d0 (2026-03-23)
Grafted into  : agent-bricks-fins-era on 2026-08-03
Modifications : provenance header added; see this repo's git history for
                all subsequent changes.
License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
                root of this repository. Provided AS-IS.
-->

# Ingestion Pipeline: Staging → Lakeflow + UC Volume

This document describes the **Lakeflow ingestion** setup: a **Lakeflow Spark Declarative Pipelines** pipeline that ingests file metadata (and content) from staging into Delta tables, and a **Workflows job** that copies the same files into the Unity Catalog volume used by the Knowledge Assistant and Vector Search.

---

## Overview

| Step | What | Where |
|------|------|--------|
| 1. Stage | Download or copy files into a staging layout | Local: `data/scripts/staging/` or DBFS/Volume: `/FileStore/rag_staging/` |
| 2a. Lakeflow pipeline | Ingest from staging into Delta (bronze + manifest) | Pipeline `ingest_unstructured_docs` → tables `filings_bronze`, `filings_manifest` |
| 2b. Copy job | Copy files from staging to target volume | Job `ingest_unstructured_to_volume` (notebook `data/ingest_to_volume.py`) |
| 3. Output | Files in volume for KA/Vector Search | `/Volumes/main/mfg_agent_bricks_demo/finance_unstructured_data/` (10k/, 10q/, 8k/) |

- **Lakeflow pipeline** (optional): Uses Auto Loader to stream files from the staging path into a bronze Delta table; good for incremental ingestion and a queryable manifest.
- **Copy job** (required for the KA): Copies files from staging to the target volume so the Knowledge Assistant and Vector Search can index them.

Both are **idempotent**; safe to re-run after adding new files to staging.

---

## Staging layout (input)

The job expects the staging path to contain optional subfolders `10k/`, `10q/`, `8k/`. Each subfolder holds files (e.g. `.htm`, `.html`, `.pdf`). Any missing subfolder is skipped.

```
staging_path/
├── 10k/
│   └── AAPL_10k_2023-09-30.htm
├── 10q/
│   └── AAPL_10q_2024-03-30.htm
└── 8k/
    └── (optional)
```

**How to populate staging**

1. **Local run of the SEC download script** (recommended first time):
   ```bash
   cd data/scripts
   pip install -r requirements.txt   # or: pip install requests
   export SEC_EDGAR_USER_AGENT="YourApp admin@example.com"
   python download_sec_filings.py --tickers AAPL MSFT --max-per-type 1 --output-dir ./staging
   ```
   Then **upload** the `staging/` folder to DBFS or a Volume so Databricks can read it (e.g. drag-and-drop to `/FileStore/rag_staging` in the Databricks UI, or use `databricks fs cp`).

2. **Direct write to DBFS/Volume**: If you have another process that writes files into `/FileStore/rag_staging/10k/` (and 10q/, 8k/), point the job’s `staging_path` at that path.

---

## Lakeflow pipeline (Spark Declarative Pipelines)

- **Pipeline name**: `[Demo] Ingest unstructured docs (Lakeflow)`
- **Config**: `databricks.yml` → `resources.pipelines.ingest_unstructured_docs`
- **Source**: `src/ingest_unstructured_docs/transformations/bronze_filings.py` (streaming table `filings_bronze`, materialized view `filings_manifest`)
- **Staging path**: Set via pipeline configuration `staging_path` (default `/FileStore/rag_staging`). The pipeline uses Auto Loader (`cloudFiles` + `binaryFile`) to ingest all `.htm`, `.html`, `.pdf` under that path.
- **Output tables**: `main.mfg_agent_bricks_demo.filings_bronze`, `main.mfg_agent_bricks_demo.filings_manifest`
- **Storage**: Pipeline checkpoints/tables use `/Volumes/main/mfg_agent_bricks_demo/pipeline_storage`. Create that volume if it does not exist (e.g. in the same way as `finance_unstructured_data`).

**Run the Lakeflow pipeline** (after deploy):
```bash
databricks pipelines run ingest_unstructured_docs --target dev
# or: databricks bundle deploy -t dev, then run from Workflows UI
```

---

## Job definition (copy to volume)

The **copy job** is defined in the same bundle.

- **Job name**: `[Demo] Ingest unstructured docs to UC Volume`
- **Notebook**: `data/ingest_to_volume.py` (Databricks Python notebook format)
- **Config file**: `databricks.yml` → `resources.jobs.ingest_unstructured_to_volume`

**Parameters (widgets / base_parameters)**

| Parameter | Default | Description |
|-----------|--------|-------------|
| `staging_path` | `/FileStore/rag_staging` | Path (DBFS or Volume) where 10k/10q/8k subfolders live. |
| `uc_catalog` | `main` | Unity Catalog catalog for the target volume. |
| `uc_schema` | `mfg_agent_bricks_demo` | Schema for the target volume. |
| `uc_volume` | `finance_unstructured_data` | Target volume name. |
| `write_manifest` | `true` | If `true`, write a Delta table `{catalog}.{schema}.pdf_manifest` with columns `path`, `document_type`. |

---

## How to run the pipeline

### Option A: Deploy with the bundle and run the job

1. Deploy the bundle (uploads the notebook and creates/updates the job):
   ```bash
   databricks bundle deploy -t dev
   ```
2. In the Databricks UI: **Workflows** → **Jobs** → find **"[Demo] Ingest unstructured docs to UC Volume"** → **Run now**.
3. Or override parameters when running: set `staging_path` (and others) in the job run form.

### Option B: Run the notebook interactively

1. Open the notebook `data/ingest_to_volume.py` in the workspace (e.g. after repo sync or upload).
2. Set the widgets (staging path, catalog, schema, volume, write_manifest).
3. Run all cells.

### Option C: Run once via CLI (if supported)

```bash
databricks jobs run-now --job-id <job-id> --python-params '{"staging_path":"/Volumes/main/mfg_agent_bricks_demo/staging_input"}'
```

(Exact CLI and parameter format may vary by workspace; use the UI or your org’s runbook if different.)

---

## Output

- **Target volume**: `{uc_catalog}.{uc_schema}.{uc_volume}` → path `/Volumes/{catalog}/{schema}/{volume}/`.
- **Subfolders**: `10k/`, `10q/`, `8k/` with the same filenames as in staging.
- **Optional manifest table**: `main.mfg_agent_bricks_demo.pdf_manifest` (path, document_type) when `write_manifest=true`.

After the run, (1) refresh or re-index the Knowledge Assistant if it reads from this volume, and (2) update the Vector Search index if you have one that sources from this volume.

---

## Schedule (optional)

The job definition in `databricks.yml` includes an optional schedule (daily at 6 AM UTC). To run only manually, remove or comment out the `schedule` block under `ingest_unstructured_to_volume` and redeploy.

---

## Troubleshooting

| Issue | What to do |
|-------|------------|
| Job fails: "path not found" | Ensure `staging_path` exists and contains at least one of 10k/, 10q/, 8k/. Upload staging files to DBFS or a Volume first. |
| No files copied | Check that subfolders are named exactly `10k`, `10q`, `8k` (lowercase) and contain files (not only subdirs). |
| Permission denied on volume | Ensure the job’s cluster or job compute has WRITE access to the target volume (and READ to staging path). |
| Manifest table already exists | The job overwrites the manifest when `write_manifest=true`. If you use a different table name, add a parameter for it and update the notebook. |

---

## Related docs

- [PDF_SOURCES_AND_STAGING.md](PDF_SOURCES_AND_STAGING.md) – Where to get public PDFs and how to run the download script.
- [TASKS_SECOND_DEVELOPER.md](TASKS_SECOND_DEVELOPER.md) – Full task list for the second developer (Vector Search, demo readiness).
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) – Repo and architecture overview.
