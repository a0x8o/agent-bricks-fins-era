# Fix: Research Documents Materialization Failure

**Dashboard**: MAG7 Financial You.com Agent (`01f1a272be991a68b4b19433b856c87b`)
**Dataset**: Research Documents (`datasets/research_docs`)
**Date**: 2026-10-09
**Status**: RESOLVED

## Problem

The Research Documents dataset materialization was permanently stuck in **Failed** state on the published dashboard. The materialization panel showed:
- **Research Documents** — ⚠ Failed
- Last materialization: —
- Next refresh: —
- "Materialization creation failed. View the statement in Query History for more details."

Affected widgets on the Research Library page:
- "Total Documents Available" (counter) — showed materialization error instead of data
- "Documents by Source" (bar chart) — showed materialization error instead of data

## Root Cause

The dataset SQL query is a 6-table `UNION ALL` across:
- `alexxx.era_research.annual_reports_data` (6 rows)
- `alexxx.era_research.earning_transcripts_data` (25 rows)
- `alexxx.era_research.earning_releases_data` (70 rows)
- `alexxx.era_research.10k_data` (50 rows)
- `alexxx.era_research.10q_data` (152 rows)
- `alexxx.era_research.8k_data` (331 rows)

**Contributing factor**: Three table names (`10k_data`, `10q_data`, `8k_data`) start with digits and were not backtick-quoted. The materialization engine's SQL parser is stricter than the interactive query engine and requires backtick quoting for digit-prefixed identifiers.

**Primary cause**: Even after backtick-quoting the table names, the materialization continued to fail. The exact materialization engine error was not accessible (Query History link pointed to a missing/expired statement). The materialization engine may have additional restrictions on UNION ALL queries with string literal aliases, or a caching issue prevented the fix from taking effect.

## Fix Applied

### Step 1: Backtick-quote digit-prefixed table names
```sql
-- Before
FROM alexxx.era_research.10k_data
FROM alexxx.era_research.10q_data
FROM alexxx.era_research.8k_data

-- After
FROM alexxx.era_research.`10k_data`
FROM alexxx.era_research.`10q_data`
FROM alexxx.era_research.`8k_data`
```

### Step 2: Attempted materialization recovery
- Toggled materialization off → on to reset cached failure state
- Re-published dashboard with embedded credentials
- Triggered schedule run (run `615493554836105`) — completed with `TERMINATION_CODE_SUCCESS` but Research Documents materialization still showed Failed

### Step 3: Disabled materialization (final fix)
Since the dataset is only 634 rows (lightweight UNION ALL), materialization provides negligible performance benefit. Disabled `materializeOnPublish` for this dataset so widgets query live on the published dashboard.

```
editDataset(datasets/research_docs, materializeOnPublish=false)
```

Re-published dashboard → widgets now render correctly on the published page.

## Additional Fix: Schedule Page Selection

The daily 1:00 AM EDT schedule (`01f1c1b68f5c1fd788e0070d34f2de53`) was only emailing the first page (Market Overview). Updated `pageSelection` from `firstOnly` to `all` so all 4 pages are included in scheduled emails.

## Current State

| Dataset | Materialization | Status |
| --- | --- | --- |
| Earning Releases | Enabled | Succeeded |
| Research Documents | **Disabled** | N/A (live query) |
| Ticker Data | Enabled | Succeeded |
| Ticker Latest Date | Enabled | Succeeded |
| P/E Ratios Latest | Enabled | Succeeded |
| Agent Payload | Ineligible (calc fields) | N/A |

## Future Considerations

- If materialization is needed for this dataset in the future, investigate the exact error in Query History after a fresh materialization attempt
- Consider consolidating the 6 source tables into a single unified table (e.g., via a pipeline or materialized view) to simplify the query
- The backtick fix should remain even with materialization disabled, as it's correct SQL practice for digit-prefixed identifiers