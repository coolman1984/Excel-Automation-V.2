"""Project configuration - the first place an adaptation is made.

One JSON file per project describes the business meaning: which files arrive,
what a row means, which columns matter, how records are identified, which
totals must reconcile and what the dashboard shows.

The validator is deliberately strict: an unknown or misspelled key fails
immediately with the exact path, so an adaptation agent fixes it in one step
instead of debugging a run.
"""

from __future__ import annotations

import dataclasses
import json
import os
from typing import Any

from engine.data import structure, types
from engine.errors import user_error

FIELD_TYPES = {"text", "number", "integer", "date", "datetime", "boolean"}
CHECK_TYPES = {"not_null", "unique", "range", "allowed_values", "regex", "not_future", "not_blank"}
ON_FAIL = {"quarantine", "block", "warn"}

_SOURCE_KEYS = {
    "id", "title", "required", "match", "format", "sheet", "header_row", "delimiter",
    "grain", "business_key", "corrections_allowed", "missing_record_policy",
    "columns", "checks", "control_totals", "filters", "notes", "extraction",
    "update_mode", "period_field", "structure", "column_order", "header_search_rows",
}
_COLUMN_KEYS = {"source", "field", "type", "required", "trim", "default", "date_formats",
                "notes", "scale", "aliases"}
_ROOT_KEYS = {
    "project_name", "title", "language", "approval", "business", "sources",
    "relationships", "metrics_sql", "dashboard", "analytics", "insights", "quality_gates",
    "automation", "sql_server", "database", "notes", "inbox",
}

_INBOX_KEYS = {"after_run", "archive_folder", "archive_keep_days", "reprocess_identical"}
_INBOX_AFTER_RUN = {"archive", "keep", "delete"}


@dataclasses.dataclass
class Column:
    source: str
    field: str
    type: str = "text"
    required: bool = False
    trim: bool = True
    default: Any = None
    date_formats: list[str] = dataclasses.field(default_factory=list)
    notes: str = ""
    scale: int = types.DEFAULT_SCALE
    aliases: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Source:
    id: str
    title: str
    match: list[str]
    columns: list[Column]
    format: str = "xlsx"
    sheet: Any = None
    header_row: int = 1
    delimiter: str | None = None
    required: bool = True
    grain: str = ""
    business_key: list[str] = dataclasses.field(default_factory=list)
    corrections_allowed: bool = True
    missing_record_policy: str = "keep"
    extraction: dict = dataclasses.field(default_factory=dict)
    structure: dict = dataclasses.field(default_factory=dict)
    column_order: str = "unstable"
    header_search_rows: int = 25
    update_mode: str = "UPSERT"
    period_field: str = ""
    checks: list[dict] = dataclasses.field(default_factory=list)
    control_totals: list[dict] = dataclasses.field(default_factory=list)
    filters: list[dict] = dataclasses.field(default_factory=list)
    notes: str = ""

    def field_names(self) -> list[str]:
        return [column.field for column in self.columns]

    def column_for(self, field: str) -> Column | None:
        for column in self.columns:
            if column.field == field:
                return column
        return None


@dataclasses.dataclass
class ProjectConfig:
    project_name: str
    root: str
    raw: dict
    sources: list[Source]
    title: dict
    language: str = "en"
    approval: dict = dataclasses.field(default_factory=dict)
    business: dict = dataclasses.field(default_factory=dict)
    relationships: list[dict] = dataclasses.field(default_factory=list)
    metrics_sql: str = "sql/metrics.sql"
    dashboard: dict = dataclasses.field(default_factory=dict)
    insights: list[dict] = dataclasses.field(default_factory=list)
    quality_gates: dict = dataclasses.field(default_factory=dict)
    sql_server: dict = dataclasses.field(default_factory=dict)
    database: dict = dataclasses.field(default_factory=dict)
    inbox: dict = dataclasses.field(default_factory=dict)

    # -- helpers -----------------------------------------------------------
    def source(self, source_id: str) -> Source:
        for source in self.sources:
            if source.id == source_id:
                return source
        raise KeyError(source_id)

    @property
    def metrics_sql_path(self) -> str:
        return os.path.join(self.root, self.metrics_sql)

    @property
    def is_approved(self) -> bool:
        return str(self.approval.get("status", "")).upper() == "APPROVED"

    def display_title(self, language: str | None = None) -> str:
        language = language or self.language
        return self.title.get(language) or self.title.get("en") or self.project_name

    def gate(self, name: str, default: Any) -> Any:
        return self.quality_gates.get(name, default)


