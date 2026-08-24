# Current state — V14

**Date:** 2026-08-23  
**Engine:** 14.0.0  
**Authority:** the final adaptation contract supplied with V12, implemented in V13 and reliability/decision-UX hardened in V14.

This file separates code-complete capability from environment-proven capability. Never turn a
conditional proof into a marketing claim.

## Verified in this environment

| Proof | Result |
|---|---|
| Full automated suite | **159 tests passing, 1 browser-navigation test skipped by environment** |
| Example end-to-end run | PASS/WARNING behavior as designed; reconciled trusted metrics |
| Exact persisted run-state sequence | PASS through `COMPLETE` |
| APPEND / UPSERT / SNAPSHOT / REPLACE_PERIOD history contracts | PASS in automated tests |
| Identical rerun / corrections / rollback / last-good preservation | PASS |
| Population and trusted control reconciliation | PASS |
| Automatic evidence-backed insights | PASS |
| Compact dashboard JSON generation | PASS |
| Automatic self-contained `dashboard.html` generation + structural/offline verification | PASS |
| Modern dashboard responsive layout | Manually rendered in Chromium at 1440/900/420 px; no horizontal overflow or page errors |
| English / Arabic / RTL / dark mode | PASS in rendered QA |
| Package shape and private-runtime gate | PASS |
| Missing DuckDB in a DuckDB-required package is blocked | PASS |
| Missing pywin32 in a COM-required package is blocked | PASS |
| Missing pyodbc in SQL-Server-enabled package is blocked | PASS |
| SQL Server unavailable/missing credentials leaves local trusted result available as PENDING | PASS in contract tests |

## Code-complete but target-environment proof is still required

| Capability | Implementation | Remaining proof before broad end-user claim |
|---|---|---|
| DuckDB production backend | implemented in `engine/db/database.py` | bundle actual Windows DuckDB binary in private runtime and run full target package |
| Excel COM protected workbook route | implemented in `engine/excel/com_reader.py` | run against a real protected corporate workbook in the authorized Windows/Excel session |
| SQL Server synchronization | implemented in `engine/sync/sql_server.py` | run with approved `pyodbc`, ODBC driver, credentials, and actual target SQL Server if enabled |
| Non-technical operator handoff | workflow implemented | two real runs and one recovery by a representative end user |

DuckDB is not installed in this Linux execution environment, so the regression suite used the
SQLite compatibility backend. That is a development fallback, not a claim that the DuckDB runtime
has already been environment-proven.

## Canonical run states

```text
DETECTED
OPENING
EXTRACTING
VALIDATING
LOADING
MERGING
CALCULATING
GENERATING_JSON
GENERATING_DASHBOARD
VERIFYING
COMPLETE
```

`FAILED` is used only when a run terminates unsuccessfully. State is persisted atomically in the
run workspace.

## Product boundary

The reusable engine is ready for adaptation work. A **specific employee package** is production-
qualified only after its own project configuration, representative data, private Windows runtime,
protected-file requirement (if any), SQL Server requirement (if any), and operator acceptance gates
pass on the target environment.
