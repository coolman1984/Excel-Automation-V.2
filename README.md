# Ultimate Excel Automation V14 — reusable master template

A reusable offline Excel-to-dashboard product that an adaptation agent configures for one
business case and returns as one operator ZIP. The engine is built once; the business meaning
changes per project.

```text
Template ZIP + representative Excel files + plain business explanation
        ↓
AI adaptation agent: reuse → configure → add minimal project SQL/Python → prove
        ↓
ProjectName.zip
        ↓
extract → double-click START → add/select Excel → Process → use trusted dashboard
```

**Agent: read `PROJECT_SKILL.md` first.**  
**Business user: read `docs/FOR_THE_BUSINESS_USER.md`.**

## Canonical recurring run

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

On a successful run the application detects/selects the source, opens protected workbooks
through authorized Excel COM when configured, extracts large blocks, validates and stages data,
updates trusted history, calculates deterministic KPIs, creates evidence-backed insights,
generates compact dashboard JSON plus a self-contained `dashboard.html`, verifies both, publishes
atomically, and optionally synchronizes the locally trusted result to SQL Server.

A failed run never replaces the last-good trusted result.

## What is reusable

- direct `.xlsx` / `.csv` extraction plus Windows Excel COM for protected workbooks;
- configurable large-block extraction and lineage;
- DuckDB production backend with a SQLite development/test fallback;
- `APPEND`, `UPSERT`, `SNAPSHOT`, and `REPLACE_PERIOD` history modes;
- quality checks, quarantine, population reconciliation, and trusted controls;
- deterministic SQL metrics and isolated project Python only when justified;
- evidence-backed automatic insights without invented root causes;
- optional SQL Server synchronization after local success;
- modern one-page dashboard with KPI cards, decision signals, charts, filters, search, tables,
  quality evidence, run history, CSV export, print, English/Arabic, RTL, light/dark mode, and a
  self-contained offline HTML report;
- persisted run state and lineage;
- one-click private Windows operator package with dependency verification.

## Two packages

| Package | User | Contents |
|---|---|---|
| `Project-Template.zip` | adaptation agent | engine, tests, docs, example, project template, tools |
| `ProjectName.zip` | final business user | `START.bat`, `QUICK_START.html`, `Application/` only |

## Agent commands

```bash
python PROJECT_TOOL.py new-project AcmeSales
python PROJECT_TOOL.py doctor --project projects/AcmeSales
python PROJECT_TOOL.py run --project projects/AcmeSales --inbox ./files --verbose
python PROJECT_TOOL.py test --quick
python PROJECT_TOOL.py test
python PROJECT_TOOL.py deliver --project projects/AcmeSales --output-dir release \
       --runtime runtime_inputs/python-windows
```

The delivery verifier refuses a project that requires DuckDB, Excel COM, or SQL Server but does
not carry the corresponding runtime dependency. The final operator never installs packages.

## Database rule

Production project templates default to `database.backend = duckdb`. The source repository can
fall back to SQLite only for development/testing where the DuckDB binary is not available. A
package explicitly configured for DuckDB fails its delivery gate if DuckDB is missing.

## Protected Excel rule

A source can use:

- `direct` — dependency-free `.xlsx` reader;
- `excel_com` — Windows Excel desktop in the logged-in authorized user session;
- `auto` — direct first, with COM available as the protected-workbook path.

The source workbook is opened read-only and never edited.

## Offline runtime

Offline means **no runtime download**, not “no dependencies”. The private Windows runtime must
contain all dependencies required by that project: DuckDB for production, `pywin32` when COM is
required, and `pyodbc` only when SQL Server synchronization is enabled. See
`runtime_inputs/README.md` and `docs/FINISH_ON_WINDOWS.md`.

## Repository map

| Path | Purpose |
|---|---|
| `PROJECT_SKILL.md` | agent operating instructions |
| `.ai/` | map, context, business questions, current verified state |
| `engine/` | reusable runtime |
| `projects/_template/` | starting project surface |
| `projects/example_sales/` | complete safe example |
| `tests/` | regression and acceptance proofs |
| `runtime_inputs/` | prepared private Windows runtime before final delivery |
| `tools/` | template ZIP builder and support tools |

## Evidence status

The implementation is code-complete for the reusable paths above, but Windows-only and enterprise
integrations still require proof in the actual target environment before a customer package may
claim them as environment-proven. Exact evidence is kept in `.ai/CURRENT_STATE.md`.
