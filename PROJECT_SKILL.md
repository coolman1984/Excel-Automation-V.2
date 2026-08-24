# Read this first — V14 adaptation agent

You received a reusable Excel automation product. **Do not rebuild it.** Adapt only the smallest
business-owned surface needed for the new Excel files and business logic.

## Operating order

```text
reuse existing capability
→ project.json mappings/configuration
→ project-owned SQL
→ isolated project-owned Python only when SQL is unsuitable
→ shared-engine change only after a reusable gap is proven
```

For an ordinary adaptation, shared-engine changes should be zero.

## Read in this order

1. `.ai/CURRENT_STATE.md`
2. `.ai/PROJECT_MAP.md`
3. `.ai/CONTEXT_PACK.md`
4. `projects/example_sales/project.json`
5. only files routed by the map for the task

Do not mass-read the repository.

## Business discovery

Use `.ai/BUSINESS_QUESTIONS.md`. Confirm only business meaning: source role, row meaning, key,
corrections, disappearance behavior, relationships, control totals, KPIs, exceptions, decisions,
and frequency. Never invent a missing business rule. Mark it `PENDING_APPROVAL`.

## Create and configure

```bash
python PROJECT_TOOL.py new-project <Name>
python PROJECT_TOOL.py doctor --project projects/<Name>
```

Normally edit:

- `projects/<Name>/project.json`
- `projects/<Name>/sql/metrics.sql`
- `projects/<Name>/sql/fact.sql`

The reusable engine already provides protected Excel COM, direct Excel extraction, DuckDB/local
warehouse, four history modes, reconciliation, insights, dashboard generation, state tracking,
optional SQL Server synchronization, web UI, offline HTML, recovery, packaging, and verification.

## Important project settings

- `database.backend`: production template uses `duckdb`.
- `sources[].extraction.mode`: `auto`, `direct`, or `excel_com`.
- `sources[].update_mode`: `APPEND`, `UPSERT`, `SNAPSHOT`, or `REPLACE_PERIOD`.
- `sources[].period_field`: required for `REPLACE_PERIOD`.
- `sql_server.enabled`: optional; local trusted processing remains authoritative.

Use `excel_com` when a protected corporate workbook requires the authorized Excel desktop session.
Never bypass that route merely because direct parsing is easier.

## Canonical run state

```text
DETECTED → OPENING → EXTRACTING → VALIDATING → LOADING → MERGING → CALCULATING
→ GENERATING_JSON → GENERATING_DASHBOARD → VERIFYING → COMPLETE
```

`FAILED` is the failure-only terminal state. A failed run must preserve the last-good output.

## Proof while adapting

```bash
python PROJECT_TOOL.py run --project projects/<Name> --inbox <representative-files> --verbose
python PROJECT_TOOL.py test --quick
```

Before delivery:

```bash
python PROJECT_TOOL.py test
python PROJECT_TOOL.py deliver --project projects/<Name> --output-dir release \
       --runtime runtime_inputs/python-windows
```

Delivery is not complete unless `RESULT: PASS`. The verifier blocks missing private Python,
DuckDB when required, `pywin32` when COM is required, and `pyodbc` when SQL Server is enabled.
The final user must install nothing and need no internet, terminal, Git, Python, Node, or admin rights.

## Non-negotiable rules

- Source workbooks remain unchanged and are opened read-only.
- Read large ranges, not cell-by-cell loops.
- Trusted calculations are deterministic and authoritative once.
- Browser code presents approved data; it does not create a second KPI formula.
- AI may explain verified results but may not calculate trusted KPIs or invent root causes.
- Local trusted publication must succeed before SQL Server synchronization starts.
- Runtime internet/CDNs are forbidden.
- Never hand the final user anything except the verified `<Name>.zip`.
