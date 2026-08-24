# `project.json` reference

The complete list of settings. The validator rejects anything not listed here,
naming the exact path, so a typo costs one line of output rather than a run.

## Root

| Key | Type | Required | Meaning |
|---|---|---|---|
| `project_name` | string | yes | Internal name; becomes `<name>.zip`. Letters, digits, `_`, `-`. |
| `title` | object or string | no | `{"en": "...", "ar": "..."}`; shown on the page. |
| `language` | string | no | `en` or `ar`; the language the page opens in. |
| `approval` | object | no | `status` (`APPROVED` / `PENDING_APPROVAL`), `approved_by`, `approved_on`, `notes`. A run refuses to publish unless the status is `APPROVED`. |
| `business` | object | no | `purpose`, `decision_supported`, `run_frequency`. Shown to the user and recorded in the run manifest. |
| `sources` | array | yes | One entry per input file. |
| `relationships` | array | no | How sources join. |
| `metrics_sql` | string | no | Path to the metrics file, default `sql/metrics.sql`. |
| `dashboard` | object | no | Which metrics appear as KPIs and tables. Metric KPIs are whole-report figures; they are labelled "not filtered" when a filter is active. |
| `analytics` | object | no | The filters, charts and comparisons; see below. |
| `automation` | object | no | Watched folder and unattended runs; see below. |
| `insights` | array | no | Rules that turn a metric into a highlight. |
| `quality_gates` | object | no | `block_on_reconciliation_failure` (default `true`), `max_rejected_percent` (default `100`), `archive_keep_runs` (default `10`). |
| `database` | object | no | Local warehouse backend. `backend` is `duckdb` (production), `auto`, or `sqlite` (development/test fallback). |
| `sql_server` | object | no | Optional post-local-success synchronization: `enabled`, `connection_string_env`, `schema`, `table_prefix`, `batch_rows`, optional `sources`. |
| `notes` | string | no | Free text for the next agent. |

## `sources[]`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `id` | string | — | Table name. Letters, digits, underscore. |
| `title` | string | `id` | What the business calls this file. |
| `match` | string or array | — | File name patterns, e.g. `["sales_*.xlsx"]`. |
| `format` | string | `xlsx` | `xlsx` or `csv`. |
| `sheet` | string, integer or null | first tab | Tab name or index. |
| `header_row` | integer | `1` | The Excel row holding the headings. A **hint**, not a hard requirement: see `header_search_rows` below - a banner row added above it does not need this changed. |
| `header_search_rows` | integer | `25` | How many rows from the top of the sheet may be searched for the real header when `header_row` no longer looks right. Raise it for a file with an unusually tall banner; lower it toward `1` to disable the search and require an exact match, e.g. for a source where any drift should always block. |
| `column_order` | string | `unstable` | `stable` enables a positional fallback: an unresolved required column takes the same position it holds in this list, matched to the same position in the file. Never applied to a `business_key` or `control_totals` field. Use only when the file's column order is genuinely guaranteed by its source system. |
| `delimiter` | string or null | detect | CSV only. |
| `required` | boolean | `true` | `false` lets a run proceed without this file. |
| `grain` | string | `""` | One sentence: what a row represents. |
| `business_key` | array | `[]` | Fields that identify the same record across files. Empty means identical rows are de-duplicated by their content. |
| `corrections_allowed` | boolean | `true` | May a later file change an existing record? `false` keeps the trusted value and lists the attempt. |
| `missing_record_policy` | string | `keep` | Legacy compatibility: `keep` implies UPSERT, `close` implies SNAPSHOT when `update_mode` is omitted. |
| `update_mode` | string | inferred | `APPEND`, `UPSERT`, `SNAPSHOT`, or `REPLACE_PERIOD`. Prefer this explicit V13 setting. |
| `period_field` | string | `""` | Required by `REPLACE_PERIOD`; identifies the exact business period being replaced. |
| `extraction` | object | `{"mode":"auto"}` | `mode`: `auto`, `direct`, or `excel_com`; optional `chunk_rows` and `visible`. Use `excel_com` for protected corporate workbooks that require Excel desktop. |
| `structure` | object | see below | Detection of total/subtotal/banner/section rows inside the data. See `sources[].structure` below. |
| `columns` | array | — | The mapping; see below. |
| `filters` | array | `[]` | Rows deliberately out of scope. |
| `checks` | array | `[]` | Quality rules. |
| `control_totals` | array | `[]` | `{"field": "...", "precision": 2, "tolerance": "0"}`. |
| `notes` | string | `""` | Free text. |

