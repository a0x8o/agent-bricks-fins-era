# Dashboard Datasets — MAG7 Financial You.com Agent

Dataset SQL definitions for dashboard `01f1a272be991a68b4b19433b856c87b`.
These are the source-of-truth queries deployed to the published dashboard.

## Files

| File | Dataset Ref | Page(s) | Materialization |
| --- | --- | --- | --- |
| `research_docs.sql` | `datasets/research_docs` | Research Library | **DISABLED** (see fix below) |
| `earning_releases.sql` | `datasets/earning_releases` | Research Library | Enabled |
| `ticker_data.sql` | `datasets/ticker_data` | Market Overview, Valuation Metrics | Enabled |
| `ticker_latest.sql` | `datasets/ticker_latest` | Market Overview, Valuation Metrics | Enabled |
| `egress_audit.sql` | `datasets/egress_audit` | Agent Operations | Ineligible (calc fields) |
| `pe_ratios.sql` | `datasets/pe_ratios` | Valuation Metrics | Enabled |

## Schedule

- **Cron**: `0 0 1 * * ?` (daily at 1:00 AM EDT)
- **Schedule ID**: `01f1c1b68f5c1fd788e0070d34f2de53`
- **Page selection**: `all` (all 4 pages emailed)
- **Credentials**: Run as owner (embedded)
- **Compute**: `agent-bricks-demos` warehouse

## Fix Log

### 2026-10-09: Research Documents materialization failure

**Problem**: `research_docs` dataset materialization permanently stuck in Failed state.
Widgets "Total Documents Available" and "Documents by Source" showed error on published page.

**Root cause**: Table names `10k_data`, `10q_data`, `8k_data` start with digits and were
not backtick-quoted. The materialization engine's SQL parser is stricter than the
interactive engine. Even after quoting, materialization engine continued to fail.

**Fixes applied**:
1. Backtick-quoted all digit-prefixed table names in `research_docs.sql`
2. Disabled `materializeOnPublish` for `research_docs` (634 rows, live query is fine)
3. Updated schedule `pageSelection` from `firstOnly` to `all`

See `docs/fix_research_docs_materialization.md` for full details.