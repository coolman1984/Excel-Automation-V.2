"""Build and verify the dashboard document.

``dashboard.json`` is the only thing the browser reads. It contains approved
results and pre-aggregations - never a formula the browser has to evaluate.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
from typing import Any

from engine.errors import user_error

SCHEMA_VERSION = 1
ATTENTION_LIMIT = 500


def build(config, result, payloads: list[dict], highlights: list[dict], checks,
          connection, run_id: str, status: str, analytics: dict | None = None) -> dict:
    by_id = {payload["id"]: payload for payload in payloads}
    layout = config.dashboard or {}

    def selected(kind: str, key: str) -> list[dict]:
        wanted = layout.get(key)
        if wanted is None:
            return [p for p in payloads if p.get("kind") == kind]
        chosen = []
        for entry in wanted:
            metric_id = entry if isinstance(entry, str) else entry.get("metric")
            payload = by_id.get(metric_id)
            if payload is None:
                raise user_error(
                    "E-CFG-003",
                    next_action=f"Dashboard '{key}' refers to metric '{metric_id}', which is not "
                                f"defined in the project metrics SQL file.",
                    detail=f"available metrics: {sorted(by_id)}")
            if isinstance(entry, dict):
                payload = {**payload, **{k: v for k, v in entry.items() if k != "metric"}}
            chosen.append(payload)
        return chosen

    attention = [dict(row) for row in connection.execute(
        "SELECT source_id, file_name, excel_row, rule, field, message, severity, row_json"
        " FROM quarantine WHERE run_id = ? ORDER BY file_name, excel_row LIMIT ?",
        (run_id, ATTENTION_LIMIT))]
    for row in attention:
        try:
            row["values"] = json.loads(row.pop("row_json"))
        except (ValueError, KeyError):
            row["values"] = {}
    attention_total = int(connection.execute(
        "SELECT COUNT(*) FROM quarantine WHERE run_id = ?", (run_id,)).fetchone()[0])

    # This run is still marked RUNNING in the table (its row is updated at the end of the
    # transaction), so it is described from the result rather than re-read.
    previous = [{"run_id": run_id, "started_at": result.started_at,
                 "finished_at": result.finished_at, "status": status,
                 "rows_clean": result.rows_clean, "rows_rejected": result.rows_rejected,
                 "message": result.message}]
    previous += [dict(row) for row in connection.execute(
        "SELECT run_id, started_at, finished_at, status, rows_clean, rows_rejected, message"
        " FROM runs WHERE run_id <> ? ORDER BY started_at DESC LIMIT 19", (run_id,))]

    rejected = int(getattr(result, "rows_rejected", 0) or 0)
    read = int(getattr(result, "rows_in", 0) or 0)
    accepted_rate = round(((read - rejected) / read * 100), 1) if read else 100.0
    passed_checks = sum(1 for c in checks if c.status == "PASS")
    decision = {
        "action_count": sum(1 for i in highlights if i.get("severity") == "action"),
        "watch_count": sum(1 for i in highlights if i.get("severity") == "watch"),
        "signal_count": len(highlights),
        "acceptance_rate": accepted_rate,
        "checks_passed": passed_checks,
        "checks_total": len(checks),
        "top_signal": highlights[0] if highlights else None,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "project": {
            "name": config.project_name,
            "title": config.title,
            "language": config.language,
            "purpose": config.business.get("purpose", ""),
            "decision": config.business.get("decision_supported", ""),
            "run_frequency": config.business.get("run_frequency", ""),
            "approved_by": config.approval.get("approved_by", ""),
        },
        "run": {
            "run_id": run_id,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "status": status,
            "state": getattr(result, "state", "COMPLETE"),
            "database_backend": getattr(result, "database_backend", ""),
            "message": result.message,
            "rows": {"read": result.rows_in, "accepted": result.rows_clean,
                     "needs_attention": result.rows_rejected, "out_of_scope": result.rows_filtered},
            "files": result.files,
        },
        "kpis": [_kpi(payload) for payload in selected("kpi", "kpis")],
        # Every KPI the engine calculated, displayed or not - the evidence a
        # golden test and a reviewer check against.
        "metrics": [{"id": payload["id"], "title": payload.get("title", ""),
                     "value": _clean_number(payload.get("value")),
                     "format": payload.get("format", "number"),
                     "unit": payload.get("unit", "")}
                    for payload in payloads if payload.get("kind") == "kpi"],
        "charts": [_chart(payload) for payload in selected("series", "charts")],
        "tables": [_table(payload) for payload in selected("table", "tables")],
        "analytics": analytics,
        "insights": highlights,
        "reconciliation": [
            {"source_id": c.source_id, "check": c.name, "expected": c.expected,
             "actual": c.actual, "difference": c.difference, "status": c.status}
            for c in checks],
        "sources": result.sources,
        "attention": {"total": attention_total, "shown": len(attention), "rows": attention},
        "history": previous,
        "enterprise_sync": getattr(result, "enterprise_sync", {}) or {},
        "decision": decision,
    }


def _clean_number(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if value.is_integer() and abs(value) < 1e15:
            return int(value)
        return round(value, 6)
    return value


def _kpi(payload: dict) -> dict:
    return {
        "id": payload["id"],
        "title": payload.get("title", payload["id"]),
        "subtitle": payload.get("subtitle", ""),
        "value": _clean_number(payload.get("value")),
        "format": payload.get("format", "number"),
        "unit": payload.get("unit", ""),
        "evidence": payload.get("evidence", {}),
    }


def _chart(payload: dict) -> dict:
    return {
        "id": payload["id"],
        "title": payload.get("title", payload["id"]),
        "kind": payload.get("chart", "bar"),
        "format": payload.get("format", "number"),
        "unit": payload.get("unit", ""),
        "points": [{"label": str(point.get("label")), "value": _clean_number(point.get("value")),
                    "series": point.get("series")}
                   for point in payload.get("points", [])],
        "evidence": payload.get("evidence", {}),
    }


def _table(payload: dict) -> dict:
    return {
        "id": payload["id"],
        "title": payload.get("title", payload["id"]),
        "columns": payload.get("columns", []),
        "rows": [[_clean_number(cell) for cell in row] for row in payload.get("rows", [])],
        "evidence": payload.get("evidence", {}),
    }


def verify(document: dict, payloads: list[dict]) -> None:
    """Fail the run before publishing if the document is not trustworthy."""

    required = ("schema_version", "project", "run", "kpis", "charts", "tables", "reconciliation")
    missing = [key for key in required if key not in document]
    if missing:
        raise user_error("E-RUN-001", next_action="Report this support code.",
                         detail=f"dashboard is missing {missing}")

    source_values = {p["id"]: _clean_number(p.get("value")) for p in payloads
                     if p.get("kind") == "kpi"}
    for kpi in document["kpis"]:
        expected = source_values.get(kpi["id"], "__missing__")
        if expected == "__missing__":
            raise user_error("E-RUN-001", next_action="Report this support code.",
                             detail=f"dashboard KPI '{kpi['id']}' has no calculated value")
        if kpi["value"] != expected:
            raise user_error(
                "E-RUN-001",
                what_happened="A dashboard number did not match the calculated value, so nothing "
                              "was published.",
                next_action="Process again. If it repeats, send the support code to your support "
                            "contact.",
                detail=f"{kpi['id']}: dashboard={kpi['value']!r} calculated={expected!r}")

    try:
        json.dumps(document, default=str)
    except (TypeError, ValueError) as exc:
        raise user_error("E-RUN-001", next_action="Report this support code.",
                         detail=f"dashboard is not serialisable: {exc}") from exc