## `sources[].columns[]`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `source` | string | — | The heading exactly as it appears in Excel (matched case-insensitively, trimmed). |
| `field` | string | — | Internal name, used in SQL. |
| `type` | string | `text` | `text`, `number`, `integer`, `date`, `datetime`, `boolean`. |
| `required` | boolean | `false` | An empty value sends the row to quarantine. |
| `trim` | boolean | `true` | Remove surrounding spaces. |
| `default` | any | `null` | Used when the cell is empty. |
| `date_formats` | array | `[]` | Extra `strptime` patterns tried first, e.g. `["%d/%m/%Y"]`. |
| `scale` | integer | `12` | `number` columns only. Decimal places kept exactly; a value needing more is quarantined rather than rounded. |
| `aliases` | array | `[]` | Other header texts this column is known by, e.g. `["Total Amount", "Net Amount"]`. An alias match is treated the same as an exact match - never a guess, never a warning. |
| `notes` | string | `""` | Free text. |

Values the parser already understands without help: `1,234.50`, `1 234`,
`(50)` as negative, trailing-minus `12-`, Arabic decimal `12٫5`, the usual date
orders, `Yes`/`No`/`نعم`/`لا`, and an Excel serial number that lost its format.
A percentage such as `15%` is deliberately refused rather than guessed.

## Header and column resolution

A header exactly where `header_row` says, with column names exactly matching
`columns[].source`, resolves silently and is never mentioned again. Anything
short of that is absorbed when it safely can be, and always named on the
dashboard's controls table so nothing is silent:

- **Header moved** (a banner or title row added above it) - found automatically
  within `header_search_rows` rows, reported as `header_location`, run stays
  at `WARNING`.
- **Column renamed, reordered, translated, or given a unit suffix** - resolved
  through a ladder of increasingly permissive rules (exact, alias, normalised
  case/punctuation/digit-forms, fuzzy similarity, and opt-in position), reported
  as `column_mapping`, run stays at `WARNING`. A genuinely different-looking
  name (`Amount` vs `Total Amount`) is deliberately **not** guessed - declare it
  as an `aliases` entry once the business owner confirms it means the same
  thing, and it resolves silently from then on.
- **Two files' headers, or two possible matches, tie exactly** - refused
  outright rather than picked arbitrarily; the run `BLOCK`s with the tied
  candidates named.
- **Nothing in the file matches any configured column at all** - no guess is
  made; the run `BLOCK`s with the ordinary missing-column message.

Run `PROJECT_TOOL doctor --project projects/<Name> --probe <folder-with-a-sample-file>`
to see exactly how a representative file would be read - sheet, header row,
every column's resolution and rung, and how its rows classify - without
processing anything.

## `sources[].structure`

Total lines, subtotal lines, title banners and section labels sit in the same
columns as real rows, so a reader that trusts the rectangle counts them as
data. This block controls how they are told apart; see `docs/AUTOMATION_FLOW.md`
for the full classification rules.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `detect_total_rows` | boolean | `true` | Set `false` only for a source that is proven never to contain one. |
| `total_label_fields` | array | all text columns | Which columns' text is checked against the total-label lexicon (`Total`, `Subtotal`, `الإجمالي`, ...). |
| `extra_total_labels` | array | `[]` | Project-specific words to add to that lexicon. |
| `verify_totals_against_data` | boolean | `true` | Compare a detected total against the rows it covers. |
| `on_total_mismatch` | string | `block` | `block` (safest) or `warn` when a stated total disagrees with its rows. |
| `capture_section_headers_into` | string or null | `null` | A mapped text column to fill with the last section label seen above each row. |
| `stop_after_blank_rows` | integer | `0` | `0` reads the whole sheet; a positive number ends the data block after that many consecutive blank rows. |

