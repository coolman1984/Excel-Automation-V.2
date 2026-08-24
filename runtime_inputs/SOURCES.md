# Pinned Windows runtime sources

The private Windows x64 runtime is built from immutable, SHA-256-pinned artifacts listed in
`windows_runtime_manifest.json`.

- CPython 3.11.9 embeddable x64 — official Python release archive.
- DuckDB 1.5.5 for CPython 3.11 Windows x64 — PyPI wheel.
- pywin32 312 for CPython 3.11 Windows x64 — PyPI wheel.
- pyodbc 5.3.0 for CPython 3.11 Windows x64 — PyPI wheel.

The preparation tool verifies every downloaded byte before extraction. Package licenses and notices
from the wheels remain inside the expanded private runtime. Microsoft Excel is not redistributed;
it must already exist on a PC that uses the COM extraction mode. A Microsoft SQL Server ODBC driver
is likewise an environment prerequisite only when SQL Server synchronization is enabled.
