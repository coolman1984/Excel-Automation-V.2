"""Filterable pre-aggregations.

The dashboard has to answer "what about only Retail, only in March?" without
becoming a second calculation engine. So the engine pre-aggregates the trusted
facts once, into a small cube of (date bucket x dimension values) cells holding
additive measures. The browser then *sums cells* - it never re-derives a formula.

That distinction is the whole design:

* additive measures (sum, count) filter exactly, because a sum of sums is a sum;
* a ratio filters exactly too, as long as both of its parts are additive and the
  division happens after the filtering;
* a distinct count cannot be filtered this way at all, so it is refused here and
  stays a whole-population metric.
"""

from __future__ import annotations

import dataclasses
import os
from decimal import Decimal

from engine.data import types
from engine.errors import user_error

GRAINS = {"day", "week", "month", "quarter", "year"}
AGGREGATES = {"sum", "count", "ratio"}
MAX_CELLS = 50000


@dataclasses.dataclass
class Measure:
    id: str
    title: str
    aggregate: str
    field: str = ""
    format: str = "number"
    unit: str = ""
    numerator: str = ""
    denominator: str = ""
    goal_direction: str = "up"

    @property
    def is_ratio(self) -> bool:
        return self.aggregate == "ratio"


@dataclasses.dataclass
class Dimension:
    id: str
    title: str
    field: str


def _bucket(value: str, grain: str) -> str:
    """Turn an ISO date into the label for its period."""

    text = str(value)[:10]
    year, month, day = text[:4], text[5:7], text[8:10]
    if grain == "year":
        return year
    if grain == "quarter":
        return f"{year}-Q{(int(month) - 1) // 3 + 1}"
    if grain == "month":
        return f"{year}-{month}"
    if grain == "week":
        import datetime as _dt

        iso = _dt.date(int(year), int(month), int(day)).isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return text


