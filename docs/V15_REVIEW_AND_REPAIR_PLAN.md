# V15 — Review, Repair and Sustainable-Automation Plan

**Status:** DRAFT — awaiting your approval. **No engine code has been changed.**
**Baseline reviewed:** `ULTIMATE_EXCEL_AUTOMATION_V14_MASTER_TEMPLATE.zip`, imported unchanged as commit 1 of this branch.
**Authority documents:** V11 Simple Product Master Plan, V14 Final Adaptation Agent Instruction, `.ai/CURRENT_STATE.md`.
**Date:** 2026-08-24

---

## 0. ملخص تنفيذي

راجعت المشروع كله: قرأت الكود، شغّلت الـ 167 اختبار (كلها نجحت)، شغّلت المشروع من أوله لآخره، صوّرت الداشبورد في Chromium، وبنيت ملفات Excel فيها الحالات الصعبة اللي إنت ذكرتها عشان أختبر عليها فعلياً بدل ما أخمّن.

**الخلاصة في ٤ نقاط:**

1. **المحرك مبني صح من حيث المعمار** — Pipeline محدد، Reconciliation، History بأربع طرق، Quarantine، Offline packaging. ده أساس قوي ومش محتاج إعادة بناء.

2. **لكن فيه عيب واحد خطير جداً:** لو الملف فيه **صف إجمالي (Total / Subtotal) في وسط البيانات** والصف ده مالي الأعمدة المطلوبة — المحرك بيبلعه كأنه بيانات عادية. جربتها: الإيراد الحقيقي **٦٠٠**، والمنشور على الداشبورد **١٧٠٠**. وكل فحوصات "إثبات صحة الأرقام" طلعت **PASS**. يعني النظام بيشهد إن الرقم الغلط صح. ده يهدم الوعد الأساسي للمنتج.

3. **والمشروع مش مستدام للتشغيل اليومي بدون تدخل:**
   - الـ inbox **مبيتنضّفش أبداً** — كل تشغيل بيعيد قراءة كل ملف اتضاف من قبل. أثبتّها عملياً: تشغيلتين = ١٠ صفوف بدل ٥.
   - أي **صف عنوان زيادة فوق الهيدر** = الرن بيقف تماماً (E-IN-003) والحل المقترح "عدّل الإعدادات" = ترجع تنادي الـ AI. ده بالظبط اللي إنت عايز تلغيه.
   - أي **تغيير في اسم عمود** = نفس التوقف.
   - الـ Watcher بيقرأ ملفات لسه بتتكتب، وبيرمي الملفات لو فيه رن شغال، وذاكرته بتضيع مع إعادة التشغيل.

4. **التصميم فعلاً وحش، وفيه bug مرئي:** في الـ Light mode **عنوان التقرير أبيض على خلفية بيضا = مش ظاهر خالص**. السبب إن ملف الـ CSS عبارة عن طبقات patches فوق بعض (٣٩ selector متكرر، وبلوك اسمه "V14 refinement" في آخر الملف بيلغي اللي فوقه). فيه كمان كارت دعائي فاضي بياخد أهم مساحة في الصفحة، وهرم الخطوط مقلوب، والرسوم البيانية مزحومة في ثلث الشاشة.

**الخطة تحت مقسومة على ٤ مراحل**، أولها إصلاح صحة الأرقام (P0)، وأهم جزء جديد فيها هو **Resilient Ingestion Layer** — طبقة بتخلي المحرك يفهم الملف حتى لو اتغير شكله، من غير ما يحتاج AI. مش هبدأ تنفيذ أي حاجة لغاية ما توافق.

---

## 1. What this product is, as actually built

The V14 template is a **reusable offline Excel-to-decision engine**. One ZIP goes to a
non-technical operator; they double-click `START.bat`, a loopback web app opens, they
drop Excel files in, press Process, and get a verified dashboard.

The internal run is a strict state machine:

```
DETECTED → OPENING → EXTRACTING → VALIDATING → LOADING → MERGING
→ CALCULATING → GENERATING_JSON → GENERATING_DASHBOARD → VERIFYING → COMPLETE
```

The parts that genuinely work and must be preserved:

| Capability | Where | Verdict |
|---|---|---|
| Dependency-free `.xlsx` streaming reader | `engine/excel/xlsx_reader.py` | Solid. Shared strings, inline strings, date styles, 1904 epoch, cached formula values — all handled with only the stdlib. |
| Deterministic run + single transaction + rollback | `engine/pipeline.py` | Correct in shape. A failed run does not corrupt history. |
| Four history contracts | `engine/data/history.py` | APPEND / UPSERT / SNAPSHOT / REPLACE_PERIOD are real and tested. |
| Row-population and control-total reconciliation | `engine/data/reconcile.py` | Integer-minor-unit comparison is the right idea. |
| Quarantine with Excel row numbers | `engine/data/clean.py` | Rejected rows stay visible and point back to the real file/row. |
| Pre-aggregated cube + browser-side filtering | `engine/data/cube.py` | The "browser never recalculates" boundary is enforced and verified. |
| Operator-package shape gate | `engine/packaging/verifier.py` | Blocks missing runtime, missing DuckDB/pywin32/pyodbc, unsafe ZIP paths. |
| Strict config validation | `engine/config.py` | Unknown keys fail loudly with an exact path. |

**This architecture should not be restarted.** Everything below is repair and extension.

---

## 2. How this review was done

Not by reading alone. Each finding below is either a code citation or a reproduction.

