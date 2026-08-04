# [EDIT FIRST] Catalog and schema where the workshop creates tables, functions,
# volumes, and registers Genie/agents. The instructor sets these to their workspace.
catalog = "alexxx"
schema = dbName = db = "era_research"
# Example (Brandon's FEVM working values):
# catalog = "serverless_stable_lsryzn_catalog"
# schema = dbName = db = "brandon_cowen"
table = "parsed_data"
volume_name = "raw_documents"
base_url = "https://github.com/databricks-industry-solutions/agent-bricks-fins-mag7"
sa_name = "Supervisor_Agent_ERA"

# Chatbot App Configuration
app_name = "agent-bricks-chatbot"
lakebase_instance_name = "agent-bricks-lakebase"
app_resource_suffix = "workshop"

# ──────────────────────────────────────────────────────────────────────────────
# Chatbot App "Pro" mode (OPTIONAL)
# ──────────────────────────────────────────────────────────────────────────────
# The chatbot app ships in two flavors, selected by `app_mode`:
#   "simple" (default) — the basic chat-only experience. Requires nothing below.
#   "pro"              — adds a dockable workspace panel with an interactive
#                        knowledge-graph view, a data explorer, an embedded Genie
#                        + AI/BI dashboard, and a richer "thinking" stream.
#
# Pro mode reads the optional resources below. Leave them as-is for simple mode.
# The deploy notebook (06b_deploy_chatbot_app_pro_OPTIONAL) injects these into the
# app as environment variables; they are all harmless no-ops in simple mode.
app_mode = "simple"  # "simple" | "pro"

# GraphRAG is exposed to the Supervisor as SQL Unity Catalog functions
# (get_company_summary, compare_companies) over the graphrag_* tables — NOT as an
# external MCP server. The MCP-on-Apps approach is unusable through the Agent Bricks
# MCP proxy on streaming requests (httpx ResponseNotRead; see ML-63338), whereas UC
# function tools register reliably. See 05b (creates the functions) and 04 (wires them).

# SQL warehouse the app uses to read graph/ticker tables (Statement Execution API).
# Required for the Graph + Data Explorer tabs in pro mode. Auto-discovered by the
# pro deploy notebook (06b) if left blank.
sql_warehouse_id = ""

# Published Genie space + AI/BI dashboard embedded in the Dashboard tab (pro mode).
# Left blank: the pro deploy notebook (06b) discovers the Genie space by name and an
# AI/BI dashboard by name. Override with an id or explicit *_embed_url to pin them.
genie_space_id = ""
genie_embed_url = ""       # optional explicit embed URL override
aibi_dashboard_id = ""     # AI/BI (Lakeview) dashboard id
aibi_embed_url = ""        # optional explicit embed URL override

# Catalog/schema holding the graph (graphrag_vertices/graphrag_edges) and
# ticker_data tables. Defaults to the project catalog/schema above.
graph_catalog = catalog
graph_schema = schema