"""Local analytical database access.

Production packages prefer DuckDB because the workload is analytical and the
project can be large.  A SQLite compatibility fallback remains available for
source-development environments that do not have the DuckDB binary bundled.
The rest of the engine talks only to this module, so business logic never
changes when the storage backend changes.
"""

from __future__ import annotations

import datetime as _dt
import os
import sqlite3
from decimal import Decimal
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from engine.data import types
from engine.logging_setup import logger

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")

# Kept for callers that only need the storage class, not the exact declaration.
SQL_TYPE = {
    "text": "TEXT",
    "number": "DOUBLE",
    "integer": "BIGINT",
    "date": "TEXT",
    "datetime": "TEXT",
    "boolean": "BOOLEAN",
}


def sql_type(backend: str, kind: str, scale: int = types.DEFAULT_SCALE) -> str:
    """The column declaration for a mapped field on this backend.

    DuckDB gets a real DECIMAL, so ``SUM(amount)`` in project SQL is exact. SQLite
    has no decimal type, so the development fallback stores DOUBLE and its SQL sums
    are approximate - see the note on the adapter below. Reconciliation stays exact
    on both, because it reads the staged text and adds in Decimal.
    """

    if kind == "number" and backend == "duckdb":
        return f"DECIMAL({types.TOTAL_DIGITS}, {int(scale)})"
    return SQL_TYPE[kind]


# SQLite cannot store a decimal. Binding one has to lose exactness somewhere, and
# this is that somewhere: it is explicit rather than hidden inside the driver, so
# the development fallback's limit is visible in the code that causes it.
sqlite3.register_adapter(Decimal, float)


