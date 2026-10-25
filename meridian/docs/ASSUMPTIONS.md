# Assumptions — Meridian

Recorded decisions where the spec was ambiguous or the workspace differed. Dated 2026-10-24.

1. **Catalog/schema**: `fins.meridian` (user owns schemas in `fins`; `UC_CATALOG=fins`,
   `UC_SCHEMA=meridian` are env-configured, not hardcoded into queries — table FQNs are
   interpolated from config at query-render time).
2. **Warehouse**: only `demo` (`00a19186c27fa1de`) exists; bound as the `sql-warehouse`
   app resource. It's a 2X-Small that may be STOPPED — cold-start UX is designed for it.
3. **Tailwind v3** (not v4): stable PostCSS pipeline, better shadcn-style token mapping.
4. **shadcn/ui**: hand-rolled equivalent primitives on Radix (fewer deps, same patterns)
   rather than the full shadcn CLI scaffold.
5. **Mock mode**: `APP_MODE=mock` serves the same deterministic synthetic generator used
   by `scripts/seed_synthetic_data.py` — no committed datasets, identical data shape.
6. **Genie SSE**: Conversation API has no streaming; the backend polls and re-emits SSE.
   Agent-mode streaming API is Beta (preview enrollment) — documented upgrade path only.
7. **Space creation**: Genie space is created/updated by `scripts/create_genie_space.py`
   via the Genie API (space serialized config), not hand-built in the UI.
8. **Replay point-in-time**: direct query path clamps via `until=` in SQL (enforced);
   Genie as-of is best-effort prompt augmentation + client-side max-date check, as spec'd.
9. **Bar Replay trades**: session state only for v1; optional Delta persistence table is
   defined but writes ship disabled by default.
10. **Light theme**: implemented but dark ("Obsidian") is the reference target.
11. **Countdown to bar close**: intraday only; daily bars show no countdown (no session
    calendar in synthetic data).
12. **Earnings/dividend badges**: synthetic fundamentals supply earnings dates; dividend
    events generated for yield-paying synthetic symbols only.
13. **Deployments**: `scripts/deploy.sh` uses the bundle (`databricks.yml`) for resource
    wiring + `apps deploy` for source; UI screenshots/golden-path recording are produced
    via Playwright in CI/local, not on the cluster.
14. **PRs**: repo remote is `a0x8o/agent-bricks-fins-era` on GitHub; milestone commits land
    on `feat/meridian`. Pushing/PRs happen only with user's say-so (Devin git rules).