def _fail(path: str, message: str, action: str, code: str = "E-CFG-003") -> None:
    raise user_error(code, next_action=action, detail=f"{path}: {message}")


def _check_unknown(where: str, data: dict, allowed: set[str]) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail(where, f"unknown setting(s) {unknown}",
              f"Remove {unknown} or fix the spelling. Allowed here: {sorted(allowed)}",
              code="E-CFG-004")


def _require(where: str, data: dict, key: str, kind: type | tuple[type, ...]) -> Any:
    if key not in data:
        _fail(where, f"missing required setting '{key}'", f"Add '{key}' to {where}.")
    value = data[key]
    if not isinstance(value, kind):
        names = kind.__name__ if isinstance(kind, type) else "/".join(k.__name__ for k in kind)
        _fail(where, f"'{key}' must be {names}, found {type(value).__name__}",
              f"Change '{key}' in {where} to {names}.")
    return value


def _parse_column(where: str, data: dict) -> Column:
    _check_unknown(where, data, _COLUMN_KEYS)
    source = _require(where, data, "source", str)
    field = _require(where, data, "field", str)
    kind = data.get("type", "text")
    if kind not in FIELD_TYPES:
        _fail(where, f"type '{kind}' is not supported",
              f"Use one of {sorted(FIELD_TYPES)}.")
    if not field.replace("_", "").isalnum():
        _fail(where, f"field '{field}' must be letters, digits and underscores only",
              "Rename the field; it becomes a database column name.")
    scale = int(data.get("scale", types.DEFAULT_SCALE))
    if not 0 <= scale <= types.MAX_SCALE:
        _fail(where, f"scale {scale} is outside 0..{types.MAX_SCALE}",
              f"Use a scale between 0 and {types.MAX_SCALE} decimal places.")
    if "scale" in data and kind != "number":
        _fail(where, f"scale applies to 'number' columns, not '{kind}'",
              "Remove 'scale', or change the column type to number.")
    aliases = [str(a).strip() for a in data.get("aliases", []) if str(a).strip()]
    return Column(source=source, field=field, type=kind,
                  required=bool(data.get("required", False)),
                  trim=bool(data.get("trim", True)),
                  default=data.get("default"),
                  date_formats=list(data.get("date_formats", [])),
                  notes=str(data.get("notes", "")),
                  scale=scale,
                  aliases=aliases)