class Row(dict):
    """A tiny mapping row that also supports numeric indexing like sqlite.Row."""

    def __init__(self, columns: Sequence[str], values: Sequence[Any]):
        super().__init__(zip(columns, values))
        self._columns = list(columns)
        self._values = list(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        if isinstance(key, slice):
            return self._values[key]
        return super().__getitem__(key)


class Cursor:
    def __init__(self, raw, backend: str, affected: int | None = None):
        self.raw = raw
        self.backend = backend
        self._affected = affected

    @property
    def description(self):
        return getattr(self.raw, "description", None)

    @property
    def rowcount(self) -> int:
        if self._affected is not None:
            return self._affected
        value = getattr(self.raw, "rowcount", -1)
        return value if isinstance(value, int) else -1

    def _columns(self) -> list[str]:
        return [item[0] for item in (self.description or [])]

    def fetchone(self):
        value = self.raw.fetchone()
        if value is None:
            return None
        if isinstance(value, sqlite3.Row):
            return value
        if isinstance(value, Row):
            return value
        return Row(self._columns(), value)

    def fetchall(self):
        values = self.raw.fetchall()
        if not values:
            return []
        if isinstance(values[0], sqlite3.Row):
            return values
        columns = self._columns()
        return [value if isinstance(value, Row) else Row(columns, value) for value in values]

    def __iter__(self) -> Iterator:
        return iter(self.fetchall())


class Connection:
    """Backend-neutral connection with the subset the engine needs."""

    def __init__(self, raw, backend: str):
        self.raw = raw
        self.backend = backend

    def execute(self, sql: str, params: Sequence[object] = ()) -> Cursor:
        statement = _translate(sql, self.backend)
        raw = self.raw.execute(statement, tuple(params))
        return Cursor(raw, self.backend)

    def executemany(self, sql: str, rows: Iterable[Sequence[object]]) -> Cursor:
        materialized = list(rows)
        if not materialized:
            # SQLite treats an empty batch as a silent no-op; DuckDB raises. A
            # source that legitimately produced zero rows (no insights, an
            # optional source with no file this run) must not turn into a run
            # failure only on the production backend.
            return Cursor(None, self.backend, 0)
        statement = _translate(sql, self.backend)
        raw = self.raw.executemany(statement, materialized)
        return Cursor(raw, self.backend, len(materialized))

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self.raw.executescript(script)
            return
        for statement in _split_script(script):
            self.raw.execute(statement)

    def close(self) -> None:
        self.raw.close()


def _split_script(script: str) -> list[str]:
    """Split our migration SQL. Migrations intentionally contain no SQL strings with ';'."""

    statements: list[str] = []
    current: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            current = []
    if current:
        statement = "\n".join(current).strip().rstrip(";").strip()
        if statement:
            statements.append(statement)
    return statements


def _translate(sql: str, backend: str) -> str:
    if backend != "duckdb":
        return sql
    text = sql.strip()
    if text.upper() == "BEGIN IMMEDIATE":
        return "BEGIN TRANSACTION"
    return sql


def _duckdb_module():
    try:
        import duckdb  # type: ignore
    except ImportError:
        return None
    return duckdb


def backend_available(name: str) -> bool:
    if name == "duckdb":
        return _duckdb_module() is not None
    return name == "sqlite"


def connect(path: str, backend: str | None = None) -> Connection:
    """Open the local warehouse.

    ``UEA_DB_BACKEND=duckdb`` is used by production packaging. ``auto`` prefers
    DuckDB when the bundled module exists and otherwise uses SQLite so the
    source template can still be tested on minimal development machines.
    """

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    requested = (backend or "auto").lower()
    if requested == "auto":
        # A project asking for "auto" is deferring the choice, so the environment
        # gets to make it. That is what lets the suite pin a backend and run twice.
        requested = (os.environ.get("UEA_DB_BACKEND") or "auto").lower()
    if requested not in {"auto", "duckdb", "sqlite"}:
        raise ValueError(f"unsupported database backend: {requested}")

    duckdb = _duckdb_module()
    if requested in {"auto", "duckdb"} and duckdb is not None:
        raw = duckdb.connect(path)
        # Conservative local analytics defaults: allow spilling instead of crashing
        # on wide/large workbooks, and keep temporary data beside the private DB.
        # Spilling to disk instead of failing on a wide workbook is the whole point
        # of these settings, so they are applied individually and logged when one is
        # not available. DuckDB's SET takes no bound parameters - passing one used to
        # raise inside a bare except, which silently disabled the spill directory.
        temp_dir = os.path.abspath(path) + ".spill"
        os.makedirs(temp_dir, exist_ok=True)
        for statement in (f"SET temp_directory = '{temp_dir}'",
                          "SET preserve_insertion_order = false"):
            try:
                raw.execute(statement)
            except Exception as exc:  # pragma: no cover - depends on the DuckDB build
                logger().debug("duckdb setting not applied (%s): %s", statement, exc)
        return Connection(raw, "duckdb")
    if requested == "duckdb":
        raise RuntimeError(
            "DuckDB is required by this package but is not bundled. Rebuild the operator package "
            "with the approved DuckDB runtime dependency.")

    raw = sqlite3.connect(path, isolation_level=None, timeout=30.0)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA foreign_keys=ON")
    raw.execute("PRAGMA synchronous=FULL")
    return Connection(raw, "sqlite")


def migrate(connection: Connection) -> list[str]:
    """Apply every migration that has not run yet. Returns applied names."""

    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = {row["name"] for row in connection.execute("SELECT name FROM schema_migrations")}
    applied: list[str] = []
    for name in sorted(os.listdir(MIGRATIONS_DIR)):
        if not name.endswith(".sql") or name in done:
            continue
        with open(os.path.join(MIGRATIONS_DIR, name), "r", encoding="utf-8") as handle:
            connection.executescript(handle.read())
        connection.execute("INSERT INTO schema_migrations(name, applied_at) VALUES (?, ?)",
                           (name, _dt.datetime.now().isoformat(timespec="seconds")))
        applied.append(name)
    return applied


def null_safe_eq(connection: Connection, left: str, right: str) -> str:
    """``left`` equals ``right``, treating NULL as a comparable value.

    SQLite spells this ``a IS b``; DuckDB only accepts the standard
    ``a IS NOT DISTINCT FROM b`` and fails to parse the SQLite form. The engine
    builds these comparisons itself, so it asks here rather than guessing.
    """

    if connection.backend == "duckdb":
        return f"{left} IS NOT DISTINCT FROM {right}"
    return f"{left} IS {right}"


def quote(identifier: str) -> str:
    """Quote an identifier that the engine itself generated from config."""

    safe = "".join(ch for ch in identifier if ch.isalnum() or ch == "_")
    if safe != identifier or not safe:
        raise ValueError(f"unsafe identifier: {identifier!r}")
    return f'"{safe}"'


def create_table(connection: Connection, name: str,
                 columns: Sequence[tuple[str, str]], primary_key: Sequence[str] = ()) -> None:
    parts = [f"{quote(column)} {kind}" for column, kind in columns]
    if primary_key:
        parts.append("PRIMARY KEY (" + ", ".join(quote(c) for c in primary_key) + ")")
    connection.execute(f"CREATE TABLE IF NOT EXISTS {quote(name)} ({', '.join(parts)})")


def drop_table(connection: Connection, name: str) -> None:
    connection.execute(f"DROP TABLE IF EXISTS {quote(name)}")


def insert_many(connection: Connection, table: str, columns: Sequence[str],
                rows: Iterable[Sequence[object]]) -> int:
    materialized = list(rows)
    if not materialized:
        return 0
    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(quote(c) for c in columns)
    connection.executemany(
        f"INSERT INTO {quote(table)} ({column_list}) VALUES ({placeholders})", materialized)
    return len(materialized)


def table_exists(connection: Connection, name: str) -> bool:
    if connection.backend == "duckdb":
        row = connection.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = ? "
            "UNION ALL SELECT 1 FROM information_schema.views WHERE table_name = ? LIMIT 1",
            (name, name)).fetchone()
    else:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?", (name,)
        ).fetchone()
    return row is not None


def scalar(connection: Connection, sql: str, params: Sequence[object] = ()) -> object:
    row = connection.execute(sql, params).fetchone()
    return None if row is None else row[0]
