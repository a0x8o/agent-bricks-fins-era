# Agent Bricks Workshop - Feedback & Issues

> **Historical.** Tim Lortz, Slack, March 12–17 2026 (`agent-bricks-fins-mag7`).
>
> Status as of August 2026: issues **2–3 and 5–10 are fixed in code**. Issue **1**
> leftover was a stale root `tables_setup.ipynb` and a Readme path into
> `resources/` — both corrected; the live notebook is
> `setup_instructor/00_tables_setup.ipynb`. Issue **4** leftover was unquoted
> identifiers in 05b smoke tests — those statements now use backticks. Do not
> re-implement the original punch list.

---

## Issue 1: `tables_setup.ipynb` Not Documented as a Required Step

**Severity:** Documentation / Setup blocker
**Affected files:** `README.md`, `tables_setup.ipynb`

**Problem:** The `tables_setup.ipynb` notebook is a required prerequisite before running any of the `setup_instructor/` notebooks, but it is not documented in the README. Users encounter errors (missing schema, missing volumes) because they skip this step.

**Additional problems with `tables_setup.ipynb`:**
- It is in the repo root, but the README references a `resources/` folder for setup materials
- It imports as a `.py` file rather than rendering as a notebook

**Fix:**
1. Update the `README.md` to clearly list `tables_setup.ipynb` as **Step 1** before any instructor setup notebooks are run.
2. Move `tables_setup.ipynb` into the `setup_instructor/` folder (or rename it to `00_tables_setup.ipynb` in `setup_instructor/` to make ordering obvious).
3. Ensure the notebook metadata marks it as a notebook (`.ipynb` format), not a `.py` import.

---

## Issue 2: Schema and Volume Must Be Pre-Created

**Severity:** Setup blocker
**Affected files:** `config.py`, `tables_setup.ipynb`, `resources/data_setup_functions.py`

**Problem:** If the schema or the `raw_documents` volume specified in `config.py` does not already exist, the setup notebooks fail. There is no automated creation of these prerequisites.

**Fix:**
1. In `tables_setup.ipynb` (or a shared setup utility), add idempotent `CREATE SCHEMA IF NOT EXISTS` and `CREATE VOLUME IF NOT EXISTS` statements that run before any other operations.
2. Derive the schema and volume names from `config.py` so there is a single source of truth.

---

## Issue 3: KA Agent Setup Fails with "Directory Not Found"

**Severity:** Bug
**Affected file:** `setup_instructor/01_instructor_setup_ka.ipynb` (Cell/Command 7)

**Problem:** Running the KA agent setup cell produces:
```
ERROR:__main__:API Error: POST /api/2.0/knowledge-assistants failed: The directory being accessed is not found.
```

**Root cause:** The KA setup attempts to access a directory (likely for document ingestion) that hasn't been created yet. This is a downstream effect of Issue 2 — the volume/directory must exist before the KA agent can be configured.

**Fix:**
1. Ensure the `tables_setup.ipynb` creates all required volumes and directories before the KA notebook runs.
2. Add a pre-flight check at the top of `01_instructor_setup_ka.ipynb` that validates the required directories exist and provides a clear error message pointing the user to run `tables_setup.ipynb` first.

---

## Issue 4: SQL Identifier Error with Hyphens in Schema Names

**Severity:** Bug
**Affected files:** Any file that constructs SQL using schema/catalog names from `config.py`

**Problem:** If a user sets a schema name containing hyphens (e.g., `agent-bricks-fins-mag7`), SQL statements fail:
```
[INVALID_IDENTIFIER] The unquoted identifier agent-bricks-fins-mag7 is invalid
and must be back quoted as: `agent-bricks-fins-mag7`.
```

**Fix:**
1. In all SQL statements that reference catalog, schema, or table names from config, wrap identifiers with backticks. For example:
   - Change: `CREATE SCHEMA {schema_name}`
   - To: `` CREATE SCHEMA `{schema_name}` ``
2. Alternatively, add validation in `config.py` that warns or sanitizes names containing special characters (hyphens, spaces, etc.).

---

## Issue 5: Genie Setup Only Records First Text Instruction

**Severity:** Bug
**Affected file:** `setup_instructor/02_instructor_setup_genie.ipynb`

**Problem:** When running the Genie setup, only the first text instruction is recorded out of multiple defined instructions. The remaining instructions are silently dropped.

**Fix:**
1. Review the Genie text instruction registration logic. Ensure it iterates over ALL instructions and submits each one, not just the first element.
2. Add logging to confirm how many instructions were successfully registered.

---

## Issue 6: SQL Examples Key Mismatch in Genie Setup (CRITICAL)

**Severity:** Bug — key mismatch causes `KeyError`
**Affected file:** `setup_instructor/02_instructor_setup_genie.ipynb` (Cell 8), `resources/brick_setup_functions.py`