def parse(config) -> dict | None:
    """Read and check the ``analytics`` block. Returns None when absent."""

    raw = config.raw.get("analytics")
    if not raw:
        return None

    allowed = {"fact_sql", "from", "date", "dimensions", "measures", "charts", "kpis", "notes"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise user_error("E-CFG-004", next_action=f"Remove {unknown} from 'analytics'.",
                         detail=f"allowed: {sorted(allowed)}")

    date = raw.get("date") or {}
    grain = date.get("grain", "month")
    if grain not in GRAINS:
        raise user_error("E-CFG-003", next_action=f"analytics.date.grain must be one of {sorted(GRAINS)}.",
                         detail=f"found {grain!r}")
    if not date.get("field"):
        raise user_error("E-CFG-003", next_action="Add analytics.date.field - the column that dates a row.",
                         detail="analytics.date")

    dimensions = []
    for index, entry in enumerate(raw.get("dimensions", [])):
        field = entry.get("field")
        if not field:
            raise user_error("E-CFG-003", next_action=f"analytics.dimensions[{index}] needs a 'field'.",
                             detail=str(entry))
        dimensions.append(Dimension(id=entry.get("id", field), title=entry.get("title", field),
                                    field=field))

    measures: list[Measure] = []
    for index, entry in enumerate(raw.get("measures", [])):
        aggregate = entry.get("aggregate", "sum")
        if aggregate not in AGGREGATES:
            hint = ("A distinct count cannot be filtered from pre-aggregations. Keep it as a "
                    "metric in the metrics SQL file instead."
                    if "distinct" in str(aggregate) else f"Use one of {sorted(AGGREGATES)}.")
            raise user_error("E-CFG-003",
                             next_action=f"analytics.measures[{index}].aggregate: {hint}",
                             detail=f"found {aggregate!r}")
        measure = Measure(
            id=entry.get("id") or entry.get("field", f"measure_{index}"),
            title=entry.get("title", entry.get("field", "")),
            aggregate=aggregate,
            field=entry.get("field", ""),
            format=entry.get("format", "number"),
            unit=entry.get("unit", ""),
            numerator=entry.get("numerator", ""),
            denominator=entry.get("denominator", ""),
            goal_direction=entry.get("goal_direction", "up"))
        if aggregate == "sum" and not measure.field:
            raise user_error("E-CFG-003",
                             next_action=f"analytics.measures[{index}] needs the column to add up.",
                             detail=str(entry))
        measures.append(measure)

    known = {m.id for m in measures}
    for measure in measures:
        if not measure.is_ratio:
            continue
        missing = [part for part in (measure.numerator, measure.denominator) if part not in known]
        if missing:
            raise user_error(
                "E-CFG-003",
                next_action=(f"Measure '{measure.id}' divides {measure.numerator} by "
                             f"{measure.denominator}; both must be measures defined above it."),
                detail=f"unknown: {missing}")
        for part in (measure.numerator, measure.denominator):
            source = next(m for m in measures if m.id == part)
            if source.is_ratio:
                raise user_error(
                    "E-CFG-003",
                    next_action=f"Measure '{measure.id}' may only divide two additive measures.",
                    detail=f"'{part}' is itself a ratio")

    dimension_ids = {d.id for d in dimensions}
    for index, chart in enumerate(raw.get("charts", [])):
        if chart.get("measure") not in known:
            raise user_error("E-CFG-003",
                             next_action=f"analytics.charts[{index}].measure must be one of {sorted(known)}.",
                             detail=str(chart))
        by = chart.get("by", "date")
        if by != "date" and by not in dimension_ids:
            raise user_error("E-CFG-003",
                             next_action=(f"analytics.charts[{index}].by must be 'date' or one of "
                                          f"{sorted(dimension_ids)}."), detail=str(chart))
        form = chart.get("form", "bar")
        if form not in ("line", "bar", "stacked", "donut"):
            raise user_error("E-CFG-003",
                             next_action=f"analytics.charts[{index}].form must be line, bar, stacked or donut.",
                             detail=str(chart))
        if chart.get("split") and chart["split"] not in dimension_ids:
            raise user_error("E-CFG-003",
                             next_action=f"analytics.charts[{index}].split must be one of {sorted(dimension_ids)}.",
                             detail=str(chart))
    for kpi in raw.get("kpis", []):
        if kpi not in known:
            raise user_error("E-CFG-003", next_action=f"analytics.kpis must name measures: {sorted(known)}.",
                             detail=str(kpi))

    return {"raw": raw, "date_field": date["field"], "grain": grain,
            "date_title": date.get("title", "Period"), "dimensions": dimensions,
            "measures": measures}


def fact_sql(config, spec: dict) -> str:
    inline = spec["raw"].get("from")
    if inline:
        return f"SELECT * FROM {inline}"
    path = os.path.join(config.root, spec["raw"].get("fact_sql", "sql/fact.sql"))
    if not os.path.isfile(path):
        raise user_error("E-SQL-001",
                         next_action=f"Create {path}: one SELECT returning the rows to analyse.",
                         detail="analytics.fact_sql")
    with open(path, "r", encoding="utf-8") as handle:
        statement = "\n".join(line for line in handle.read().splitlines()
                              if not line.strip().startswith("--"))
    statement = statement.strip().rstrip(";").strip()
    if not statement.lower().startswith(("select", "with")):
        raise user_error("E-SQL-001", next_action=f"{path} must be a SELECT (or WITH ... SELECT).",
                         detail=statement[:200])
    return statement


def build(connection, config, spec: dict) -> dict:
    """Run the fact query once and fold it into the cube the browser filters."""

    statement = fact_sql(config, spec)
    try:
        cursor = connection.execute(statement)
        rows = cursor.fetchall()
    except Exception as exc:
        raise user_error("E-SQL-001",
                         next_action="Fix the analytics fact query; it must read the trusted views.",
                         detail=str(exc)) from exc
    columns = [description[0] for description in (cursor.description or [])]

    required = [spec["date_field"]] + [d.field for d in spec["dimensions"]]
    required += [m.field for m in spec["measures"] if m.field]
    missing = sorted({name for name in required if name not in columns})
    if missing:
        raise user_error(
            "E-SQL-001",
            next_action=f"The analytics fact query must also return {missing}.",
            detail=f"it returned {columns}")

    dimensions = spec["dimensions"]
    additive = [m for m in spec["measures"] if not m.is_ratio]
    values: list[dict[str, int]] = [{} for _ in dimensions]
    order: list[list[str]] = [[] for _ in dimensions]
    cells: dict[tuple, list[Decimal]] = {}
    periods: set[str] = set()

    for row in rows:
        raw_date = row[spec["date_field"]]
        if raw_date is None:
            continue
        period = _bucket(raw_date, spec["grain"])
        periods.add(period)
        key_parts: list[int] = []
        for index, dimension in enumerate(dimensions):
            label = row[dimension.field]
            label = "—" if label is None or str(label).strip() == "" else str(label)
            if label not in values[index]:
                values[index][label] = len(order[index])
                order[index].append(label)
            key_parts.append(values[index][label])
        key = (period, tuple(key_parts))
        bucket = cells.setdefault(key, [Decimal(0) for _ in additive])
        for position, measure in enumerate(additive):
            if measure.aggregate == "count":
                bucket[position] += 1
                continue
            value = row[measure.field]
            if value is not None:
                bucket[position] += Decimal(str(value))
        if len(cells) > MAX_CELLS:
            raise user_error(
                "E-CFG-003",
                what_happened="This report asks for more detail than a browser can filter quickly.",
                next_action=("Use a wider date grain, or remove a dimension with very many values, "
                             "in analytics."),
                detail=f"more than {MAX_CELLS} combinations")

    def number(value: Decimal) -> float | int:
        as_float = float(value)
        return int(as_float) if as_float.is_integer() else round(as_float, 6)

    payload_cells = [
        {"p": period, "k": list(key), "m": [number(v) for v in measures]}
        for (period, key), measures in sorted(cells.items(), key=lambda item: (item[0][0], item[0][1]))
    ]

    return {
        "grain": spec["grain"],
        "date_title": spec["date_title"],
        "periods": sorted(periods),
        "dimensions": [{"id": d.id, "title": d.title, "values": order[index]}
                       for index, d in enumerate(dimensions)],
        "measures": [dataclasses.asdict(m) for m in spec["measures"]],
        "additive": [m.id for m in additive],
        "cells": payload_cells,
        "charts": spec["raw"].get("charts", []),
        "kpis": spec["raw"].get("kpis", [m.id for m in spec["measures"]]),
        "rows": len(rows),
    }


def totals(payload: dict) -> dict[str, float]:
    """Whole-population totals - used to prove the cube against the metrics."""

    additive = payload["additive"]
    sums = {measure_id: Decimal(0) for measure_id in additive}
    for cell in payload["cells"]:
        for index, measure_id in enumerate(additive):
            sums[measure_id] += Decimal(str(cell["m"][index]))
    result = {key: float(value) for key, value in sums.items()}
    for measure in payload["measures"]:
        if measure["aggregate"] == "ratio":
            denominator = result.get(measure["denominator"], 0)
            result[measure["id"]] = (result.get(measure["numerator"], 0) / denominator
                                     if denominator else None)
    return result


def verify(connection, config, spec: dict, payload: dict) -> list[tuple[str, str, str, str]]:
    """Prove the cube against a second, independent pass over the same facts.

    If a row were dropped while folding the facts into cells, every filtered
    number in the browser would be quietly wrong. So the totals are recomputed
    straight from the fact query and compared.
    """

    statement = fact_sql(config, spec)
    additive = [m for m in spec["measures"] if not m.is_ratio]
    parts = ["COUNT(*) AS row_count"]
    for measure in additive:
        if measure.aggregate == "count":
            parts.append(f'COUNT(*) AS "{measure.id}"')
        else:
            parts.append(f'SUM("{measure.field}") AS "{measure.id}"')
    date_field = spec["date_field"]
    row = connection.execute(
        f'SELECT {", ".join(parts)} FROM ({statement}) AS facts '
        f'WHERE "{date_field}" IS NOT NULL').fetchone()

    checks: list[tuple[str, str, str, str]] = []
    cube_totals = totals(payload)
    cells_rows = sum(1 for _ in payload["cells"])
    checks.append(("analytics_cells", f"{row['row_count']} dated fact rows",
                   f"{cells_rows} pre-aggregated cells",
                   "PASS" if cells_rows <= (row["row_count"] or 0) else "BLOCK"))
    for measure in additive:
        expected = Decimal(str(row[measure.id] or 0))
        actual = Decimal(str(cube_totals.get(measure.id, 0)))
        difference = expected - actual
        def show(value: Decimal) -> str:
            if measure.aggregate == "count":
                return str(int(value))
            return str(Decimal(types.scaled(value, 2)) / Decimal(100))

        checks.append((
            f"analytics_total_{measure.id}", show(expected), show(actual),
            "PASS" if abs(types.scaled(difference, 6)) == 0 else "BLOCK"))
    return checks
