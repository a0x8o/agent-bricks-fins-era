# Meridian runbook

## Prereqs
Databricks CLI profile (default `DEFAULT`), Python 3.11+, Node 22+.

## First-time setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_synthetic_data.py          # creates + seeds fins.meridian.*
python scripts/create_genie_space.py           # prints GENIE_SPACE_ID
# set var.genie_space_id in databricks.yml to that value
npm --prefix frontend install
./scripts/deploy.sh                            # builds, uploads, creates+deploys app
```

## Grants
- App SP: `CAN_USE` on the sql-warehouse resource, `CAN_RUN` on the genie-space
  resource (declared in databricks.yml — bundle grants them at deploy).
- Users (OBO): `USE CATALOG fins`, `USE SCHEMA fins.meridian`, `SELECT` on the
  tables/views. OBO requires the app's `user_api_scopes` (sql, dashboards.genie).

## Config — never hardcode
`app.yaml` env: DATABRICKS_WAREHOUSE_ID (valueFrom sql-warehouse),
GENIE_SPACE_ID (valueFrom genie-space), UC_CATALOG/UC_SCHEMA, AUTH_MODE
(obo default; service_principal shows a banner), FEATURE_STREAMING,
FEATURE_PERSISTENCE.

## Common errors
| Symptom | Fix |
|---|---|
| 403 on queries | user lacks SELECT on fins.meridian, or OBO scopes not granted |
| Warehouse STOPPED banner | first query cold-starts; it clears when RUNNING |
| Genie "Narrative only" | space returned no query attachment — check space config |
| App 502 at startup | `databricks apps logs meridian` — usually missing dep or port |
| Old UI after deploy | import-dir needs `--overwrite` (deploy.sh does) |

## Pointing at real data
Replace the tables in UC_CATALOG.UC_SCHEMA with conforming real tables and set
APP_MODE=live (default). The synthetic generator is only a seed/mock source.