def _parse_source(index: int, data: dict) -> Source:
    where = f"sources[{index}]"
    if not isinstance(data, dict):
        _fail(where, "must be an object", "Each entry in 'sources' is an object.")
    _check_unknown(where, data, _SOURCE_KEYS)
    source_id = _require(where, data, "id", str)
    where = f"sources[{source_id}]"
    if not source_id.replace("_", "").isalnum():
        _fail(where, "id must be letters, digits and underscores only",
              "Rename the source id; it becomes a table name.")
    match = data.get("match")
    if isinstance(match, str):
        match = [match]
    if not match or not isinstance(match, list):
        _fail(where, "missing 'match' file pattern(s)",
              "Add \"match\": [\"sales_*.xlsx\"] so the engine can find the file.")
    columns_raw = _require(where, data, "columns", list)
    if not columns_raw:
        _fail(where, "'columns' is empty", "Map at least one column.")
    columns = [_parse_column(f"{where}.columns[{i}]", c) for i, c in enumerate(columns_raw)]
    fields = [column.field for column in columns]
    duplicates = sorted({f for f in fields if fields.count(f) > 1})
    if duplicates:
        _fail(where, f"duplicate field name(s) {duplicates}", "Give every column a unique 'field'.")

    fmt = data.get("format", "xlsx")
    if fmt not in ("xlsx", "csv"):
        _fail(where, f"format '{fmt}' is not supported", "Use \"xlsx\" or \"csv\".")

    business_key = list(data.get("business_key", []))
    unknown_key = [k for k in business_key if k not in fields]
    if unknown_key:
        _fail(where, f"business_key refers to unmapped field(s) {unknown_key}",
              "Map those columns first, or correct the business_key.")

    policy = data.get("missing_record_policy", "keep")
    if policy not in ("keep", "close"):
        _fail(where, f"missing_record_policy '{policy}' is not supported",
              "Use \"keep\" (record simply was not in this file) or \"close\" (record is finished).")

    update_mode = str(data.get("update_mode") or ("SNAPSHOT" if policy == "close" else "UPSERT")).upper()
    if update_mode not in {"APPEND", "UPSERT", "SNAPSHOT", "REPLACE_PERIOD"}:
        _fail(where, f"update_mode '{update_mode}' is not supported",
              "Use APPEND, UPSERT, SNAPSHOT, or REPLACE_PERIOD.")
    period_field = str(data.get("period_field", ""))
    if update_mode == "REPLACE_PERIOD":
        if not period_field:
            _fail(where, "REPLACE_PERIOD needs period_field",
                  "Set period_field to the mapped date/period column that defines the replaced period.")
        if period_field not in fields:
            _fail(where, f"period_field '{period_field}' is not mapped", "Map that column first.")

    extraction = dict(data.get("extraction") or {})
    extraction_mode = str(extraction.get("mode", "auto")).lower()
    if extraction_mode not in {"auto", "direct", "excel_com"}:
        _fail(where, f"extraction.mode '{extraction_mode}' is not supported",
              "Use auto, direct, or excel_com.")

    layout = dict(data.get("structure") or {})
    _check_unknown(f"{where}.structure", layout, structure.SETTING_KEYS)
    unknown_label_fields = [f for f in (layout.get("total_label_fields") or [])
                            if f not in fields]
    if unknown_label_fields:
        _fail(f"{where}.structure",
              f"total_label_fields refers to unmapped field(s) {unknown_label_fields}",
              "Map those columns first, or use their mapped field names.")
    on_mismatch = str(layout.get("on_total_mismatch", "block")).lower()
    if on_mismatch not in {"block", "warn"}:
        _fail(f"{where}.structure", f"on_total_mismatch '{on_mismatch}' is not supported",
              'Use "block" (safest: refuse to publish) or "warn".')
    section_field = layout.get("capture_section_headers_into")
    if section_field and section_field not in fields:
        _fail(f"{where}.structure",
              f"capture_section_headers_into '{section_field}' is not mapped",
              "Map that column first; the section label is written into it.")
    if int(layout.get("stop_after_blank_rows", 0) or 0) < 0:
        _fail(f"{where}.structure", "stop_after_blank_rows cannot be negative",
              "Use 0 to read the whole sheet, or the number of blank rows that ends the data.")

    column_order = str(data.get("column_order", "unstable")).lower()
    if column_order not in {"unstable", "stable"}:
        _fail(where, f"column_order '{column_order}' is not supported",
              'Use "unstable" (default; positions may vary between files) or "stable" '
              '(positions do not change, enabling a positional fallback match).')

    header_search_rows = int(data.get("header_search_rows", 25))
    if header_search_rows < 1:
        _fail(where, "header_search_rows must be at least 1",
              "Set header_search_rows to how many rows from the top of the sheet may "
              "be searched for the real header - 25 is a reasonable default.")

    for position, check in enumerate(data.get("checks", [])):
        location = f"{where}.checks[{position}]"
        kind = check.get("type")
        if kind not in CHECK_TYPES:
            _fail(location, f"check type '{kind}' is not supported", f"Use one of {sorted(CHECK_TYPES)}.")
        if check.get("on_fail", "quarantine") not in ON_FAIL:
            _fail(location, "on_fail must be quarantine, block or warn", "Fix 'on_fail'.")
        targets = check.get("fields") or ([check["field"]] if "field" in check else [])
        missing = [t for t in targets if t not in fields]
        if missing:
            _fail(location, f"check refers to unmapped field(s) {missing}", "Map those columns first.")

    for position, total in enumerate(data.get("control_totals", [])):
        location = f"{where}.control_totals[{position}]"
        field = total.get("field")
        if field not in fields:
            _fail(location, f"control total field '{field}' is not mapped", "Map that column first.")
        column = next(c for c in columns if c.field == field)
        if column.type not in ("number", "integer"):
            _fail(location, f"control total field '{field}' is type '{column.type}'",
                  "Control totals must be number or integer fields.")

    return Source(
        id=source_id,
        title=str(data.get("title", source_id)),
        match=list(match),
        columns=columns,
        format=fmt,
        sheet=data.get("sheet"),
        header_row=int(data.get("header_row", 1)),
        delimiter=data.get("delimiter"),
        required=bool(data.get("required", True)),
        grain=str(data.get("grain", "")),
        business_key=business_key,
        corrections_allowed=bool(data.get("corrections_allowed", True)),
        missing_record_policy=policy,
        extraction=extraction,
        structure=layout,
        column_order=column_order,
        header_search_rows=header_search_rows,
        update_mode=update_mode,
        period_field=period_field,
        checks=list(data.get("checks", [])),
        control_totals=list(data.get("control_totals", [])),
        filters=list(data.get("filters", [])),
        notes=str(data.get("notes", "")),
    )