1. Read every engine module, the config contract, the packaging path, the web layer.
2. Ran the full suite: **166 passed, 1 skipped** (`tests/test_browser.py`, no bundled browser). After installing Playwright + Chromium it becomes **167 passed, 0 skipped** — and that is the more damning result: `test_browser.py` passes while the light-mode report title is invisible (D1). The suite is green *because of* its blind spots, not despite them. See §3.
3. Ran the shipped `example_sales` project end-to-end. Result `WARNING`, dashboard published.
4. Rendered the generated `dashboard.html` in Chromium at 1440 px, 420 px, and in dark mode. Captured screenshots. No page errors, no horizontal overflow — the V14 report is accurate on those two points.
5. **Built new Excel fixtures for the exact edge cases you named** and ran them through the real engine (`docs/review/edge_case_repro.py`).

The last step is what produced the two critical findings. They are not theoretical.

---

## 3. Findings

Severity: **P0** = publishes wrong numbers or blocks unattended operation. **P1** = fails at real scale or on the target runtime. **P2** = quality, maintainability, polish.

### P0-1 — A total row inside the data is silently counted as data. Every check still passes. ⚠️ *Most important finding*

Real-world Excel exports routinely carry `Subtotal` and `TOTAL` rows between or after
data blocks. Nothing in the engine detects them: not the reader, not `clean.py`, not
`reconcile.py`.

Reproduction (`docs/review/edge_case_repro.py`, case 1b) — three real invoice lines
worth **600**, plus one subtotal row and one grand-total row that happen to have their
required columns populated (the normal case when `TOTAL` sits in the description column):

```
status     : PASS
  PASS  sales.control_total_amount:        1700.00 -> 1700.00  (diff 0.00)
  PASS  analytics.analytics_total_revenue: 1700    -> 1700     (diff 0)
  PASS  sales.row_population: 5 rows read -> 5 accepted + 0 rejected
```

**Published revenue: 1,700. True revenue: 600. Status: PASS.**

The reason reconciliation cannot catch this is structural: every check compares the
*file* against the *warehouse*. Both sides contain the phantom rows, so both sides
agree. The engine proves **faithful transcription**, and then the product describes that
as **"Proof the numbers are right"** — which is a stronger claim than the evidence
supports.

A second variant is nearly as bad. When the total row *fails* a type rule (case 1: empty
`Line`), it is quarantined as `type_or_required` — and with two total rows out of seven
source rows, the 20 % rejection gate fires and the whole run **BLOCKS**. So a plain
subtotal either corrupts the numbers or kills the run, depending on how the row is
filled in.

### P0-2 — The inbox is never cleared; every run reprocesses every file ever supplied

`discovery.find_matching()` globs the whole inbox each run, and nothing ever removes,
archives, or ledgers a processed file. `engine/cli.py:141-145` copies new files *into*
the persistent inbox and leaves them there. `automation.Watcher.check_once()` does the
same.

Reproduced: two consecutive runs against two different single-file inboxes reported
`10 rows read` from a 5-row file, because run 2 re-read run 1's file. After 30 daily
runs the engine re-extracts 30 files, and the "total from your files" figure shown to
the business user grows without bound.

UPSERT/SNAPSHOT history absorbs the duplication *in the warehouse*, which is why no test
caught it — but extraction cost grows O(n²) over the life of the report, and the
reconciliation evidence shown to the user becomes meaningless.

### P0-3 — Any header shift or column rename hard-blocks the run and demands an AI

`Source.header_row` is a fixed integer. `staging._map_headers()` requires an exact
case-insensitive match on `column.source`. There is no aliasing, no fuzzy match, no
header search, no positional fallback.

Reproduction (case 2) — one banner row added above the header, which is what happens the
first time somebody re-exports the report with a title:

```
status : BLOCK
E-IN-003: An expected column is missing from an input file.
next: Add the column(s) ['Invoice No', 'Line', ...] to 'sales_banner.xlsx',
      or update the source mapping for 'sales'.
```