**Problem:** SQL examples are not registered in Genie. The notebook passes dictionaries with keys `{"description": "...", "sql": "..."}`, but `genie_add_sql_instructions_batch()` expects keys `{"title": "...", "content": "..."}`. This causes a `KeyError: 'title'`.

**Fix:**
1. In `setup_instructor/02_instructor_setup_genie.ipynb` (Cell 8), change the SQL example dictionaries:
   - Rename key `"description"` to `"title"`
   - Rename key `"sql"` to `"content"`
2. Alternatively, update `genie_add_sql_instructions_batch()` in `resources/brick_setup_functions.py` to accept both key formats for backwards compatibility. But the preferred fix is aligning the notebook to match the function's expected interface.

---

## Issue 7: Sample Conversations Defined But Never Added to SA

**Severity:** Bug
**Affected file:** `setup_instructor/04_instructor_setup_sa.ipynb`

**Problem:** The Supervisor Agent setup notebook defines sample conversations but never actually sends them to the API. They exist in code but are dead code — the conversations never get registered.

**Fix:**
1. After defining sample conversations, add an API call to register them with the Supervisor Agent. Use the MAS API endpoint to add sample conversations.
2. If the API for adding sample conversations is unstable or unavailable, add a clear comment explaining the limitation and instruct users to add them manually through the UI.

---

## Issue 8: `app_full_name` Defined in Three Separate Places

**Severity:** Code quality / Bug
**Affected file:** `setup_instructor/06_deploy_chatbot_app.ipynb`

**Problem:** `app_full_name` is constructed in three separate places in the notebook. The 30-character maximum for Databricks app names causes issues — when the suffix is removed to fit the limit, it can leave a trailing hyphen, which also errors out.

**Fix:**
1. Define `app_full_name` exactly once near the top of the notebook (or derive it from `config.py`).
2. Add logic to handle the 30-character limit cleanly: truncate, then strip any trailing hyphens or special characters.
   ```python
   app_full_name = f"{prefix}-{suffix}"[:30].rstrip("-")
   ```
3. Remove all duplicate definitions of `app_full_name` throughout the notebook.

---

## Issue 9: App Deployment Breaks with Non-Default Git Repo Path

**Severity:** Bug
**Affected file:** `setup_instructor/06_deploy_chatbot_app.ipynb`

**Problem:** The app deployment hardcodes the expected path to the git repo. If a user clones the repo to a different workspace path, the deployment fails.

**Fix:**
Replace the hardcoded path with dynamic path resolution:
```python
notebook_dir = os.path.dirname(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
)
repo_root = os.path.dirname(notebook_dir)
app_source_path = f"/Workspace{repo_root}/chatbot-app"
```

---

## Issue 10: SA Endpoint Lookup Returns Wrong Endpoint

**Severity:** Bug
**Affected file:** `setup_instructor/06_deploy_chatbot_app.ipynb`

**Problem:** The Supervisor Agent endpoint lookup function claims to find the correct endpoint (e.g., `Supervisor_Agent_Mag7`) but actually grabs a different SA endpoint ID. This causes the app to connect to the wrong agent.

**Fix:**
Replace the endpoint lookup logic with a more robust implementation that filters by MAS tile type and validates the match. Tim provided a working patched version:

1. Use the `/api/2.0/tiles` endpoint with a filter for `tile_type=MAS` and the SA name.
2. Extract the endpoint name from the MAS response, checking multiple possible field locations (`endpoint_name`, `status.endpoint_name`, `tile.endpoint_name`).
3. If not found in the MAS response, fall back to searching serving endpoints by expected naming pattern (`mas-{tile_id[:8]}-endpoint`).
4. Add clear error messaging if no matching endpoint is found, listing available endpoints for manual selection.

---

## Summary

| # | Issue | File(s) | Severity |
|---|-------|---------|----------|
| 1 | `tables_setup.ipynb` not documented | `README.md` | Doc |
| 2 | Schema/volume not auto-created | `config.py`, `tables_setup.ipynb` | Setup |
| 3 | KA setup "directory not found" | `01_instructor_setup_ka.ipynb` | Bug |
| 4 | Hyphens in SQL identifiers | All SQL-generating files | Bug |
| 5 | Only first Genie instruction saved | `02_instructor_setup_genie.ipynb` | Bug |
| 6 | Key mismatch (`description`/`sql` vs `title`/`content`) | `02_instructor_setup_genie.ipynb`, `brick_setup_functions.py` | Bug |
| 7 | Sample conversations never added | `04_instructor_setup_sa.ipynb` | Bug |
| 8 | `app_full_name` defined 3x + char limit | `06_deploy_chatbot_app.ipynb` | Bug |
| 9 | Hardcoded repo path breaks deployment | `06_deploy_chatbot_app.ipynb` | Bug |
| 10 | SA endpoint lookup grabs wrong endpoint | `06_deploy_chatbot_app.ipynb` | Bug |
