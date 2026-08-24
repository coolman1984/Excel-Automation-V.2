# Support codes

Every message the user sees answers four questions: what happened, whether the
previous trusted result is still safe, the one next action, and a support code.
This table is for whoever receives that code.

| Code | The user sees | Usual cause | Fix |
|---|---|---|---|
| `E-CFG-001` | Configuration missing | The package was built without `project.json` | Rebuild with `deliver`; `package verify` catches this |
| `E-CFG-002` | Configuration is not valid JSON | A hand edit broke the file | The message names the line and column |
| `E-CFG-003` | A required setting is missing | Incomplete adaptation | The message names the exact path |
| `E-CFG-004` | An unknown setting | A misspelled key | The message lists the allowed keys at that level |
| `E-CFG-005` | The business meaning is not approved | `approval.status` is still `PENDING_APPROVAL` | Confirm the meaning with the owner, then set `APPROVED` |
| `E-IN-001` | A file is missing | The user did not add one of the expected files | The page lists what is expected and the file-name patterns |
| `E-IN-002` | A file could not be opened | Wrong file type, corrupt file, or the tab was renamed | Re-save as `.xlsx`; check the tab name in the source |
| `E-IN-003` | A column is missing | The export changed | Add the column back, or update `columns` in the project |
| `E-IN-004` | The file changed while being read | The file was open and being edited in Excel | Close it and press Process again |
| `E-VAL-001` | Too many rows failed the rules | A different file, or a real data problem | The attention list names the file and Excel row for each one |
| `E-REC-001` | Totals did not match | A value changed between reading and storing, or a control total is configured on the wrong column | Nothing was published; check the reconciliation table on the page |
| `E-HIST-001` | History could not be updated | Database locked by another copy of the application | Close the other window and try again |
| `E-SQL-001` | A calculation failed | A metric refers to a view or column that does not exist | Fix `sql/metrics.sql`; `doctor` catches most of these |
| `E-PKG-001` | The package is incomplete | The ZIP was edited, or extracted partially | Extract the original ZIP again |
| `E-RUN-001` | The run stopped unexpectedly | A bug | Send the code; the full trace is in `Application/Data/logs/application.log` |

## Where to look

| What | Where |
|---|---|
| Log file | `Application/Data/logs/application.log` |
| Database | `Application/Data/data/warehouse.db` (DuckDB in production; SQLite may be used only by a development/test runtime) |
| Last published dashboard | `Application/Data/data/dashboard.json` |
| Archived previous results | `Application/Data/archive/<run_id>/` |
| Copies of the processed input files | `Application/Data/runs/<run_id>/input_copies/` |

## Restoring a previous result

The archive holds the last runs (10 by default). Copy `dashboard.json` and
`warehouse.db` from `Application/Data/archive/<run_id>/` back into
`Application/Data/data/`, then start the application again.

## Rules that never change

- A failed run never replaces the last approved dashboard.
- A failed run never leaves trusted history half-updated: each run is a single
  transaction.
- Rejected rows are never deleted silently - they stay visible with their file
  name and row number.
