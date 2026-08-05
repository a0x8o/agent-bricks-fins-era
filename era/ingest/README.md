<!--
GRAFTED FILE - MODIFIED FROM ORIGINAL
Source repo   : alexxx-db/agent-bricks-fins-legal
Source path   : src/ingest_unstructured_docs/README.md
Source commit : cf640d0 (2026-03-23)
Grafted into  : agent-bricks-fins-era on 2026-08-03
Modifications : provenance header added; see this repo's git history for
                all subsequent changes.
License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
                root of this repository. Provided AS-IS.
-->

# Ingest Unstructured Docs (Lakeflow pipeline)

Lakeflow Spark Declarative Pipelines code for ingesting unstructured filings from a staging path into Delta.

- **Pipeline**: `ingest_unstructured_docs` (defined in `databricks.yml` under `resources.pipelines`)
- **Transformations**: `transformations/bronze_filings.py`
  - **Streaming table** `filings_bronze`: Auto Loader (`cloudFiles` + `binaryFile`) for `.htm`, `.html`, `.pdf` under the configured `staging_path`
  - **Materialized view** `filings_manifest`: path, size, modification time from the bronze table

Configuration `staging_path` (e.g. `/FileStore/rag_staging`) is read from pipeline configuration. See `docs/INGESTION_PIPELINE.md` for running the pipeline and the copy-to-volume job.
