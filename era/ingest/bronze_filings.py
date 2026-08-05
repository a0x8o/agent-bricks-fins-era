# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : src/ingest_unstructured_docs/transformations/bronze_filings.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
# Lakeflow Spark Declarative Pipelines: ingest unstructured filings from staging into a bronze table.
# Use with pipeline configuration "staging_path" (e.g. /FileStore/rag_staging or a Volume path).
# The downstream job (ingest_to_volume notebook) copies the same files to the target Volume for the KA.

from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Staging path: set in pipeline configuration, or default
STAGING_PATH = spark.conf.get("pipelines.configuration.staging_path", "/FileStore/rag_staging").rstrip("/")


@dp.table(
    comment="Bronze: raw file metadata and content from staging (10k/, 10q/, 8k/). Ingested via Auto Loader."
)
def filings_bronze():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")
        .option("pathGlobFilter", "*.{htm,html,pdf}")
        .option("recursiveFileLookup", "true")
        .load(STAGING_PATH)
    )


@dp.materialized_view(
    comment="File manifest: path, size, modification time. For visibility and downstream copy validation."
)
def filings_manifest():
    return (
        spark.read.table("filings_bronze")
        .select(
            F.col("path"),
            F.col("length").alias("size_bytes"),
            F.col("modificationTime").alias("modification_time"),
        )
        .distinct()
    )
