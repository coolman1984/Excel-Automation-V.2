"""Exact reconciliation.

Two questions must have a provable answer after every run:

* did every row from the file end somewhere (clean, quarantined or filtered)?
* does every control total still add up, to the last agreed decimal?

Totals are compared as integer minor units, so 0.1 + 0.2 can never drift.
"""

from __future__ import annotations

import dataclasses
import json
from decimal import Decimal

from engine.data import types
from engine.data.clean import clean_table
from engine.data.staging import stage_table
from engine.db import database


@dataclasses.dataclass
class Check:
    source_id: str
    name: str
    expected: str
    actual: str
    difference: str
    status: str          # PASS | WARNING | BLOCK

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def _decimal(text: object) -> Decimal | None:
    if text is None or str(text).strip() == "":
        return None
    try:
        return types.parse_decimal(str(text))
    except types.ParseError:
        return None


def run(connection, run_id: str, source, history_result=None) -> list[Check]:
    checks: list[Check] = []
    staged = connection.execute(
        f"SELECT * FROM {database.quote(stage_table(source.id))}").fetchall()
    clean_rows = connection.execute(
        f"SELECT * FROM {database.quote(clean_table(source.id))}").fetchall()

    clean_keys = {(row["_file"], row["_row_no"]) for row in clean_rows}
    rejected_keys = {
        (row["file_name"], row["excel_row"]) for row in connection.execute(
            "SELECT file_name, excel_row FROM quarantine WHERE run_id = ? AND source_id = ?"
            " AND severity = 'reject'", (run_id, source.id))
    }

    filtered_keys = {
        (row["file_name"], row["excel_row"]) for row in connection.execute(
            "SELECT file_name, excel_row FROM filtered_rows WHERE run_id = ? AND source_id = ?",
            (run_id, source.id))
    }

    rows_in = len(staged)
    rows_clean = len(clean_keys)
    rows_rejected = len({key for key in rejected_keys if key not in clean_keys})
    rows_filtered = len(filtered_keys - clean_keys)
    # Any row that is not accepted, rejected or deliberately excluded has been lost.
    unaccounted = [row for row in staged
                   if (row["_file"], row["_row_no"]) not in clean_keys
                   and (row["_file"], row["_row_no"]) not in rejected_keys
                   and (row["_file"], row["_row_no"]) not in filtered_keys]
    actual = f"{rows_clean} accepted + {rows_rejected} rejected + {rows_filtered} out of scope"
    if unaccounted:
        actual += f" + {len(unaccounted)} unaccounted"
    checks.append(Check(
        source_id=source.id, name="row_population",
        expected=f"{rows_in} rows read",
        actual=actual,
        difference=str(len(unaccounted)),
        status="PASS" if not unaccounted else "BLOCK"))

    for total in source.control_totals:
        field = total["field"]
        precision = int(total.get("precision", 2))
        tolerance = types.scaled(Decimal(str(total.get("tolerance", "0"))), precision)

        file_total = Decimal(0)
        buckets = {"clean": Decimal(0), "rejected": Decimal(0), "filtered": Decimal(0)}
        for row in staged:
            value = _decimal(row[field]) or Decimal(0)
            file_total += value
            key = (row["_file"], row["_row_no"])
            if key in clean_keys:
                buckets["clean"] += value
            elif key in rejected_keys:
                buckets["rejected"] += value
            elif key in filtered_keys:
                buckets["filtered"] += value
            # An unaccounted row contributes to the file total but to no bucket,
            # so the difference below cannot stay at zero.

        stored_total = Decimal(0)
        for row in clean_rows:
            stored = row[field]
            if stored is not None:
                stored_total += Decimal(str(stored))

        expected_scaled = types.scaled(file_total, precision)
        parts_scaled = sum(types.scaled(value, precision) for value in buckets.values())
        stored_scaled = types.scaled(stored_total, precision)
        clean_scaled = types.scaled(buckets["clean"], precision)

        status = "PASS"
        if abs(expected_scaled - parts_scaled) > tolerance:
            status = "BLOCK"
        elif abs(clean_scaled - stored_scaled) > tolerance:
            status = "BLOCK"
        checks.append(Check(
            source_id=source.id, name=f"control_total_{field}",
            expected=str(file_total.quantize(Decimal(1).scaleb(-precision))),
            actual=str(stored_total.quantize(Decimal(1).scaleb(-precision))),
            difference=str(Decimal(expected_scaled - parts_scaled).scaleb(-precision)),
            status=status))

    if history_result is not None:
        expected_touched = len(clean_keys)
        # A refused correction is a decision, not a lost row: it is accounted for here and
        # stays visible in quarantine.
        accounted = history_result.touched + history_result.corrections_blocked
        status = "PASS" if accounted == expected_touched else "BLOCK"
        actual = (f"{history_result.inserted} new + {history_result.corrected} corrected + "
                  f"{history_result.unchanged} unchanged")
        if history_result.corrections_blocked:
            actual += f" + {history_result.corrections_blocked} correction(s) refused"
        checks.append(Check(
            source_id=source.id, name="history_applied",
            expected=f"{expected_touched} records merged",
            actual=actual,
            difference=str(expected_touched - accounted),
            status=status))
    return checks


def save(connection, run_id: str, checks: list[Check]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO reconciliation(run_id, source_id, check_name, expected, actual,"
        " difference, status) VALUES (?,?,?,?,?,?,?)",
        [(run_id, c.source_id, c.name, c.expected, c.actual, c.difference, c.status)
         for c in checks])


def relationships(connection, config, run_id: str) -> list[Check]:
    """Verify that the sources still fit together the way the business said."""

    checks: list[Check] = []
    for relationship in config.relationships:
        child = config.source(relationship["child"])
        parent = config.source(relationship["parent"])
        child_fields = relationship.get("child_fields", [])
        parent_fields = relationship.get("parent_fields", child_fields)
        on_missing = relationship.get("on_missing", "warn")
        if not child_fields:
            continue
        join = " AND ".join(
            f"c.{database.quote(cf)} IS p.{database.quote(pf)}"
            for cf, pf in zip(child_fields, parent_fields))
        not_null = " AND ".join(f"c.{database.quote(cf)} IS NOT NULL" for cf in child_fields)
        missing = database.scalar(
            connection,
            f"SELECT COUNT(*) FROM {database.quote(clean_table(child.id))} c "
            f"LEFT JOIN {database.quote(clean_table(parent.id))} p ON {join} "
            f"WHERE {not_null} AND p.ROWID IS NULL") or 0
        status = "PASS" if not missing else ("BLOCK" if on_missing == "block" else "WARNING")
        if on_missing == "ignore":
            status = "PASS"
        checks.append(Check(
            source_id=child.id,
            name=f"link_to_{parent.id}",
            expected=f"every {child.id} row has a matching {parent.id} record",
            actual=f"{missing} row(s) without a match",
            difference=str(missing),
            status=status))
    return checks


def summary(checks: list[Check]) -> str:
    if any(c.status == "BLOCK" for c in checks):
        return "BLOCK"
    if any(c.status == "WARNING" for c in checks):
        return "WARNING"
    return "PASS"


def as_dicts(checks: list[Check]) -> list[dict]:
    return [dataclasses.asdict(c) for c in checks]


def evidence_json(checks: list[Check]) -> str:
    return json.dumps(as_dicts(checks), ensure_ascii=False)
