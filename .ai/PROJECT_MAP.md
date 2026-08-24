# Project map — V14

Read this map before opening engine files. Read every file you edit and the affected test/contract.

| Path | Responsibility / when to read |
|---|---|
| `PROJECT_SKILL.md` | adaptation operating rules; read first |
| `.ai/CURRENT_STATE.md` | proven vs conditional capability; read first |
| `.ai/CONTEXT_PACK.md` | compact architecture and adaptation surface |
| `.ai/BUSINESS_QUESTIONS.md` | business-only discovery questions |
| `projects/_template/project.json` | new project configuration contract example |
| `projects/example_sales/project.json` | complete working project example |
| `engine/config.py` | project/source contract validation; edit only for reusable config gap |
| `engine/pipeline.py` | canonical state machine, transactions, publish order; high-risk shared core |
| `engine/excel/reader.py` | dependency-free direct `.xlsx` extraction |
| `engine/excel/com_reader.py` | authorized Windows Excel COM block extraction for protected workbooks |
| `engine/data/staging.py` | source discovery/extraction routing and lineage staging |
| `engine/data/quality.py` | row/dataset quality and quarantine |
| `engine/data/history.py` | APPEND / UPSERT / SNAPSHOT / REPLACE_PERIOD trusted history |
| `engine/data/metrics.py` | deterministic trusted SQL metrics |
| `engine/data/cube.py` | approved pre-aggregated dashboard analytical data |
| `engine/data/insights.py` | configured + automatic evidence-backed insights |
| `engine/db/database.py` | DuckDB production backend + SQLite dev/test fallback, migrations |
| `engine/db/migrations/` | reusable database schema |
| `engine/sync/sql_server.py` | optional post-publication SQL Server synchronization |
| `engine/report/dashboard.py` | dashboard JSON contract |
| `engine/report/standalone.py` | self-contained HTML build and offline verification |
| `engine/webapp/static/index.html` | 2026 one-page dashboard structure |
| `engine/webapp/static/styles.css` | responsive light/dark/RTL dashboard design |
| `engine/webapp/static/app.js` | presentation filters/charts/tables/state UI; no trusted KPI formulas |
| `engine/packaging/builder.py` | final operator package builder |
| `engine/packaging/verifier.py` | final ZIP shape, runtime and dependency gate |
| `engine/cli.py` | `PROJECT_TOOL` commands and doctor readiness checks |
| `tests/test_v13_features.py` | V13 state/history/insight/sync contract tests |
| `tests/test_v14_hardening.py` | V14 extraction, decision UX and reliability edge-case proofs |
| `tests/test_packaging.py` | final ZIP and dependency-gate proofs |
| `tests/test_pipeline.py` | transaction, publish, rollback proof |
| `tests/test_analytics.py` | cube/filter reconciliation proof |
| `tests/test_standalone.py` | offline saved dashboard proof |
| `tests/test_webapp.py` | web boundary and page asset proof |
| `tests/test_browser.py` | real browser behavior where Chromium/Playwright are available |
| `runtime_inputs/README.md` | required private Windows runtime dependencies |
| `docs/AUTOMATION_FLOW.md` | end-to-end recurring flow |
| `docs/FINISH_ON_WINDOWS.md` | target Windows proof checklist |
| `tools/make_template_zip.py` | builds the adaptation-agent template ZIP |

## Dependency direction

```text
project configuration
→ pipeline
→ extraction / quality / history / calculations / insights
→ dashboard JSON + standalone HTML
→ verification + atomic publication
→ optional enterprise synchronization
```

The browser consumes verified dashboard data; it must never become the trusted calculation engine.
