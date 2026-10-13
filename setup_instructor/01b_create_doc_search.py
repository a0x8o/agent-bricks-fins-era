# Databricks notebook source
# MAGIC %md
# MAGIC # 01b — Document search with Vector Search (Knowledge Assistant replacement)
# MAGIC
# MAGIC Some accounts can no longer create a Knowledge Assistant ("legacy feature"). This notebook
# MAGIC gives the supervisor the same document Q&A another way:
# MAGIC
# MAGIC 1. Extracts page text from every corpus PDF in the volume (`pypdf`; the corpus PDFs all carry
# MAGIC    a text layer, so no OCR/AI parsing cost) and chunks it into `doc_chunks`.
# MAGIC 2. Indexes the chunks on a Vector Search endpoint with managed `databricks-gte-large-en` embeddings.
# MAGIC 3. Registers `search_filings(query)`, a SQL UC function that `04` wires in as the document agent
# MAGIC    whenever no Knowledge Assistant exists.
# MAGIC
# MAGIC Passages keep their source split (same knowledge sources as `01`) and the synthetic flag, so a
# MAGIC passage from a generated document is labelled as such in what the supervisor reads.
# MAGIC
# MAGIC Prereqs: `00_tables_setup` (uploads `data/` to the volume). Run before `04`. Re-running is safe:
# MAGIC the chunk table is rebuilt and the index re-synced.

# COMMAND ----------

# MAGIC %pip install pypdf

# COMMAND ----------

exec(open('../config.py').read())
import os
import time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

VOLUME = f"/Volumes/{catalog}/{schema}/{volume_name}"
CHUNKS_TABLE = f"{catalog}.{schema}.doc_chunks"
VS_ENDPOINT = "era-docs-vs"
VS_INDEX = f"{catalog}.{schema}.doc_chunks_index"
SEARCH_FN = f"{catalog}.{schema}.search_filings"
EMBEDDING_MODEL = "databricks-gte-large-en"

# Volume folder -> knowledge source label, the same split 01 gives the Knowledge Assistant.
# The synthetic folder stays its own source; do not merge it into the real filings.
SOURCES = {
    "10Q": "quarterly_reports_10q",
    "10k": "annual_reports_10k",
    "earning_releases": "earnings_releases",
    "annual_reports": "annual_reports",
    "earning_transcripts": "earnings_transcripts",
    "edgar_10k": "sec_annual_filings",
    "edgar_10q": "sec_quarterly_filings",
    "synthetic": "synthetic_reference_documents",
}
print("volume:", VOLUME, "| index:", VS_INDEX)

# COMMAND ----------

# Extract and chunk. One row per ~1500-character window of a page (200 overlap), keyed by
# folder/file#page#chunk so citations can point at a page.
from pypdf import PdfReader

CHUNK, OVERLAP = 1500, 200
rows = []
for folder, source in SOURCES.items():
    folder_path = f"{VOLUME}/{folder}"
    if not os.path.isdir(folder_path):
        print(f"skip (not in volume): {folder}")
        continue
    files = sorted(f for f in os.listdir(folder_path) if f.lower().endswith(".pdf"))
    for file_name in files:
        try:
            reader = PdfReader(f"{folder_path}/{file_name}")
        except Exception as e:
            print(f"unreadable, skipped: {folder}/{file_name}: {e}")
            continue
        synthetic = folder == "synthetic" or "SYNTHETIC" in file_name
        for page_no, page in enumerate(reader.pages, start=1):
            text = " ".join((page.extract_text() or "").split())
            for k, start in enumerate(range(0, len(text), CHUNK - OVERLAP)):
                piece = text[start:start + CHUNK]
                if len(piece) < 50:
                    continue
                rows.append((f"{folder}/{file_name}#p{page_no}#c{k}", source,
                             f"{folder}/{file_name}", file_name, page_no, synthetic, piece))
    print(f"{folder}: {len(files)} files")

assert rows, f"No text extracted from {VOLUME} - did 00_tables_setup upload data/?"
chunks = spark.createDataFrame(
    rows,
    "chunk_id string, source string, path string, file_name string, page int, "
    "is_synthetic boolean, content string",
)
(chunks.write.mode("overwrite").option("overwriteSchema", "true")
 .option("delta.enableChangeDataFeed", "true").saveAsTable(CHUNKS_TABLE))
# Delta Sync indexes need change data feed on the source table.
spark.sql(f"ALTER TABLE {CHUNKS_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
print(f"✅ {len(rows):,} chunks written to {CHUNKS_TABLE}")

# COMMAND ----------

# Vector Search endpoint (Standard: low latency for interactive agent calls).
from databricks.sdk.service.vectorsearch import EndpointType

if VS_ENDPOINT not in [e.name for e in w.vector_search_endpoints.list_endpoints()]:
    w.vector_search_endpoints.create_endpoint(name=VS_ENDPOINT, endpoint_type=EndpointType.STANDARD)
    print(f"Creating endpoint {VS_ENDPOINT}...")

for _ in range(60):  # up to 30 min
    state = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT).endpoint_status.state.value
    if state == "ONLINE":
        break
    print(f"  endpoint {VS_ENDPOINT}: {state}")
    time.sleep(30)
