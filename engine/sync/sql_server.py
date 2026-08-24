"""Optional SQL Server mirror of locally trusted data.

The local warehouse remains the calculation authority.  Synchronization runs
only after a locally verified result exists, uses credentials supplied through
an environment variable, reconciles row counts, and may fail without forcing
Excel to be extracted again.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os
import re
from typing import Any

from engine.db import database

_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclasses.dataclass
class SyncResult:
    enabled: bool = False
    status: str = "DISABLED"       # DISABLED | PASS | PENDING
    message: str = "SQL Server synchronization is disabled."
    rows: int = 0
    tables: list[dict] = dataclasses.field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _ident(value: str) -> str:
    if not _SAFE.match(value):
        raise ValueError(f"unsafe SQL Server identifier: {value!r}")
    return f"[{value}]"


def _sql_type(kind: str) -> str:
    return {
        "text": "NVARCHAR(4000)",
        "date": "NVARCHAR(32)",
        "datetime": "NVARCHAR(40)",
        "number": "DECIMAL(38,10)",
        "integer": "BIGINT",
        "boolean": "BIT",
    }.get(kind, "NVARCHAR(4000)")


def settings(config) -> dict:
    raw = config.sql_server or {}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "connection_string_env": str(raw.get("connection_string_env", "UEA_SQLSERVER_CONNECTION")),
        "schema": str(raw.get("schema", "dbo")),
        "table_prefix": str(raw.get("table_prefix", config.project_name + "__")),
        "batch_rows": max(100, int(raw.get("batch_rows", 2000))),
        "sources": list(raw.get("sources", [])),
    }


def _record(local, run_id: str, result: SyncResult) -> None:
    try:
        local.execute(
            "INSERT OR REPLACE INTO sync_events(run_id, target, status, at, detail_json) "
            "VALUES (?,?,?,?,?)",
            (run_id, "sql_server", result.status,
             _dt.datetime.now().isoformat(timespec="seconds"),
             json.dumps(result.to_dict(), ensure_ascii=False, default=str)))
    except Exception:
        pass


def sync(config, local, run_id: str) -> SyncResult:
    cfg = settings(config)
    if not cfg["enabled"]:
        result = SyncResult()
        _record(local, run_id, result)
        return result

    result = SyncResult(enabled=True, status="PENDING",
                        message="Local result is trusted; SQL Server synchronization is pending.")
    conn_text = os.environ.get(cfg["connection_string_env"], "").strip()
    if not conn_text:
        result.error = f"environment variable {cfg['connection_string_env']} is not set"
        _record(local, run_id, result)
        return result
    try:
        import pyodbc  # type: ignore
    except ImportError:
        result.error = "pyodbc is not bundled"
        _record(local, run_id, result)
        return result

    selected = set(cfg["sources"] or [source.id for source in config.sources])
    schema = cfg["schema"]
    if not _SAFE.match(schema):
        result.error = "unsafe schema name"
        _record(local, run_id, result)
        return result

    remote = None
    try:
        remote = pyodbc.connect(conn_text, autocommit=False, timeout=15)
        cursor = remote.cursor()
        cursor.fast_executemany = True
        cursor.execute("SET XACT_ABORT ON")
        for source in config.sources:
            if source.id not in selected:
                continue
            table_name = cfg["table_prefix"] + source.id
            if not _SAFE.match(table_name):
                raise ValueError(f"unsafe table name {table_name!r}")
            full = f"{_ident(schema)}.{_ident(table_name)}"
            columns = ["_bk", "_version", "_last_run"] + [c.field for c in source.columns]
            type_map = {"_bk": "NVARCHAR(512)", "_version": "BIGINT",
                        "_last_run": "NVARCHAR(100)"}
            type_map.update({c.field: _sql_type(c.type) for c in source.columns})
            definition = ", ".join(f"{_ident(name)} {type_map[name]} NULL" for name in columns)
            create = (
                f"IF OBJECT_ID(N'{schema}.{table_name}', N'U') IS NULL BEGIN "
                f"CREATE TABLE {full} ({definition}, CONSTRAINT {_ident('PK_' + table_name)} "
                f"PRIMARY KEY ({_ident('_bk')})); END")
            cursor.execute(create)

            local_rows = local.execute(
                f"SELECT _bk, _version, _last_run, "
                f"{', '.join(database.quote(c.field) for c in source.columns)} "
                f"FROM {database.quote('hist__' + source.id)} WHERE _status = 'active'").fetchall()
            temp = "#uea_stage"
            cursor.execute(f"IF OBJECT_ID('tempdb..{temp}') IS NOT NULL DROP TABLE {temp}")
            cursor.execute(f"CREATE TABLE {temp} ({definition})")
            placeholders = ", ".join("?" for _ in columns)
            insert_sql = f"INSERT INTO {temp} ({', '.join(_ident(c) for c in columns)}) VALUES ({placeholders})"
            batch = []
            for row in local_rows:
                batch.append(tuple(row[column] for column in columns))
                if len(batch) >= cfg["batch_rows"]:
                    cursor.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                cursor.executemany(insert_sql, batch)

            # Discrete UPDATE/INSERT/DELETE is intentionally used instead of MERGE.
            # It is easier to reason about under concurrency and follows Microsoft's
            # current guidance for straightforward synchronization workloads.
            updates = ", ".join(f"target.{_ident(c)} = source.{_ident(c)}" for c in columns if c != "_bk")
            cursor.execute(
                f"UPDATE target SET {updates} FROM {full} AS target "
                f"INNER JOIN {temp} AS source ON target.{_ident('_bk')} = source.{_ident('_bk')}")
            insert_cols = ", ".join(_ident(c) for c in columns)
            select_cols = ", ".join(f"source.{_ident(c)}" for c in columns)
            cursor.execute(
                f"INSERT INTO {full} ({insert_cols}) SELECT {select_cols} FROM {temp} AS source "
                f"WHERE NOT EXISTS (SELECT 1 FROM {full} AS target "
                f"WHERE target.{_ident('_bk')} = source.{_ident('_bk')})")
            # This mirror is a full active snapshot of the local trusted history.
            # Therefore deletion of rows absent from staging is deliberate and safe.
            cursor.execute(
                f"DELETE target FROM {full} AS target WHERE NOT EXISTS "
                f"(SELECT 1 FROM {temp} AS source WHERE source.{_ident('_bk')} = target.{_ident('_bk')})")
            remote_count = cursor.execute(f"SELECT COUNT(*) FROM {full}").fetchone()[0]
            if int(remote_count) != len(local_rows):
                raise RuntimeError(
                    f"row-count reconciliation failed for {table_name}: local={len(local_rows)} remote={remote_count}")
            result.rows += len(local_rows)
            result.tables.append({"source_id": source.id, "table": f"{schema}.{table_name}",
                                  "rows": len(local_rows), "status": "PASS"})
        remote.commit()
        result.status = "PASS"
        result.message = f"SQL Server synchronized successfully ({result.rows:,} trusted rows)."
        result.error = ""
    except Exception as exc:
        if remote is not None:
            try:
                remote.rollback()
            except Exception:
                pass
        result.status = "PENDING"
        result.message = "Local result is trusted; SQL Server synchronization will need a retry."
        result.error = str(exc)
    finally:
        if remote is not None:
            try:
                remote.close()
            except Exception:
                pass
        _record(local, run_id, result)
    return result
