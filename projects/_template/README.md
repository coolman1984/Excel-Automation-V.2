# Project folder

Everything a single report needs lives here.

| File | What it is |
|---|---|
| `project.json` | The business meaning: files, columns, keys, rules, totals, dashboard |
| `sql/metrics.sql` | The trusted calculations |
| `tests/golden.json` | Expected values that must never change silently |
| `fixtures/` | Small, safe example files (never real customer data) |

Nothing else belongs here. Shared behaviour belongs to the engine.
