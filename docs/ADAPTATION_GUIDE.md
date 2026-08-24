# Adaptation guide

The long version of `PROJECT_SKILL.md`. Read this only if the context pack did
not answer your question.

## Step 0 - understand what you were given

A chat session receives three things:

1. `Project-Template.zip` - this repository, already finished and tested;
2. the customer's Excel files (or small samples of them);
3. a plain explanation of what they do by hand today.

You return exactly one thing: `<ProjectName>.zip`.

Nothing in the engine needs to be written again. If you find yourself designing
a pipeline, a reader or a dashboard, you have taken the expensive path.

## Step 1 - look at the files before asking anything

```bash
python - <<'PY'
from engine.excel.xlsx_reader import Workbook, read_block
book = Workbook("their_file.xlsx")
print(book.sheet_names)
headers, rows = read_block("their_file.xlsx", book.sheet_names[0], max_rows=5)
print(headers)
for row in rows: print(row)
PY
```

Now you can ask better questions: you already know the tabs, the headings and
what the first rows look like.

## Step 2 - confirm the business meaning

Use `.ai/BUSINESS_QUESTIONS.md`. Summarise the answers back in one short block
and get a yes. Anything you did not get an answer for stays `PENDING_APPROVAL`
in `project.json`; the engine refuses to publish until it is resolved, which is
the behaviour you want.

## Step 3 - create the project

```bash
python PROJECT_TOOL.py new-project AcmeSales
```

This copies `projects/_template/`. Then fill in `project.json` using
`.ai/CONTEXT_PACK.md` section 3 and `projects/example_sales/project.json` as the
worked example.

Fill it in this order - each answer decides the next:

1. `sources[].match` - what the files are called;
2. `sources[].sheet` and `header_row` - where the table starts;
3. `sources[].columns` - only the columns the business actually uses;
4. `sources[].grain` - one sentence, in their words;
5. `sources[].business_key` - what makes two rows "the same record";
6. `corrections_allowed` and `missing_record_policy`;
7. `control_totals` - the number they check by hand today;
8. `checks` - the rules they already apply mentally;
9. `filters` - rows they exclude on purpose;
10. `relationships` - how the sources join.

Run `doctor` after each block of edits. It is fast and it names the exact path
of a mistake:

```bash
python PROJECT_TOOL.py doctor --project projects/AcmeSales
```

## Step 4 - write the trusted calculations

Edit `projects/AcmeSales/sql/metrics.sql`. Every metric is one SELECT against
`v_<source_id>`. Start with the totals the business already checks, then add the
breakdowns they asked for. Keep each metric small and readable - it is the
evidence a person will be asked to trust.

Then list them in `dashboard`, in the order they should be read.

## Step 5 - prove it with their own numbers

```bash
python PROJECT_TOOL.py run --project projects/AcmeSales --inbox ./their_files --verbose
```

Check, in this order:

1. `status` is `PASS` or `WARNING` (never deliver on `BLOCK`);
2. every `control_total_*` check is `PASS` with difference `0`;
3. the KPI values equal the numbers the business owner produces by hand;
4. the quarantined rows are the ones they would also have rejected;
5. run it a second time - `new_records` must be `0`.

Record the agreed values in `projects/AcmeSales/tests/golden.json` and put a
small, safe sample in `projects/AcmeSales/fixtures/` so the next session can
re-prove the result without the customer's real data.

## Step 6 - deliver

```bash
python PROJECT_TOOL.py deliver --project projects/AcmeSales --output-dir release \
       --runtime runtime_inputs/python-windows
```

The output must end with `RESULT: PASS`. Hand over `release/AcmeSales.zip` and
fill in `.ai/ADAPTATION_REPORT.md`.

## When configuration genuinely is not enough

Follow the order and stop at the first level that works:

| Level | Example | Cost |
|---|---|---|
| 1. Configuration | a new column, a new rule, a different key | minutes |
| 2. Project SQL | a margin calculation, a ranking, a comparison to last month | minutes |
| 3. Project-owned Python | a genuinely procedural transformation SQL cannot express | hours, and it must live in `projects/<name>/` only |
| 4. Shared engine change | a new source format every customer will need | days, needs evidence and tests |

Before touching `engine/`, write down: what is needed, why configuration and SQL
cannot express it, and which customers other than this one would use it. If you
cannot write those three lines convincingly, the change belongs at level 1-3.

Any shared-engine change must keep every existing test passing and add a test of
its own.
