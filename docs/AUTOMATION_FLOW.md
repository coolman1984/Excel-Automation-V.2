# Automation flow — V13

This is the recurring flow after a project has already been adapted and approved.

| Step | Runtime behavior | Implementation |
|---:|---|---|
| 1 | New source is detected or selected | local upload / configured intake / watched folder |
| 2 | Source/report identity is resolved | configured source matching + source manifest |
| 3 | File stability/identity is confirmed | fingerprint/hash and duplicate-run protection |
| 4 | Protected workbook opens in authorized Excel session when required | `engine/excel/com_reader.py` |
| 5 | Required worksheet/range and headers are discovered | direct reader or COM adapter |
| 6 | Data is read in large blocks | configurable block/chunk extraction |
| 7 | Raw values + lineage are staged locally | DuckDB production backend; SQLite dev fallback |
| 8 | Structure and quality are checked | schema, types, rules, quarantine, controls |
| 9 | Clean data is standardized | typed canonical project fields |
| 10 | History is resolved | APPEND / UPSERT / SNAPSHOT / REPLACE_PERIOD |
| 11 | Trusted calculations run | deterministic project SQL / approved isolated Python |
| 12 | Meaningful changes are detected | configured + generic evidence-backed insights |
| 13 | Dashboard datasets are built | reconciled pre-aggregated analytical cube |
| 14 | Compact dashboard JSON is generated | trusted report contract |
| 15 | `dashboard.html` is generated | self-contained local HTML/CSS/JS |
| 16 | Numerical/structural/offline checks run | reconciliation + standalone verifier |
| 17 | Trusted result publishes atomically | last-good remains safe on failure |
| 18 | SQL Server synchronizes when enabled | post-local-success mirror; outage becomes PENDING |
| 19 | Run finishes with lineage and state `COMPLETE` | state file, logs, archive, sync evidence |

## Persisted run state

```text
DETECTED
→ OPENING
→ EXTRACTING
→ VALIDATING
→ LOADING
→ MERGING
→ CALCULATING
→ GENERATING_JSON
→ GENERATING_DASHBOARD
→ VERIFYING
→ COMPLETE
```

A failed run uses `FAILED` and never overwrites trusted history or the last-good dashboard.

## Extraction choice

`direct` reads normal `.xlsx` files without Excel automation. `excel_com` uses Microsoft Excel
desktop under the logged-in authorized Windows user and is intended for protected corporate
workbooks. `auto` uses the normal route and can fall back to COM when available.

COM opens read-only, disables update links, reads rectangular `Value2` blocks, and closes the
workbook/Excel instance without saving changes.

## Database choice

Production template projects use DuckDB. SQLite remains only as a compatibility backend for source
unit tests or environments where the DuckDB binary is not present. A package configured explicitly
for DuckDB is rejected if its private runtime lacks DuckDB.

## History choice

- `APPEND`: existing business keys are immutable; conflicting changes are quarantined.
- `UPSERT`: insert new keys and version approved corrections; missing old rows stay active.
- `SNAPSHOT`: UPSERT plus records missing from the complete new snapshot are closed.
- `REPLACE_PERIOD`: replace only periods represented by the incoming run; other periods remain.

## SQL Server boundary

SQL Server is optional and never the calculation authority. The application first completes and
publishes a locally trusted run. Synchronization then mirrors active trusted records transactionally.
If credentials, driver, network, or server are unavailable, synchronization becomes `PENDING`; the
local trusted run remains usable and Excel is not re-extracted merely to retry synchronization.

## Dashboard boundary

The processing layer owns trusted formulas. The browser owns presentation: filters, chart rendering,
search, sort, drill/context, export, print, themes and language. Automatic insights quote verified
changes and contributors but do not invent root cause.
