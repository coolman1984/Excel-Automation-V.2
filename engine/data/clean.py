"""Typed clean data, quality checks and quarantine.

Rows that fail an agreed rule are never silently dropped: they are written to
the ``quarantine`` table with the file, the Excel row number, the rule and a
plain-language message, and they stay visible in the application.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import re

from engine.data import types
from engine.data.staging import stage_table
from engine.db import database
from engine.errors import user_error

LINEAGE_COLUMNS = [("_run_id", "TEXT"), ("_file", "TEXT"), ("_row_no", "INTEGER"),
                   ("_row_hash", "TEXT"), ("_bk", "TEXT")]


@dataclasses.dataclass
class CleanResult:
    source_id: str
    rows_in: int
    rows_clean: int
    rows_rejected: int
    rows_filtered: int
    warnings: int


def clean_table(source_id: str) -> str:
    return f"clean__{source_id}"


def _business_key(source, values: dict) -> str:
    if not source.business_key:
        return ""
    parts = []
    for field in source.business_key:
        value = values.get(field)
        parts.append("" if value is None else str(value).strip().lower())
    return "|".join(parts)


def _row_hash(source, values: dict) -> str:
    import hashlib

    payload = json.dumps({c.field: values.get(c.field) for c in source.columns},
                         sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _quarantine(connection, run_id: str, source_id: str, file_name: str, excel_row: int,
                rule: str, field: str, message: str, severity: str, payload: dict) -> None:
    connection.execute(
        "INSERT INTO quarantine(run_id, source_id, file_name, excel_row, rule, field, message,"
        " severity, row_json) VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, source_id, file_name, excel_row, rule, field, message, severity,
         json.dumps(payload, default=str, ensure_ascii=False)))


def clean(connection, run_id: str, source) -> CleanResult:
    """Type the staged rows, apply the configured checks, fill the clean table."""

    target = clean_table(source.id)
    database.drop_table(connection, target)
    database.create_table(
        connection, target,
        LINEAGE_COLUMNS + [(c.field, database.SQL_TYPE[c.type]) for c in source.columns])
    columns = [c[0] for c in LINEAGE_COLUMNS] + [c.field for c in source.columns]

    staged = connection.execute(f"SELECT * FROM {database.quote(stage_table(source.id))}").fetchall()
    accepted: list[list[object]] = []
    rejected = 0
    filtered = 0
    warnings = 0
    seen_keys: dict[str, int] = {}

    for row in staged:
        raw = {c.field: row[c.field] for c in source.columns}
        values: dict[str, object] = {}
        failure: tuple[str, str] | None = None
        for column in source.columns:
            text = raw[column.field]
            if (text is None or str(text).strip() == "") and column.default is not None:
                text = str(column.default)
            try:
                value = types.parse(text, column.type, column.date_formats)
            except types.ParseError as exc:
                failure = (column.field, str(exc))
                break
            if value is None and column.required:
                failure = (column.field, f"'{column.source}' is required but empty")
                break
            values[column.field] = value
        if failure:
            rejected += 1
            _quarantine(connection, run_id, source.id, row["_file"], row["_row_no"],
                        "type_or_required", failure[0], failure[1], "reject", raw)
            continue

        excluded_by = _filter_reason(source, values)
        if excluded_by:
            filtered += 1
            connection.execute(
                "INSERT OR REPLACE INTO filtered_rows(run_id, source_id, file_name, excel_row,"
                " reason) VALUES (?,?,?,?,?)",
                (run_id, source.id, row["_file"], row["_row_no"], excluded_by))
            continue

        key = _business_key(source, values)
        if source.business_key and key in seen_keys:
            rejected += 1
            _quarantine(connection, run_id, source.id, row["_file"], row["_row_no"],
                        "duplicate_business_key", ", ".join(source.business_key),
                        f"This record is already in the same file at row {seen_keys[key]}.",
                        "reject", raw)
            continue
        if source.business_key:
            seen_keys[key] = row["_row_no"]

        accepted.append([run_id, row["_file"], row["_row_no"], _row_hash(source, values), key]
                        + [values.get(c.field) for c in source.columns])

    if accepted:
        database.insert_many(connection, target, columns, accepted)

    extra_rejected, extra_warnings = _run_checks(connection, run_id, source, target)
    rejected += extra_rejected
    warnings += extra_warnings

    rows_clean = int(database.scalar(connection, f"SELECT COUNT(*) FROM {database.quote(target)}") or 0)
    return CleanResult(source_id=source.id, rows_in=len(staged), rows_clean=rows_clean,
                       rows_rejected=rejected, rows_filtered=filtered, warnings=warnings)


def _filter_reason(source, values: dict) -> str:
    """``filters`` keep only the rows the business considers in scope.

    Returns the reason a row is out of scope, or an empty string when it stays.
    """

    for rule in source.filters:
        field = rule.get("field")
        value = values.get(field)
        operator = rule.get("operator", "equals")
        target = rule.get("value")
        excluded = (
            (operator == "equals" and value != target)
            or (operator == "not_equals" and value == target)
            or (operator == "in" and value not in (target or []))
            or (operator == "not_in" and value in (target or []))
            or (operator == "not_null" and value is None)
        )
        if excluded:
            return f"{field} {operator} {target!r}"
    return ""


def _range_message(field: str, value, check: dict) -> str:
    low, high = check.get("min"), check.get("max")
    if low is not None and high is not None:
        limit = f"between {low} and {high}"
    elif low is not None:
        limit = f"at least {low}"
    else:
        limit = f"no more than {high}"
    return f"'{field}' is {value}, but it must be {limit}."


def _fetch(connection, table: str, where: str, params=()):
    return connection.execute(
        f"SELECT * FROM {database.quote(table)} WHERE {where}", params).fetchall()


def _reject_rows(connection, run_id, source, table, rows, rule, field, message_for, severity):
    count = 0
    for row in rows:
        payload = {c.field: row[c.field] for c in source.columns}
        _quarantine(connection, run_id, source.id, row["_file"], row["_row_no"], rule, field,
                    message_for(row), severity, payload)
        if severity == "reject":
            connection.execute(
                f"DELETE FROM {database.quote(table)} WHERE _file = ? AND _row_no = ?",
                (row["_file"], row["_row_no"]))
        count += 1
    return count


def _run_checks(connection, run_id: str, source, table: str) -> tuple[int, int]:
    rejected = 0
    warnings = 0
    for check in source.checks:
        kind = check["type"]
        on_fail = check.get("on_fail", "quarantine")
        severity = "reject" if on_fail == "quarantine" else ("block" if on_fail == "block" else "warning")
        field = check.get("field", "")
        label = check.get("message")
        rows: list = []
        rule_field = field

        if kind in ("not_null", "not_blank"):
            clause = f"{database.quote(field)} IS NULL"
            if kind == "not_blank":
                clause += f" OR TRIM(CAST({database.quote(field)} AS TEXT)) = ''"
            rows = _fetch(connection, table, clause)
            message = lambda row, f=field: label or f"'{f}' is empty."
        elif kind == "range":
            clauses, params = [], []
            if check.get("min") is not None:
                clauses.append(f"{database.quote(field)} < ?")
                params.append(check["min"])
            if check.get("max") is not None:
                clauses.append(f"{database.quote(field)} > ?")
                params.append(check["max"])
            if not clauses:
                continue
            rows = _fetch(connection, table, " OR ".join(clauses), params)
            message = lambda row, f=field, c=check: label or _range_message(f, row[f], c)
        elif kind == "allowed_values":
            allowed = check.get("values", [])
            placeholders = ", ".join("?" for _ in allowed) or "NULL"
            rows = _fetch(connection, table,
                          f"{database.quote(field)} IS NOT NULL AND "
                          f"{database.quote(field)} NOT IN ({placeholders})", allowed)
            message = lambda row, f=field, a=allowed: label or (
                f"'{f}' is '{row[f]}', which is not one of {a}.")
        elif kind == "not_future":
            today = _dt.date.today().isoformat()
            rows = _fetch(connection, table, f"{database.quote(field)} > ?", (today,))
            message = lambda row, f=field: label or f"'{f}' is in the future ({row[f]})."
        elif kind == "regex":
            pattern = re.compile(check.get("pattern", ".*"))
            rows = [row for row in _fetch(connection, table, f"{database.quote(field)} IS NOT NULL")
                    if not pattern.fullmatch(str(row[field]))]
            message = lambda row, f=field: label or f"'{f}' has an unexpected format ('{row[f]}')."
        elif kind == "unique":
            fields = check.get("fields") or [field]
            rule_field = ", ".join(fields)
            key = ", ".join(database.quote(f) for f in fields)
            duplicates = connection.execute(
                f"SELECT {key} FROM {database.quote(table)} GROUP BY {key} HAVING COUNT(*) > 1"
            ).fetchall()
            rows = []
            for duplicate in duplicates:
                clause = " AND ".join(f"{database.quote(f)} IS ?" for f in fields)
                rows.extend(_fetch(connection, table, clause, tuple(duplicate)))
            message = lambda row, f=rule_field: label or f"More than one row has the same {f}."
        else:  # pragma: no cover - config validation already rejects this
            continue

        if not rows:
            continue
        if on_fail == "block":
            raise user_error(
                "E-VAL-001",
                next_action=(check.get("next_action")
                             or f"Correct the '{rule_field}' values in the source file and process again."),
                trusted_data_safe=True,
                detail=f"{source.id}: check '{kind}' on '{rule_field}' failed for {len(rows)} row(s).",
            )
        count = _reject_rows(connection, run_id, source, table, rows, kind, rule_field,
                             message, severity)
        if severity == "reject":
            rejected += count
        else:
            warnings += count
    return rejected, warnings