Every excluded row - total, banner, section or malformed - keeps its Excel
row number and original values in the `excluded_rows` table and is never
silently dropped.

## What each layer creates in the database

| Object | Content |
|---|---|
| `stg__<id>` | Raw text exactly as read, with file name, hash and Excel row number |
| `clean__<id>` | Typed, checked rows for this run |
| `hist__<id>` | Trusted history: one row per business key, versioned |
| `v_<id>` | The active trusted records - **what your SQL reads** |
| `quarantine` | Rejected and warned rows, with the reason in plain language |
| `filtered_rows` | Rows excluded on purpose, so nothing is unaccounted for |
| `reconciliation` | Every proof, per run |
| `metrics`, `insights`, `runs`, `run_files`, `run_events`, `sync_events` | Results, run-state evidence and optional synchronization status |


## `analytics`

The pre-aggregated cube the browser filters. Omit it and the page still works -
it simply has no filters and no charts of its own.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `fact_sql` | string | `sql/fact.sql` | A file holding one SELECT over the trusted views: the date, every dimension column, every measure column. |
| `from` | string | — | Instead of `fact_sql`: read a single view directly, e.g. `"v_sales"`. |
| `date.field` | string | — | The column that dates a row. |
| `date.grain` | string | `month` | `day`, `week`, `month`, `quarter`, `year`. |
| `date.title` | string | `Period` | What to call the time axis. |
| `dimensions[]` | array | `[]` | `{"id", "title", "field"}` - what people filter and group by. A dimension with more than 12 distinct values still groups charts, but is not offered as filter chips. |
| `measures[]` | array | `[]` | See below. |
| `charts[]` | array | `[]` | `{"id", "title", "measure", "by", "form", "split"}`. `by` is `date` or a dimension id; `form` is `line`, `bar`, `stacked` or `donut`; `split` divides a chart into series. |
| `kpis[]` | array | every measure | Which measures appear as cards, in order. |

### `analytics.measures[]`

| Key | Meaning |
|---|---|
| `id` | Used by charts and KPIs. |
| `title` | Shown to the person, exactly as written. |
| `aggregate` | `sum`, `count` or `ratio`. |
| `field` | The column to add up (`sum` only). |
| `numerator`, `denominator` | Two additive measure ids (`ratio` only). |
| `format` | `money`, `integer`, `percent`, `number`. |
| `unit` | Appended after the number, e.g. `SAR`. |
| `goal_direction` | `up` (default) or `down` - decides whether a rise is shown as good or bad. |

**Why only these three.** A filtered figure is a sum of pre-aggregated cells, so
it is exactly right for additive measures, and for a ratio whose two parts are
summed before dividing. A distinct count is not additive - two months of
distinct customers cannot be added - so it is refused here, with that reason,
and belongs in `sql/metrics.sql` as a whole-report KPI.

Every run recomputes the cube's totals straight from the fact query and refuses
to publish if they disagree, so a lost row cannot silently change a filter.

## `automation`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `watch_folder` | string | `""` | While the application is open, new or changed files here are processed by themselves. |
| `check_every_minutes` | number | `10` | How often to look. |
| `process_on_start` | boolean | `false` | Process whatever is already waiting when the application opens. |

A file is only processed when its content changed, so nothing is duplicated by
looking twice. For unattended runs use a scheduler and
`Application\runtime\pythonw.exe Application\app\launch.py --run-once`, which
processes what is waiting and exits with a status code.

The delivered package ships `SCHEDULE.bat` at its root for exactly this: it
registers a per-user Windows scheduled task (hourly or daily) that calls
`--run-once`, with no administrator rights and no stored password. A
scheduled run has no console to watch, so a failure there - a broken
configuration or a blocked publish - is written to `NEEDS_ATTENTION.txt`
next to `START.bat` instead; that file is removed automatically the next
time a run succeeds, so it only ever appears when something actually needs
a person's attention.
