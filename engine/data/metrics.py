"""Trusted metrics.

The trusted formula exists exactly once: in SQL, against the trusted history
views. The browser never recalculates a KPI - it displays what this module
proved and stored.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re

from engine.data import types
from engine.errors import user_error

_HEADER_RE = re.compile(r"^\s*--\s*metric\s*:\s*(?P<id>[A-Za-z0-9_]+)\s*$", re.IGNORECASE)
_ANNOTATION_RE = re.compile(r"^\s*--\s*(?P<key>[a-z_]+)\s*:\s*(?P<value>.*?)\s*$", re.IGNORECASE)
_ALLOWED_START = ("select", "with")
KINDS = {"kpi", "series", "table"}


@dataclasses.dataclass
class MetricDefinition:
    id: str
    sql: str
    kind: str = "kpi"
    title: str = ""
    subtitle: str = ""
    format: str = "number"
    unit: str = ""
    goal_direction: str = ""      # up | down | flat - used by insights
    notes: str = ""


def parse_file(path: str) -> list[MetricDefinition]:
    """Read a project metrics SQL file into metric definitions."""

    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    definitions: list[MetricDefinition] = []
    current: dict[str, str] | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current, buffer
        if current is None:
            return
        sql = "\n".join(buffer).strip().rstrip(";").strip()
        if not sql:
            raise user_error("E-SQL-001",
                             next_action=f"Add a SELECT statement under '-- metric: {current['id']}'.",
                             detail=path)
        kind = current.get("kind", "kpi").lower()
        if kind not in KINDS:
            raise user_error("E-SQL-001",
                             next_action=f"Use kind kpi, series or table for metric '{current['id']}'.",
                             detail=f"{path}: kind={kind}")
        definitions.append(MetricDefinition(
            id=current["id"], sql=sql, kind=kind,
            title=current.get("title", current["id"].replace("_", " ").title()),
            subtitle=current.get("subtitle", ""),
            format=current.get("format", "number"),
            unit=current.get("unit", ""),
            goal_direction=current.get("goal_direction", ""),
            notes=current.get("notes", "")))
        current, buffer = None, []

    for line in lines:
        header = _HEADER_RE.match(line)
        if header:
            flush()
            current = {"id": header.group("id")}
            buffer = []
            continue
        if current is None:
            continue
        annotation = _ANNOTATION_RE.match(line)
        if annotation and not buffer:
            current[annotation.group("key").lower()] = annotation.group("value")
            continue
        buffer.append(line)
    flush()

    identifiers = [d.id for d in definitions]
    duplicates = sorted({i for i in identifiers if identifiers.count(i) > 1})
    if duplicates:
        raise user_error("E-SQL-001", next_action=f"Rename the duplicate metric id(s) {duplicates}.",
                         detail=path)
    return definitions


def _guard(definition: MetricDefinition) -> None:
    head = re.sub(r"^\s*(--[^\n]*\n)*", "", definition.sql).lstrip().lower()
    if not head.startswith(_ALLOWED_START):
        raise user_error(
            "E-SQL-001",
            next_action=f"Metric '{definition.id}' must be a SELECT (or WITH ... SELECT) query.",
            detail=definition.sql[:200])


def compute(connection, definitions: list[MetricDefinition]) -> list[dict]:
    """Run each metric and return its payload, ready to store and to display."""

    results: list[dict] = []
    for definition in definitions:
        _guard(definition)
        try:
            cursor = connection.execute(definition.sql)
            rows = cursor.fetchall()
        except Exception as exc:  # sqlite3.Error and friends
            raise user_error(
                "E-SQL-001",
                next_action=(f"Fix the SQL for metric '{definition.id}' in the project metrics file."),
                detail=f"{definition.id}: {exc}",
            ) from exc
        columns = [description[0] for description in (cursor.description or [])]
        payload: dict = {
            "id": definition.id,
            "kind": definition.kind,
            "title": definition.title,
            "subtitle": definition.subtitle,
            "format": definition.format,
            "unit": definition.unit,
            "goal_direction": definition.goal_direction,
        }
        if definition.kind == "kpi":
            value = None
            if rows:
                value = rows[0]["value"] if "value" in columns else rows[0][0]
            payload["value"] = types.as_json_number(value)
            payload["evidence"] = {"sql": definition.sql, "rows": len(rows)}
        elif definition.kind == "series":
            payload["points"] = [
                {"label": _label(row, columns),
                 "value": types.as_json_number(_value(row, columns)),
                 "series": row["series"] if "series" in columns else None}
                for row in rows]
            payload["evidence"] = {"sql": definition.sql, "rows": len(rows)}
        else:
            payload["columns"] = columns
            payload["rows"] = [[types.as_json_number(row[column]) for column in columns]
                               for row in rows]
            payload["evidence"] = {"sql": definition.sql, "rows": len(rows)}
        results.append(payload)
    return results


def _label(row, columns: list[str]) -> object:
    return row["label"] if "label" in columns else row[0]


def _value(row, columns: list[str]) -> object:
    return row["value"] if "value" in columns else row[len(columns) - 1]


def save(connection, run_id: str, payloads: list[dict]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO metrics(run_id, metric_id, kind, title, payload_json)"
        " VALUES (?,?,?,?,?)",
        [(run_id, p["id"], p["kind"], p.get("title", ""), json.dumps(p, ensure_ascii=False,
                                                                     default=str))
         for p in payloads])


def load(connection, run_id: str) -> list[dict]:
    return [json.loads(row["payload_json"]) for row in connection.execute(
        "SELECT payload_json FROM metrics WHERE run_id = ? ORDER BY metric_id", (run_id,))]


def kpi_values(payloads: list[dict]) -> dict[str, object]:
    return {p["id"]: p.get("value") for p in payloads if p.get("kind") == "kpi"}
