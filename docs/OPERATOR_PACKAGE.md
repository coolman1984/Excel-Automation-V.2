# The operator package

What the business user receives, and the contract that keeps it simple.

## The only shape allowed

```text
ProjectName/
    START.bat
    QUICK_START.html
    Application/
        app/          engine, project configuration, page assets
        runtime/      the private Python runtime
        Data/         database, results, logs, archive (created on first start)
```

Nothing else may be visible at the root. No source folder, no tests, no Git, no
wheelhouse, no build tools, no configuration editor, no README full of commands.

## Building it

```bash
# one command: stage, package and verify
python PROJECT_TOOL.py deliver --project projects/AcmeSales --output-dir release \
       --runtime runtime_inputs/python-windows

# or the two stages separately
python PROJECT_TOOL.py app stage --project projects/AcmeSales --out build/AcmeSales \
       --runtime runtime_inputs/python-windows
python PROJECT_TOOL.py package build --project-name AcmeSales --app-dir build/AcmeSales \
       --output-dir release
python PROJECT_TOOL.py package verify --zip release/AcmeSales.zip
```

## What the verifier refuses

| Refused | Why |
|---|---|
| An unexpected entry at the package root | The user must see three things, not a repository |
| A missing `START.bat`, `QUICK_START.html` or `Application/` | The journey breaks |
| A missing `Application/app/launch.py` | Nothing would start |
| A missing private runtime | The user would have to install Python |
| A developer folder inside `Application/` (`tests`, `.git`, `wheelhouse`, `docs`, …) | Machinery must stay hidden |
| A missing project configuration | The application would have nothing to run |
| `START.bat` invoking pip, conda, winget, Git, curl, PowerShell downloads, `netsh`, `runas`, a system Python or Node | The package must never install, download or elevate |
| An unsafe path inside the ZIP (`..`, absolute, drive letter) | Extraction must be safe |
| More than one folder in the ZIP | One package, one folder |

Every rule above is covered by a test in `tests/test_packaging.py`.

## What happens when the user double-clicks `START.bat`

1. `START.bat` checks that `Application/app/launch.py` and the private runtime
   exist. If not, it prints a plain-language message with support code
   `E-PKG-001` and stops.
2. It starts `Application/runtime/pythonw.exe Application/app/launch.py`
   (`python.exe` if the quiet build is absent).
3. `launch.py` asks the operating system for a **free loopback port**, starts the
   local application on `127.0.0.1`, generates a one-time session key and opens
   the browser at that address.
4. The user adds files on the page and presses Process.

No firewall rule, no URL reservation, no Windows service, no administrator
prompt, no machine-wide installation, no internet.

## Data and updates

- Everything the run produces lives in `Application/Data/`: the database, the
  published dashboard, the archive, the logs, the exports.
- To keep the history when delivering a new version, copy `Application/Data/`
  from the old folder into the new one before the first start.
- To start clean, delete `Application/Data/`; it is recreated automatically.

## Offline means no downloads, not no dependencies

The package contains everything it needs. It uses no internet connection at any
point, including the first start. It does need the private runtime that ships
inside it - which is why `package verify` refuses to build a package without it.
