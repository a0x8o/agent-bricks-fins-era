# Meridian architecture

React SPA (Vite, static) → FastAPI → {SQL Statement Execution API, Genie
Conversation API} → Unity Catalog (`fins.meridian.*`).

- Identity: OBO user token per request (`x-forwarded-access-token`) →
  `user_workspace_client()`; service principal only for app-internal writes
  (audit) or AUTH_MODE=service_principal (visible banner).
- Reads: `app/queries/*.sql` named-parameter queries via Statement Execution.
- NL: Genie Conversation API → normalized answer (text, SQL, result, suggestions)
  → chart inference rules → answer card. SSE endpoint polls and re-emits status.
- Mock: `APP_MODE=mock` → `services/synthetic.py` (same generator the seed
  script writes to UC). Identical data shape either way.
- Point-in-time: `until=` param clamps every data path for Bar Replay.