def load(path: str) -> ProjectConfig:
    """Load and validate ``project.json``."""

    if os.path.isdir(path):
        path = os.path.join(path, "project.json")
    if not os.path.isfile(path):
        raise user_error("E-CFG-001", next_action=f"Create {path} from projects/_template/project.json.",
                         detail=path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise user_error("E-CFG-002",
                         next_action=f"Fix the JSON syntax at line {exc.lineno}, column {exc.colno}.",
                         detail=f"{path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        _fail(path, "the file must contain a JSON object", "Wrap the settings in { }.")

    _check_unknown("project.json", data, _ROOT_KEYS)
    project_name = _require("project.json", data, "project_name", str)
    sources_raw = _require("project.json", data, "sources", list)
    if not sources_raw:
        _fail("project.json", "'sources' is empty", "Describe at least one input file.")
    sources = [_parse_source(i, s) for i, s in enumerate(sources_raw)]
    ids = [s.id for s in sources]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        _fail("project.json", f"duplicate source id(s) {duplicates}", "Give every source a unique id.")

    for position, relationship in enumerate(data.get("relationships", [])):
        location = f"relationships[{position}]"
        for side in ("child", "parent"):
            if relationship.get(side) not in ids:
                _fail(location, f"'{side}' must be one of {ids}", "Correct the source id.")
        child = next(s for s in sources if s.id == relationship["child"])
        parent = next(s for s in sources if s.id == relationship["parent"])
        for field in relationship.get("child_fields", []):
            if field not in child.field_names():
                _fail(location, f"child field '{field}' is not mapped", "Map that column first.")
        for field in relationship.get("parent_fields", []):
            if field not in parent.field_names():
                _fail(location, f"parent field '{field}' is not mapped", "Map that column first.")
        if relationship.get("on_missing", "warn") not in ("warn", "block", "ignore"):
            _fail(location, "on_missing must be warn, block or ignore", "Fix 'on_missing'.")

    title = data.get("title") or {"en": project_name}
    if isinstance(title, str):
        title = {"en": title}

    inbox_raw = dict(data.get("inbox") or {})
    _check_unknown("inbox", inbox_raw, _INBOX_KEYS)
    after_run = str(inbox_raw.get("after_run", "archive")).lower()
    if after_run not in _INBOX_AFTER_RUN:
        _fail("inbox", f"after_run '{after_run}' is not supported",
              'Use "archive" (default; moves the file to keep the inbox current-only), '
              '"keep" (leave it in place), or "delete".')
    archive_keep_days = int(inbox_raw.get("archive_keep_days", 90))
    if archive_keep_days < 0:
        _fail("inbox", "archive_keep_days cannot be negative",
              "Use 0 to keep archived files forever, or the number of days to retain them.")
    inbox = {
        "after_run": after_run,
        "archive_folder": str(inbox_raw.get("archive_folder", "Processed")),
        "archive_keep_days": archive_keep_days,
        "reprocess_identical": bool(inbox_raw.get("reprocess_identical", False)),
    }

    return ProjectConfig(
        project_name=project_name,
        root=os.path.dirname(os.path.abspath(path)),
        raw=data,
        sources=sources,
        title=title,
        language=str(data.get("language", "en")),
        approval=dict(data.get("approval", {})),
        business=dict(data.get("business", {})),
        relationships=list(data.get("relationships", [])),
        metrics_sql=str(data.get("metrics_sql", "sql/metrics.sql")),
        dashboard=dict(data.get("dashboard", {})),
        insights=list(data.get("insights", [])),
        quality_gates=dict(data.get("quality_gates", {})),
        sql_server=dict(data.get("sql_server", {})),
        database=dict(data.get("database", {})),
        inbox=inbox,
    )


def pending_approvals(config: ProjectConfig) -> list[str]:
    """Return every business decision still marked PENDING_APPROVAL."""

    pending: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif isinstance(node, str) and "PENDING_APPROVAL" in node:
            pending.append(path)

    walk(config.raw, "")
    if not config.is_approved:
        pending.append("approval.status")
    return sorted(set(pending))
