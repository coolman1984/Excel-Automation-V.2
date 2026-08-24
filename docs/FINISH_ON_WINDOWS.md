# Final Windows qualification — V13

The engine is adapted once; the final business user installs nothing. This checklist proves the
specific private runtime and customer environment before broad delivery.

## 1. Prepare the private runtime

On an approved build machine with internet access:

```bat
python tools\prepare_windows_runtime.py
```

Or, on a closed build machine, copy the four pinned archives named in
`runtime_inputs\windows_runtime_manifest.json` into `runtime_inputs\downloads\` and run:

```bat
python tools\prepare_windows_runtime.py --offline
```

Expected folder:

```text
runtime_inputs\python-windows\
    python.exe
    pythonw.exe
    duckdb\...
    win32com\...
    pywin32_system32\...
    pyodbc*.pyd
    UEA_RUNTIME_MANIFEST.json
```

The preparation tool verifies SHA-256 and never installs packages machine-wide.

## 2. Run the full regression suite

```bat
python PROJECT_TOOL.py test
```

All normal tests must pass. A browser test may skip only if its browser tooling is genuinely absent;
a skip is not evidence of browser proof.

## 3. Prove the example package

```bat
python PROJECT_TOOL.py deliver --project projects\example_sales --output-dir release ^
  --runtime runtime_inputs\python-windows
```

Expected: `RESULT: PASS`. Extract the ZIP, double-click `START.bat`, process the supplied example
fixtures, and confirm the golden totals in `projects\example_sales\tests\golden.json`.

Turn the network off and process again. The same trusted totals must appear and identical data must
not duplicate history.

## 4. Prove DuckDB on the packaged runtime

Create/adapt a project with:

```json
"database": {"backend": "duckdb"}
```

Run `doctor`, deliver it with the private runtime, then complete a real run from the extracted ZIP.
The run result must report `database_backend = duckdb` and produce the same trusted controls as the
source evidence.

## 5. Prove protected Excel COM when applicable

For a real protected corporate workbook that normally opens only through the authorized Excel
session:

```json
"extraction": {"mode": "excel_com", "chunk_rows": 5000, "visible": false}
```

On the target Windows PC:

1. Log in as the approved user.
2. Confirm Microsoft Excel can open the workbook normally.
3. Close Excel.
4. Process the workbook through the delivered application.
5. Confirm the source hash is retained, source remains byte-for-byte unchanged, row/control totals
   reconcile, and Excel closes after the run.

Do not claim protected-file support from fixtures or direct `.xlsx` parsing.

## 6. Prove SQL Server only when enabled

The target environment must already have the approved Microsoft ODBC Driver for SQL Server. Set the
connection string in the configured environment variable, then process a run and confirm:

- local trusted publication completes first;
- synchronization is `PASS`;
- SQL Server row counts reconcile to local active trusted rows;
- disabling SQL Server/network makes sync `PENDING` while the local trusted report remains usable;
- retrying synchronization does not require re-extracting Excel.

If SQL Server is disabled for the project, this gate is not applicable.

## 7. Non-technical handoff proof

A representative end user must complete:

1. extract ZIP and double-click START;
2. two routine processing runs;
3. one deliberately recoverable failure and successful recovery;
4. filtering, insight review, export/print of the dashboard.

The user must not need a terminal, Git, system Python/Node, package installation, internet, admin
rights, manual ports, or technical database knowledge.

## 8. Build the reusable master template ZIP

After the private runtime is prepared, run:

```bat
python tools\make_template_zip.py
```

The builder now includes `runtime_inputs\python-windows\` when it exists, so the next adaptation
agent receives the reusable engine **and** the private Windows build runtime. This is the preferred
fully self-contained master-template handoff.

## Failure rule

Never weaken a test, verifier, control total, or dependency gate to obtain a green result. Fix the
cause. A failed run preserves the last-good output by design.