The remedy the product offers the operator is *edit the configuration* — i.e. call the
adaptation agent back. The V14 instruction accepts this explicitly ("the AI adaptation
agent is needed again only when the source structure … changes"). **Closing this gap is
the core of your request**, and it is addressed in §5.

### P0-4 — Unattended runs can ingest a half-written file

`automation.collect_new()` hashes a file with no stability check and immediately records
the fingerprint in `seen`. A file still being copied over a network share is hashed
mid-write, copied to the inbox, and processed as complete data. `discovery.collect()`
re-hashes it later, but by then the truncated copy is stable and passes.

`discovery._stable_stat()` does exist, but it waits **2 × 80 ms**. That is not a
meaningful settling window for a slow export.

### P0-5 — The watcher drops files it cannot process, permanently

`Watcher.check_once()` records the fingerprint in `seen` *before* calling
`on_new_files()`. If a run is already in progress, `Application.process()` returns
`{"started": False}` and the file is never processed — but it is now marked as seen, so
the next tick skips it. Same for any run that fails: no retry.

`seen` is also in-memory only, so a restart re-processes everything. The module docstring
claims "the fingerprint of every file already processed is remembered", which is not what
the code does.

### P0-6 — There is no unattended entry point in the operator package

`launch.py --run-once` exists and works. The delivered ZIP ships only `START.bat`, which
starts the interactive web app. To run daily unattended the operator must open a terminal
and configure Task Scheduler by hand — which violates the product's own rule ("no
terminal", "no technical setup"). There is also:

- **no run lock** — two scheduled instances would open the same DuckDB file concurrently;
- **no failure notification** — a 06:00 failure is discovered when somebody looks;
- **no "nothing new today" outcome** — `discovery.collect(required=True)` raises `E-IN-001` when the file has not arrived yet, so a normal quiet day is reported as a failure.

### P1-1 — The DuckDB production path has never been executed

`.ai/CURRENT_STATE.md` is honest about this, and it deserves emphasis: **the entire
167-test suite runs on the SQLite fallback.** DuckDB is the documented production
backend. Specific portability risks found by inspection:

| Construct | Where | Risk |
|---|---|---|
| `SET temp_directory = ?` with a bound parameter | `database.py:174` | DuckDB `SET` does not take prepared parameters. Wrapped in `try/except: pass`, so the spill directory **silently never applies** — exactly the setting meant to prevent OOM on large workbooks. |
| `PRAGMA enable_object_cache` | `database.py:172` | Deprecated in current DuckDB; silently swallowed. |
| `p.ROWID IS NULL` in a LEFT JOIN | `reconcile.py:230` | Works in SQLite. Fragile in DuckDB; should test the parent key instead. |
| `_split_script()` naive `;` splitting | `database.py:113` | "Migrations intentionally contain no SQL strings with ';'" — one future migration breaks it silently. |
| Single-writer file lock | DuckDB semantics | The web server and a scheduled `--run-once` cannot hold the same database. Blocks §5.6. |

### P1-2 — Row-by-row history merge will not survive a large daily file

`history.apply()` issues **one `SELECT` plus one `INSERT`/`UPDATE` per clean row** in a
Python loop (`history.py:94-140`). At 500 000 rows that is over a million round trips.
This must become a set-based merge.

### P1-3 — Whole-table materialisation contradicts the streaming promise

Extraction streams correctly. Everything after it does not:

- `clean.py:75` — `SELECT * FROM stg__<source>` `.fetchall()`, all staged rows in RAM.
- `reconcile.py:49-51` — all staged rows **and** all clean rows in RAM simultaneously.
- `clean.py:_reject_rows` — one `DELETE` per rejected row.
- `clean.py` `seen_keys` — unbounded dict for duplicate detection.

The product claims "block-based reads, never cell-by-cell" and "never materialise a huge
workbook in RAM". True of the reader, false of the pipeline.

### P1-4 — Money is carried as a float

`types.parse()` maps `number` → `parse_number()` → **`float`**, stored as `DOUBLE`.
`reconcile.py` then converts back to `Decimal` and compares in integer minor units — so
reconciliation is exact, but the trusted metric SQL sums `DOUBLE` columns. The docstring
"0.1 + 0.2 can never drift" is true only of the reconciliation comparison, not of the
published KPI. At scale, summing millions of doubles accumulates real error.

### P1-5 — The `unique` check deletes every row of a duplicate group

`clean._run_checks()` for `kind == "unique"` fetches *all* rows in each duplicate group
and `_reject_rows()` deletes each one. Two rows sharing a key means **both** disappear —
including the legitimate original. The normal semantic is keep-first, quarantine-the-rest,
which `clean()` already implements for `business_key` but not for a `unique` check on
different fields.

### P1-6 — One over-wide CSV row aborts the entire run

`csv_reader.iter_rows()` raises `E-IN-003` on any row with more fields than the header.
A trailing delimiter or a footer line like `TOTAL,,,12345` kills an unattended run. This
should quarantine the row, not abort the file.

### P1-7 — Publication of the JSON/HTML pair is not atomic

After `COMMIT`, `pipeline.py` performs four separate `atomic_write` calls (JSON, HTML,
then both again after sync). Each write is individually atomic; the **set** is not. A
crash between them leaves the database advanced to run N while the dashboard is a mix of
run N and N−1. The "last approved dashboard always survives" invariant is only partly
delivered.

### P1-8 — Schema drift is invisible

New columns in the source are silently ignored (`_map_headers` only reports *missing*
optionals). Nothing tells anyone the file changed shape. A renamed column that happens to
be optional silently becomes NULL, and the KPI quietly drops.

### P1-9 — `automation` config is accepted but never validated

`automation` is in `_ROOT_KEYS` (`config.py:34`) but has no key validation, unlike every
other section. A typo — `check_every_minute` instead of `check_every_minutes` — silently
disables the watcher with no error.

### P1-10 — `START.bat` fails silently

`:run_quiet` calls `start "" pythonw.exe launch.py` and returns 0 immediately. If Python
fails to start, the operator sees no window, no browser and no error. There is no
fallback to the console path on failure.

### P2 findings

- **`.ai/PROJECT_MAP.md` has drifted** — it routes agents to `engine/excel/reader.py` and `engine/data/quality.py`. Neither exists (`xlsx_reader.py`, and quality lives inside `clean.py`). The map is the *first* file an adaptation agent reads.
- **`REPLACE_PERIOD` semantics are ambiguous** — `periods` is `SELECT DISTINCT <period_field>`, so a date field replaces per-*day*, not per-month. Undocumented.
- **No SCD-2 audit** — `_version` increments but old values are overwritten. "Version corrections" implies a change log that does not exist.
- **Row-hash key collision** — with no `business_key`, `history.apply()` keys on `_row_hash`. Two genuinely identical rows in one file collapse into one record.
- **`find_matching` is non-recursive** and ignores only `~$`/`.` prefixes — not `.tmp`, `.part`, `.crdownload`.
- **Static path check** uses `target.startswith(STATIC_DIR)` without a separator, so a sibling directory named `static_x` would pass. Use `os.path.commonpath`.
- **Session key travels in the URL query string** and lands in browser history. Should hand off to a cookie on first load.
- **Docs overclaim** — `docs/AUTOMATION_FLOW.md` step 3 lists "duplicate-run protection", which exists only as the in-process `seen` dict.
- **The reconciliation table is shown raw to a business user** — `control_total_amount`, `link_to_customers`, `analytics_cells` with expected/actual/difference columns. This is engine internals on the operator's screen, against the V11 rule "the user sees outcomes, not components".

### Design findings

Rendered from the real generated `dashboard.html`.

- **D1 — In light mode the report title is invisible** (and `test_browser.py` passes anyway)**.** `.topbar` at line 129 sets `color:#fff` over a dark `--brand` gradient. Line 421, inside a later block, redefines `.topbar` background to `color-mix(in srgb, var(--surface) 88%, transparent)` — near-white in light mode. **White text on a white bar.** Dark mode hides the bug, which is presumably why it shipped as "PASS in rendered QA".
- **D2 — Root cause: the stylesheet is layered patches, not a system.** 468 lines, **39 selectors defined more than once**, with a block at line 418 labelled "V14 executive one-page refinement" overriding earlier rules. `.chart-grid` is defined twice with contradictory grids (2-column, then 12-column spans). `.kpi` appears 13 times, `.chart` 13 times.
- **D3 — Marketing filler occupies the top of the results page.** The "Verified before it is published" trust card takes the prime slot and, in the exported copy where the intake card is hidden, sits alone in a 2-column grid leaving a large dead area.
- **D4 — Inverted type hierarchy.** Section headings are `1.02rem`; the exception headline renders at `clamp(24px, 2.2vw, 36px)`. "2 row(s) were not used" is the largest text on the page, above the revenue figure.
- **D5 — Wizard step numbers leak into the exported dashboard** — "2. Your result", "3. Proof the numbers are right". There are no steps in a saved copy.
- **D6 — Chart layout is broken at width.** `preserveAspectRatio="xMinYMin meet"` on a fixed 640×270 viewBox left-aligns the plot inside a wide card; the stacked chart occupies roughly a third of its container. `barWidth = min(56, bandWidth*0.62)` leaves 3-category bands 70 % empty.
- **D7 — Chart junk and flat colour.** Everything is one blue. Value labels sit inconsistently inside and outside bars. Gridlines are the same weight as axis lines.
- **D8 — Card soup.** Every block is the same white surface, 22 px radius, same shadow, stacked vertically. No density rhythm, no grouping, no visual hierarchy between an executive number and an audit table.
- **D9 — Contradictory KPI microcopy.** Cards say "no earlier period to compare" while still drawing a sparkline.
- **D10 — Icons are text glyphs** (`✓ ◇ ↻ ◷ ◎`) with inconsistent optical size and platform-dependent rendering.

---

## 4. Repair plan

Four phases. Each phase ends green and shippable. Nothing starts until you approve.

### Phase A — Numbers you can actually trust (P0-1, P1-4, P1-5, P1-7)

| # | Change | Files |
|---|---|---|
| A1 | Non-data row classifier (§5.3) — detect and exclude total/subtotal/banner/footer rows before staging, into a new `excluded_rows` ledger with reason `structural_total` | new `engine/data/structure.py`, `staging.py` |
| A2 | New reconciliation check `structural_integrity`: source rows = data + excluded-structural + rejected + filtered, and, when a total row was found, **assert the detected total equals the sum of the data rows it covers**. This turns the phantom-row case from silent corruption into a positive proof. | `reconcile.py` |
| A3 | Exact money: `number` columns carry `Decimal`; store as `DECIMAL(38,s)` in DuckDB / scaled `INTEGER` minor units in SQLite; SQL metrics sum exact types | `types.py`, `database.py`, `clean.py` |
| A4 | `unique` check becomes keep-first / quarantine-rest | `clean.py` |
| A5 | Single publication commit: write JSON+HTML into a staged directory, `os.replace` a pointer, one durable step | `pipeline.py`, `archive.py` |
| A6 | Rewrite the operator-facing controls panel in business language; keep the raw check table behind "Technical detail" | `dashboard.py`, `app.js` |

**Exit gate:** the two reproductions in `docs/review/edge_case_repro.py` produce the
right number or a clear BLOCK with a business-readable reason — never a wrong number
with `PASS`.

### Phase B — Resilient ingestion (P0-3, P1-6, P1-8) — see §5 for the full design

| # | Change | Files |
|---|---|---|
| B1 | Sheet + header auto-location | new `engine/excel/layout.py` |
| B2 | Column resolution ladder with aliases and normalisation | `staging.py`, `config.py` |
| B3 | Structural-drift report surfaced in the dashboard and the run manifest | `dashboard.py`, `pipeline.py` |
| B4 | CSV over-wide row → quarantine, not abort | `csv_reader.py` |
| B5 | Config contract extension + validation + migration of `projects/_template` | `config.py`, `docs/CONFIG_REFERENCE.md` |

### Phase C — Sustainable unattended operation (P0-2, P0-4, P0-5, P0-6, P1-9) — see §5.5–§5.7

| # | Change | Files |
|---|---|---|
| C1 | Persistent processed-file ledger + inbox lifecycle (archive / retain / purge) | new `engine/data/ledger.py`, migration `0004` |
| C2 | Proper file-settling with backoff; retry queue for transient failures | `discovery.py`, `automation.py` |
| C3 | Watcher: persist `seen`, queue instead of drop, retry with backoff, never mark seen before success | `automation.py` |
| C4 | "No new data" is a first-class successful outcome, not `E-IN-001` | `pipeline.py`, `discovery.py` |
| C5 | Cross-process run lock | new `engine/runlock.py` |
| C6 | `SCHEDULE.bat` in the operator package: registers a per-user Task Scheduler job, no admin rights | `packaging/templates/`, `builder.py`, `verifier.py` |
| C7 | Failure notification (local alert file + optional SMTP, offline-safe) | new `engine/notify.py` |
| C8 | Validate the `automation` config section | `config.py` |
| C9 | `START.bat` reports a real error instead of exiting 0 silently | `packaging/templates/START.bat` |

### Phase D — Scale and target-runtime truth (P1-1, P1-2, P1-3)

| # | Change | Files |
|---|---|---|
| D1 | Set-based history merge (`MERGE`/`ON CONFLICT`) replacing the per-row loop | `history.py` |
| D2 | Push clean/reconcile work into SQL; stream in bounded batches; batch deletes | `clean.py`, `reconcile.py` |
| D3 | Install DuckDB in CI and run the **entire** suite twice — once per backend | `tools/`, test config |
| D4 | Fix the DuckDB-specific defects found in P1-1 | `database.py`, `reconcile.py` |
| D5 | Scale fixture: 1 M-row generated workbook with a documented time/memory budget | `tools/make_fixtures.py`, new `tests/test_scale.py` |

### Phase E — Design system (§6)

---

## 5. The sustainable-automation toolkit

This is the heart of your request: **a file that updates daily, at any cadence, running
by itself, without calling an AI back every time the file changes shape.**

The design principle throughout:

> Everything the engine infers, it must **declare, prove and record**. Inference never
> silently changes a trusted number. When confidence is low the run degrades to a clear,
> business-readable BLOCK — never to a wrong answer, and never to a technical error that
> only an AI can decode.

### 5.1 Sheet and header auto-location

New module `engine/excel/layout.py`. Before staging, scan the first *N* rows (default 25)
of the candidate sheet and score each row as a header candidate:

- fraction of cells that are non-empty text;
- fraction that match a configured `source` name or a known alias, after normalisation;
- the row below it looks like data (types match the mapped column types);
- penalty for merged-cell banners and single-cell rows.

Pick the best-scoring row. `header_row` in the config becomes a **hint**, not a hard
requirement: if the hinted row scores well, use it; otherwise search and record
`header_row_moved: 3 → 5` in the drift report.

Sheet selection gains the same treatment: `sheet` may be an exact name (today), a
wildcard (`"Sales*"`), or `"auto"` (pick the sheet whose header row scores highest).

### 5.2 The column-resolution ladder

`_map_headers()` becomes an ordered ladder. Each rung records how it matched:

| Rung | Rule | Confidence |
|---|---|---|
| 1 | exact match on `column.source` | `exact` |
| 2 | exact match on any entry in the new `column.aliases[]` | `alias` |
| 3 | normalised match — casefold, collapse whitespace, strip punctuation/diacritics, strip a trailing unit like `(SAR)`, normalise Arabic-Indic digits and alef/hamza forms | `normalised` |
| 4 | token-set match ≥ 0.9 (`Invoice No.` ↔ `No. Invoice`) | `fuzzy` |
| 5 | positional fallback, **only** when the source declares `"column_order": "stable"` and the type of the data below matches | `positional` |

Rules that keep this safe:

- A **required** column resolved at rung 4 or 5 raises the run to `WARNING` and names the mapping on the dashboard: *"'Invoice Number' was matched to the expected column 'Invoice No'."*
- Two candidates tying at the same rung is an **error**, never a guess.
- Every resolution is written to the run manifest, so an auditor can see exactly how each column was found on any past run.
- Rung 5 is opt-in per source and never applies to a column used in a control total or a business key.

### 5.3 The non-data row classifier — the fix for totals in the middle

New `engine/data/structure.py`, running between extraction and staging. Each row is
classified before it can become data:

| Class | Signals | Action |
|---|---|---|
| `data` | default | stage |
| `structural_total` | a key text column matches a total lexicon (`total`, `subtotal`, `sum`, `grand total`, `الإجمالي`, `المجموع`, `إجمالي`, `اجمالى`) **or** the row's numeric cells equal the running sum of the preceding data block within the configured precision **or** the business-key columns are empty while numeric columns are populated | exclude, reason `structural_total`, and **use it as an independent control total** |
| `banner` | single populated cell, or all-text row above the header | exclude, reason `banner` |
| `section_header` | one text cell populated, numeric cells empty, followed by data rows | exclude, reason `section_header`; optionally captured into a configured `section_field` (a very common Excel pattern) |
| `blank_separator` | fully empty | skip (already handled) |
| `footer` | trailing rows after the last data block that fail the data-shape test | exclude, reason `footer` |

**The arithmetic signal is the important one.** A row whose `Amount` equals the sum of
the `Amount` values since the last total row is a subtotal with very high confidence,
whatever it is labelled — and that same arithmetic makes it a *free, independent check on
the data we kept*, which is strictly better evidence than the current
file-total-equals-warehouse-total tautology.

Configuration, per source:

```jsonc
"structure": {
  "detect_total_rows": true,          // default true
  "total_label_fields": ["invoice_no", "product"],
  "extra_total_labels": ["ملخص", "Summary"],
  "verify_totals_against_data": true, // subtotal must equal the block it covers
  "on_total_mismatch": "block",       // block | warn
  "capture_section_headers_into": null,
  "stop_after_blank_rows": 0          // 0 = never stop; N = treat N blanks as end-of-data
}
```

Every excluded row lands in a new `excluded_rows` table with its Excel row number, its
class and its raw JSON, and is shown in the dashboard under **"Rows the file used for
layout, not data"** — visible, auditable, never silently dropped. Reconciliation then
proves:

```
source rows = data + structural + rejected + filtered
detected subtotals == sum of the data rows they cover      (the new independent proof)
```

### 5.4 Variable row counts and unbounded growth

Row counts changing every day is *normal*, and the engine already tolerates it. What it
does not tolerate is the second-order effects:

- **Volume drift as a signal, not a failure.** New optional gates
  `expected_rows_min` / `expected_rows_max` / `max_row_change_percent`. A daily file that
  suddenly arrives at 5 % of yesterday's size is usually a truncated export, and today it
  would be merged into history as a legitimate shrink. Under SNAPSHOT that *closes 95 % of
  the business records*. This gate turns that into a clear BLOCK with the last-good result
  intact.
- **Growing files.** A source declared `"cumulative": true` (the whole history re-exported
  every day) gets a high-water-mark: rows already merged with an identical row hash skip
  the merge entirely. Extraction still streams the file, but the merge cost tracks *new*
  rows.
- **Default `update_mode` audit.** The current default is `UPSERT` + `missing_record_policy: keep`.
  For a daily full-extract file the correct mode is `SNAPSHOT`; the default silently
  accumulates records that no longer exist upstream. `doctor` will flag the combination
  of a daily cadence and `UPSERT` and require an explicit business decision.

### 5.5 Inbox lifecycle and the processed-file ledger

New table (migration `0004`):

```sql
CREATE TABLE processed_files (
  sha256      TEXT NOT NULL,
  source_id   TEXT NOT NULL,
  file_name   TEXT NOT NULL,
  first_run   TEXT NOT NULL,
  last_run    TEXT NOT NULL,
  rows_read   INTEGER NOT NULL DEFAULT 0,
  outcome     TEXT NOT NULL,     -- PROCESSED | FAILED | SUPERSEDED
  PRIMARY KEY (sha256, source_id)
);
```

Run behaviour becomes:

1. Discover matching files in the inbox (now optionally recursive).
2. Skip any file whose `sha256` is already `PROCESSED` for that source — unless
   `reprocess_identical: true`.
3. Process the rest.
4. **On success**, apply the configured `after_run` policy:

```jsonc
"inbox": {
  "after_run": "archive",     // archive | keep | delete
  "archive_folder": "Processed",
  "archive_keep_days": 90,
  "recursive": false,
  "ignore_suffixes": [".tmp", ".part", ".crdownload"]
}
```

`archive` is the default: the file moves to `Data/Processed/<YYYY-MM>/`, so the inbox
stays empty, each run reads exactly what is new, and the operator can still find any
source file. This single change removes the O(n²) growth and makes the "total from your
files" figure meaningful again.

### 5.6 Cadence and scheduling — genuinely no terminal

Two supported modes, both without admin rights:

**Mode 1 — the app is open (watched folder).** Already exists; hardened per C2/C3.

**Mode 2 — scheduled, app closed.** A new `SCHEDULE.bat` ships at the operator-package
root. Double-clicking it presents plain choices (daily at a time, hourly, weekdays only,
off) and registers a **per-user** `schtasks` job invoking
`Application\runtime\pythonw.exe Application\app\launch.py --run-once --quiet`.
No elevation, no service, no machine-wide change — the same constraint set as `START.bat`.

Supporting changes:

- `engine/runlock.py` — an OS-level lock file in `Data/`, so the interactive app and a
  scheduled run can never open the warehouse simultaneously. A scheduled run that finds
  the app running defers and records `SKIPPED_LOCKED`.
- A scheduled run with no new files exits `0` with `NO_NEW_DATA` — a normal quiet day, not
  a failure.
- Every scheduled run appends to `Data/run_history.json`, which the web app renders as a
  cadence timeline, so the operator can see at a glance that yesterday ran and today has
  not yet.

The package verifier gains a matching gate: `SCHEDULE.bat` must not invoke elevation, a
package manager, system Python, or a network call — the same rules `START.bat` already
passes.

### 5.7 Self-healing, and knowing when to stop

The engine should absorb the routine and escalate the genuine. Explicit ladder:

| Situation | Behaviour |
|---|---|
| Header moved, column renamed, columns reordered, new column added | **Absorb.** Resolve, record in the drift report, run `PASS`/`WARNING`. |
| Total/subtotal/banner/section rows | **Absorb.** Classify, exclude, and use as an extra proof. |
| File arrives late, or not at all | **Absorb.** `NO_NEW_DATA`, keep the last good result, no alarm. |
| File locked / mid-write / transient IO | **Retry** with backoff (3 attempts), then alert. |
| Required column cannot be resolved at any rung | **BLOCK**, business language, name the columns found vs expected, keep last good. |
| Ambiguous column match (two equal candidates) | **BLOCK.** Never guess a trusted mapping. |
| Row volume outside the configured band | **BLOCK.** Very likely a truncated export. |
| Subtotal does not equal the data it covers | **BLOCK.** The file disagrees with itself. |
| Reconciliation or control total fails | **BLOCK** (already). |
| New KPI / new business meaning / new decision required | **Escalate to a human owner** — this is the only class that legitimately needs the adaptation agent, and it is a business change, not a technical one. |

Every BLOCK writes an alert (§C7) and preserves the last approved dashboard.

### 5.8 Config contract delta

New keys, all optional and defaulted so **every existing `project.json` keeps working**:

```jsonc
{
  "sources": [{
    "sheet": "Sales | Sales* | auto",
    "header_row": 1,                     // now a hint
    "header_search_rows": 25,
    "column_order": "unstable",          // unstable | stable  (gates rung 5)
    "columns": [{
      "source": "Amount",
      "aliases": ["Total Amount", "Net Amount", "المبلغ", "القيمة"],
      "match": "auto"                    // auto | exact
    }],
    "structure": { /* §5.3 */ },
    "volume":    { "expected_rows_min": null,
                   "expected_rows_max": null,
                   "max_row_change_percent": null },
    "cumulative": false
  }],
  "inbox":      { /* §5.5 */ },
  "automation": {
    "watch_folder": "",
    "process_on_start": false,
    "check_every_minutes": 10,
    "schedule": { "mode": "off", "at": "06:00", "days": "mon-fri" },
    "on_failure": { "alert_file": true, "email": null },
    "retry": { "attempts": 3, "backoff_seconds": 30 }
  }
}
```

`PROJECT_TOOL doctor` gains a **dry-run structural probe**: point it at a representative
file and it reports the sheet it chose, the header row it found, how every column
resolved and at which rung, which rows it classified as non-data, and the row-volume band
it would recommend — before a single row is merged.

---

## 6. Design: a 2026 system, not another patch layer

The instruction I am taking from you: the current page is ugly, and I should apply the
best current design thinking rather than nudge the existing CSS. Given D2 — 39 duplicated
selectors and a patch block that overrides the base — **another patch layer is exactly
the wrong move.** The stylesheet gets rebuilt once, as a token-driven system.

Current references converge on the same principles for enterprise analytics in 2026:
minimalist surfaces with a warm neutral base, ruthless removal of chart junk, a
card-based metric strip of 4–6 KPIs over a flexible content grid, generous negative space
used deliberately as a grouping device, 14–16 px body type with real weight hierarchy,
accessible palettes, and a layout organised around the user's decision rather than around
the data model.

### 6.1 Foundations

- **One token layer.** Every colour, space, radius, shadow, and type step is a custom
  property defined once on `:root`, with dark values redefined in exactly one place. No
  selector may be declared twice. Enforced by a lint step in the test suite, so D2 cannot
  recur.
- **Type scale.** A real modular scale (12 / 13 / 15 / 18 / 22 / 30 / 44), body at 15 px,
  and **tabular lining numerals everywhere a figure appears** (`font-variant-numeric:
  tabular-nums`) so columns align. Fixes D4: the executive number becomes the largest
  element; an exception message never outranks it.
- **Palette.** A warm neutral ground instead of today's cold blue-grey wash; one
  restrained brand accent; semantic colours reserved strictly for status (good / watch /
  action). A categorical series ramp chosen for both light and dark and checked for
  deuteranopia. Status is never colour-only — always colour + shape + text.
- **Elevation.** Two levels only: flat bordered surfaces for content, one soft shadow for
  things that float (tooltip, sticky bar). Today's uniform 22 px radius plus shadow on
  every block is what produces D8's card soup.
- **Density.** Desktop gets a genuinely denser grid; the current layout wastes vertical
  space on chrome. Mobile keeps the air.

### 6.2 Page architecture — organised around the decision

```
┌ Command bar ── report name · run status · updated · theme · lang · save · print
├ Answer band ── the one number that matters + movement + one-line verdict
├ Signal strip ── 3–5 evidence-backed signals, each a link into the detail
├ Filter bar  ── sticky, collapsed to a summary chip row until opened
├ KPI strip   ── 4–6 cards, value + delta + sparkline, one visual language
├ Drivers     ── trend across full width, contributors beneath in a 12-column grid
├ Detail      ── searchable, sortable, virtualised tables
└ Assurance   ── plain-language "what we checked", with the technical table collapsed
```

Specific fixes carried by this structure: the trust card is **deleted** (D3); wizard step
numbers are removed from the exported copy (D5); the raw reconciliation table moves
behind a disclosure (P2), replaced by sentences like *"Every row in your file is
accounted for. The 3 subtotal rows in the file matched the data above them."*

### 6.3 Charts

- Fix the viewBox/`preserveAspectRatio` handling so plots fill their card; compute the
  band and bar geometry from the measured container, not a fixed 640 px (D6).
- Baseline-only axis, gridlines at 25 % opacity, no vertical gridlines, direct labelling
  on the last point of a line instead of a separate legend where it fits (D7).
- One accent for a single series; the categorical ramp only when a split genuinely exists.
- Every chart keeps its existing "Table" alternative — that accessibility affordance is
  already right and stays.
- Sparkline microcopy fixed: no comparison period means **no sparkline** (D9).

### 6.4 Icons and motion

Replace the text glyphs (D10) with a small inline-SVG set on a 20 px grid, single stroke
weight, inherited `currentColor`. Motion limited to 120–160 ms opacity/transform on
hover and disclosure, fully removed under `prefers-reduced-motion`.

### 6.5 What is preserved

Offline-first (no web fonts, no CDN, no network), the standalone single-file export, RTL
and Arabic, dark mode, keyboard and focus behaviour, print styles, and the hand-rolled
SVG charts (correct choice for a zero-dependency offline package — the problem is the
execution, not the approach).

### 6.6 Method

I will produce **two full-page visual mockups** rendered from the real generated
`dashboard.json`, at desktop and mobile, in light and dark, for your approval **before**
any CSS is rewritten — so you are choosing a look, not reading a description.

---

## 7. Test and acceptance gates

New suites, all offline and deterministic:

| Suite | Proves |
|---|---|
| `tests/test_structure.py` | totals mid-block, trailing grand total, banner rows, section headers, blank separators, footers — for each: correct classification, correct exclusion, correct arithmetic proof |
| `tests/test_resilience.py` | header moved 1/3/5 rows, column renamed, columns reordered, column added, column removed, Arabic headers, unit suffixes — each resolves or blocks cleanly, never silently wrong |
| `tests/test_ledger.py` | ten consecutive daily runs read only what is new; inbox archives correctly; identical file is a no-op; row counts do not compound |
| `tests/test_unattended.py` | partial-write file is not ingested; watcher queues instead of dropping; retries then alerts; run lock blocks a concurrent run; no-new-data exits 0 |
| `tests/test_scale.py` | 1 M rows within a declared time and memory budget |
| `tests/test_duckdb.py` | **the entire existing suite re-run on DuckDB** |
| `tests/test_design_tokens.py` | no duplicated CSS selector; every colour comes from a token; contrast ratios pass AA in both themes |
| `tests/test_browser.py` | extended: light **and** dark, 1440/1024/768/420, RTL, no overflow, no page errors, **and an explicit assertion that the report title is visible against its background** (D1 would have been caught by this) |

Two release rules I would like added to the product authority:

1. **No proof by tautology.** A check that compares the system against itself is not
   evidence. Every control total must have at least one independent source.
2. **Two-backend truth.** No capability may be described as proven until it has run on
   the backend the operator package actually ships.

---

## 8. Sequencing

| Phase | Content | Depends on | Rough size |
|---|---|---|---|
| **A** | Trustworthy numbers (P0-1, money, unique, atomic publish) | — | largest single correctness block |
| **B** | Resilient ingestion (auto-header, alias ladder, drift report) | A2's excluded-row ledger | large |
| **C** | Unattended operation (ledger, inbox lifecycle, scheduling, lock, alerts) | B | medium-large |
| **D** | Scale + DuckDB truth | A3 (typing) | medium |
| **E** | Design system rebuild + mockups | independent — **can start in parallel** | medium |

Phase E has no dependency on A–D and can run alongside. If you want something visible
early, E first is reasonable; if you want the risk killed first, A first.

I recommend **A, then E in parallel with B, then C, then D.** A is where the product is
currently making a promise it cannot keep, and E is where you are currently unhappy.

---

## 9. Decisions I need from you before starting

1. **Scope.** Everything above, or Phase A only to start?
2. **Order.** Correctness first (A), or design first (E) so you see progress sooner?
3. **Total-row policy.** When a detected subtotal disagrees with the data above it — BLOCK the run (safe, my recommendation) or WARN and publish?
4. **Fuzzy matching.** Should rung 4 (token-set ≥ 0.9) be enabled by default, or opt-in per project? Default-on absorbs more drift; opt-in is more conservative.
5. **Inbox default.** `archive` (my recommendation), `keep`, or `delete` after a successful run?
6. **Scheduling.** Is `schtasks` per-user registration acceptable in your corporate environment, or is the watched-folder mode the only realistic path?
7. **Failure alerts.** Local alert file only (fully offline), or should optional SMTP be built now?
8. **Design.** Two mockups for approval before any CSS is written — confirm, and tell me if there is a corporate palette or font I must respect.
9. **DuckDB.** Can you supply the approved Windows DuckDB binary for `runtime_inputs/`? Without it, the production backend stays unproven no matter what the tests say.
10. **Protected workbooks.** Does any real source need the Excel COM route? That path can only be proven on your Windows machine with a real protected file.

---

## Appendix — evidence

- `docs/review/edge_case_repro.py` — generates the three fixtures used for P0-1 and P0-3. Run it, then `PROJECT_TOOL run` against each folder to reproduce the results quoted above.
- Baseline: commit 1 of this branch is the unmodified V14 template.
- Suite at baseline: 166 passed, 1 skipped. With Playwright + Chromium installed: 167 passed, 0 skipped — including `test_browser.py`, while D1 is present.

**Sources for §6:**
[Dashboard Design Principles: The Definitive Guide (2026) — UXPin](https://www.uxpin.com/studio/blog/dashboard-design-principles/) ·
[Dashboard Design Guide 2026: Principles & Best Practices](https://createbytes.com/insights/ultimate-guide-dashboard-design-best-practices) ·
[Dashboard Design Patterns for Modern Web Apps 2026](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/) ·
[Dashboard Design Trends 2026: Which Ones Actually Matter](https://fuselabcreative.com/top-dashboard-design-trends-2025/) ·
[50 Best Dashboard Design Examples for 2026 — Muzli](https://muz.li/blog/best-dashboard-design-examples-inspirations-for-2026/) ·
[Power BI Dashboard Design: 12 Best Practices for 2026](https://www.aufaitux.com/blog/power-bi-dashboard-design-best-practices/)

---

**I am stopping here as you asked. No engine file has been modified. Nothing starts until you approve §9.**