else:
    raise TimeoutError(f"Vector Search endpoint {VS_ENDPOINT} not ONLINE after 30 min")
print(f"✅ Endpoint {VS_ENDPOINT} is ONLINE")

# COMMAND ----------

# Delta Sync index with managed embeddings. Created once; later runs re-sync it.
# Plain REST rather than the SDK's typed request classes: the SDK preinstalled on serverless
# is older and its EmbeddingSourceColumn lacks embedding_model_endpoint_name.
from databricks.sdk.errors import NotFound

try:
    w.vector_search_indexes.get_index(VS_INDEX)
    try:
        w.api_client.do("POST", f"/api/2.0/vector-search/indexes/{VS_INDEX}/sync")
        print(f"Index {VS_INDEX} exists - sync triggered")
    except Exception as e:  # a sync already running is fine
        print(f"Index {VS_INDEX} exists - sync not triggered: {e}")
except NotFound:
    w.api_client.do("POST", "/api/2.0/vector-search/indexes", body={
        "name": VS_INDEX,
        "endpoint_name": VS_ENDPOINT,
        "primary_key": "chunk_id",
        "index_type": "DELTA_SYNC",
        "delta_sync_index_spec": {
            "source_table": CHUNKS_TABLE,
            "pipeline_type": "TRIGGERED",
            "embedding_source_columns": [
                {"name": "content", "embedding_model_endpoint_name": EMBEDDING_MODEL}
            ],
        },
    })
    print(f"Creating index {VS_INDEX}...")

for _ in range(120):  # up to 60 min; embedding ~12k pages takes a while
    status = w.vector_search_indexes.get_index(VS_INDEX).status
    if status and status.ready and (status.indexed_row_count or 0) > 0:
        break
    print(f"  index: ready={status.ready if status else None} "
          f"rows={status.indexed_row_count if status else None} {status.message if status else ''}")
    time.sleep(30)
else:
    raise TimeoutError(f"Index {VS_INDEX} not ready after 60 min")
print(f"✅ Index ready: {status.indexed_row_count:,} rows")

# COMMAND ----------

# The supervisor's document tool. Returns the top passages as one string (like the GraphRAG
# functions), each headed with its file and page so the answer can cite it. Synthetic passages
# are labelled in the text itself, so the label survives whatever the model quotes.
spark.sql(f"""
CREATE OR REPLACE FUNCTION {SEARCH_FN}(
  query STRING COMMENT 'What to look for, e.g. "Ford supply chain risk factors" or "NVIDIA data center revenue guidance"'
)
RETURNS STRING
COMMENT 'Searches the financial document corpus - 10-K/10-Q filings (Mag7 and SEC EDGAR filings for Ford, Toyota, Honda, Pfizer, Merck, Amgen, Regeneron, Dow, Deere, Rockwell, United, Southwest, J.B. Hunt, S&P Global, Slide, Ryan Specialty, Hinge Health), earnings releases, earnings call transcripts and annual reports - and returns the most relevant passages. Each passage starts with [file p.N]; cite it. Passages marked SYNTHETIC come from generated reference documents for organisations that publish no filing (FordDirect, Addepar, UCLA Health, Providence, Summa Health, Henkel, Munich Re, Nationwide): the business description is realistic but every figure is invented, and the answer must say so.'
RETURN (
  SELECT concat_ws('\\n\\n---\\n\\n', collect_list(
    concat('[', path, ' p.', CAST(page AS STRING),
           CASE WHEN is_synthetic THEN ' | SYNTHETIC - illustrative, figures invented' ELSE '' END,
           ']\\n', content)))
  FROM vector_search(index => '{VS_INDEX}', query_text => query, num_results => 6)
)
""")
print(f"✅ Created {SEARCH_FN}")

# COMMAND ----------

# Smoke tests: a real filing and a synthetic document both come back, and the synthetic one is
# labelled. If the second check fails, the watermark has been lost somewhere between the PDF and
# the passage the supervisor reads.
real = spark.sql(f"SELECT {SEARCH_FN}('Ford risk factors supply chain') AS r").first().r or ""
print(real[:800])
assert "[" in real and "p." in real, "search_filings returned no passages"

synthetic = spark.sql(f"SELECT {SEARCH_FN}('Addepar annual review platform clients') AS r").first().r or ""
assert "SYNTHETIC" in synthetic, "synthetic passages are not labelled"
print("\n✅ search_filings returns cited passages, and synthetic ones are labelled")
