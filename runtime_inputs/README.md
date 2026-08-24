# Private Windows runtime inputs — V13

The final user installs **nothing**. The operator ZIP carries a private Windows runtime under
`Application/runtime/`. Offline means **no runtime downloads**.

## Required base

Use an approved Python 3.11+ Windows private/embeddable runtime prepared on an internet-enabled
build machine, then place the finished folder at:

```text
runtime_inputs/python-windows/python.exe
runtime_inputs/python-windows/pythonw.exe
```

## Bundle dependencies according to the project

| Capability | Runtime requirement |
|---|---|
| Production local warehouse | DuckDB package + native binary |
| Protected Excel via `excel_com` | `pywin32` (`win32com`, `pythoncom`, `pywintypes`) + Microsoft Excel installed/authorized on target PC |
| SQL Server sync enabled | `pyodbc` + approved Microsoft ODBC driver on the target environment |
| Direct `.xlsx` / `.csv` | built-in engine, no additional parser package |
| Dashboard | bundled HTML/CSS/JS, no CDN |

Prepare these dependencies **before** delivery using the company-approved offline build process.
Do not run `pip`, download wheels, or install software on the final user's machine.

## Prepare the build runtime

On an approved build machine with internet access:

```bash
python tools/prepare_windows_runtime.py
```

On a closed build machine, place the four pinned archives listed in
`windows_runtime_manifest.json` inside `runtime_inputs/downloads/` and run:

```bash
python tools/prepare_windows_runtime.py --offline
```

The preparation tool verifies SHA-256 before extracting anything. The agent template ZIP includes
the prepared `runtime_inputs/python-windows/` automatically when that folder exists.

## Delivery

```bash
python PROJECT_TOOL.py deliver --project projects/<name> --output-dir release \
       --runtime runtime_inputs/python-windows
```

The package verifier checks the project configuration and blocks delivery when a required runtime
capability is absent. This is deliberate: a pretty ZIP that fails on the employee's PC is not a
product, merely a compressed apology.
