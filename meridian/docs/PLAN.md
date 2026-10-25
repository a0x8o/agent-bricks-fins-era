# Meridian — Implementation Plan

A financial analysis workspace as a Databricks App: TradingView-grade dense charting UI +
a Genie panel whose answers (text + SQL + table + auto-chart) can be pinned to the workspace.

Target workspace: `dbc-8700f68c-68da.cloud.databricks.com` (profile `DEFAULT`).
Data location: `fins.meridian.*` (schema created, owned by deploying user).
Warehouse: `demo` (`00a19186c27fa1de`, 2X-Small serverless-class).
App name: `meridian`.

## Architecture

```
Browser (React/Vite SPA, dark-first "Obsidian")
   │  /api/*  — same origin, proxied by Apps runtime
   ▼
FastAPI (uvicorn, one process; serves /api/* + app/static SPA)
   ├── auth.py        OBO: x-forwarded-access-token → per-request user WorkspaceClient
   │                  SP:  Config() injected creds (only when AUTH_MODE=service_principal)
   ├── sql_exec.py    Statement Execution API, named parameters only, TTL cache
   ├── genie_client.py Conversation API via REST/SDK with the caller's identity
   ├── indicators.py  pure pandas/numpy indicators (unit-tested vs reference values)
   ├── chart_inference.py  result-schema → ranked chart specs (unit-tested rules)
   └── synthetic.py   deterministic seeded GBM generator — powers BOTH mock mode
                      and scripts/seed_synthetic_data.py (same data, two sinks)
```

Data path (charts/tables): parameterized SQL in `app/queries/*.sql` → Statement Execution
API → JSON. NL path: Genie Conversation API. The only Genie SQL the app re-executes is
"Refresh pinned insight" — SELECT-only guard, run as the user.

## API differences found vs spec (verified 2026-10-24)

- **Lightweight Charts v5.2.x**: native panes confirmed — `chart.addPane()`,
  `paneIndex` arg on `addSeries`, `IPaneApi.setStretchFactor/setHeight`,
  `layout.panes.{separatorColor,enableResize}`. Custom visuals (band fills, gradient
  glows, channel fills, event badges, replay cursor) implemented as `ISeriesPrimitive`
  plugins / custom series renderers, not DOM overlays. `takeScreenshot()` exists for the
  snapshot button. Apache-2.0; attribution kept in `NOTICE` + docs.
- **Genie**: Conversation API confirmed (`POST /api/2.0/genie/spaces/{id}/start-conversation`,
  `POST .../conversations/{cid}/messages`, `GET .../messages/{mid}`,
  `GET .../messages/{mid}/attachments/{aid}/query-result`). Statuses:
  `SUBMITTED → FILTERING_CONTEXT → ASKING_AI → EXECUTING_QUERY → COMPLETED/FAILED/CANCELLED`.
  Attachments carry `text.content`, `query.{query,description}`, `suggested_questions`.
  There is **no native SSE** on the Conversation API — the `/stream` endpoint polls
  server-side and re-emits transitions as SSE (behind `FEATURE_STREAMING`).
  The OpenAI-compatible **Agent mode** (`/genie/agents/{id}`, true streaming) exists but is
  Beta behind preview enrollment — not used; noted as upgrade path.
- **Suggested follow-ups**: present in attachments as `suggested_questions` when the
  space produces them; UI degrades to no chips (documented fallback).
- **Apps deploy**: `apps create` → `workspace import-dir --overwrite` →
  `apps deploy --source-code-path`. App resources + `user_api_scopes` declared in
  `databricks.yml` (bundle) so the SP grant wiring is repeatable; `scripts/deploy.sh`
  wraps the flow.
- **Statement Execution API**: supports named `parameters` — used for every query.
  `:identifier` placeholders are *values only*; table/column identifiers come from an
  allowlist in code (spec's "allowlist identifiers" rule).

## Data contracts

- `GET /api/prices` → `{symbol, interval, bars:[{time,open,high,low,close,adj_close,volume}], as_of, cache}`; `until=` clamps at replay cursor.
- `GET /api/quote` → `{symbol, last, change, change_pct, perf:{w1,m1,m3,m6,ytd,y1}, technicals:{score,label}, market_status}`.
- Genie answer → `{message_id,status,text,sql,query_description,result:{columns,rows,row_count,truncated},suggested[],attachments:[{id,kind}]}`.
- Errors everywhere: `{error:{code,message,request_id,retryable}}`.

## Component tree (frontend)

```
AppShell (Zustand layout store, react-resizable-panels)
├─ TopBar (search ⌘K, interval, chart type, indicators, layout picker, replay, theme, user)
├─ DrawingRail (left)          RightRail (utility icons)
├─ ChartGrid {1|2h|2v|3|4 panes}
│   └─ ChartPane: LWC candles/line/area/HA + volume + overlay MAs + ≤2 oscillator sub-panes
│        ├─ LegendRows · AxisTags · EventBadges · RangeBar
│        └─ ReplayBar (when replay active)
├─ WatchlistPanel (grouped, sparkline on hover, flash-on-change)
├─ SymbolCard (price, perf grid, technicals gauge via ECharts)
├─ GeniePanel (header/context chip, StatusTimeline, AnswerCard list, Composer)
└─ BottomDock tabs: Screener (TanStack Table+Virtual) · Fundamentals · Portfolio ·
   Heatmap (ECharts treemap) · PinnedInsights
```

## Risks

1. **Warehouse `demo` is STOPPED** — first queries cold-start (~10–30s). Mitigation:
   health check reports it; UI shows "warehouse warming up"; warmup ping on app start.
2. **OBO availability** — user auth is GA/on-by-default, but `user_api_scopes` for
   `sql` + `dashboards.genie` must be granted at app config; fallback banner + SP mode.
3. **Genie latency** — 30–120s typical; status timeline + honest elapsed time.
4. **Spec breadth vs. reality** — v1 scope risk is charting detail (drawings, replay).
   Mitigation: primitives layer isolated in `charts/plugins/`, feature-flagged.
5. **Workspace import-dir skips nothing** — `.databricksignore` + deploy script excludes
   node_modules/build artifacts; 10 MB file cap checked in platform-check.
6. **Nested bundle** — `meridian/databricks.yml` is its own bundle root (sibling to the
   repo's root bundle); run bundle commands from `meridian/`.

## Milestones

Per spec: M1 skeleton+deploy → M2 data → M3 workspace → M4 Genie → M5 dock →
M5b pro charting → M6 hardening. One commit per milestone on `feat/meridian`.
