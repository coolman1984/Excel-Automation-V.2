"""Raw staging with lineage.

Every value is stored exactly as the file presented it (as text) together with
the file it came from, its hash and its original Excel row number. Nothing is
interpreted yet - interpretation happens in :mod:`engine.data.clean` - so any
later question ("where did this number come from?") has an answer.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import os

from engine.db import database
from engine.errors import user_error
from engine.excel import com_reader, csv_reader, xlsx_reader

LINEAGE_COLUMNS = [("_run_id", "TEXT"), ("_file", "TEXT"), ("_sha256", "TEXT"),
                   ("_row_no", "INTEGER")]


@dataclasses.dataclass
class StageResult:
    source_id: str
    rows_read: int
    files: list[str]
    missing_optional_columns: list[str]


def stage_table(source_id: str) -> str:
    return f"stg__{source_id}"


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, _dt.datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _map_headers(source, headers: list[str], file_name: str) -> tuple[dict[str, int], list[str]]:
    lookup = {}
    duplicates = set()
    for index, header in enumerate(headers):
        key = str(header).strip().lower()
        if not key:
            continue
        if key in lookup:
            duplicates.add(key)
        else:
            lookup[key] = index
    expected = {c.source.strip().lower() for c in source.columns}
    ambiguous = sorted(duplicates & expected)
    if ambiguous:
        raise user_error(
            "E-IN-003",
            what_happened="A required column name appears more than once in the source header.",
            next_action=f"Rename the duplicate column(s) {ambiguous} in '{file_name}' so each mapped column is unique.",
            detail=f"headers={headers}")
    positions: dict[str, int] = {}
    missing_required: list[str] = []
    missing_optional: list[str] = []
    for column in source.columns:
        index = lookup.get(column.source.strip().lower())
        if index is None:
            (missing_required if column.required else missing_optional).append(column.source)
            continue
        positions[column.field] = index
    if missing_required:
        raise user_error(
            "E-IN-003",
            next_action=(f"Add the column(s) {missing_required} to '{file_name}', or update the "
                         f"source mapping for '{source.id}'."),
            detail=f"file columns = {headers}",
        )
    return positions, missing_optional


def stage(connection, run_id: str, source, files) -> StageResult:
    """Load discovered files incrementally; never materialise a huge workbook in RAM."""

    table = stage_table(source.id)
    database.drop_table(connection, table)
    database.create_table(connection, table,
                          LINEAGE_COLUMNS + [(c.field, "TEXT") for c in source.columns])
    columns = [c[0] for c in LINEAGE_COLUMNS] + [c.field for c in source.columns]

    rows_read = 0
    missing_optional: list[str] = []
    extraction = source.extraction or {}
    requested_chunk = max(250, int(extraction.get("chunk_rows", 5000)))

    for discovered in files:
        ext = os.path.splitext(discovered.file_name)[1].lower()
        mode = str(extraction.get("mode", "auto")).lower()
        use_com = mode == "excel_com" or ext in {".xls", ".xlsb"}

        if source.format == "csv":
            headers, _, _ = csv_reader.inspect(discovered.workspace_path,
                                                delimiter=source.delimiter,
                                                header_row=source.header_row)
            row_iter = csv_reader.iter_rows(discovered.workspace_path,
                                             delimiter=source.delimiter,
                                             header_row=source.header_row)
        elif use_com:
            com_blocks = com_reader.iter_blocks(discovered.workspace_path, sheet=source.sheet,
                header_row=source.header_row, chunk_rows=requested_chunk,
                visible=bool(extraction.get("visible", False)))
            headers, _ = next(com_blocks)
            row_iter = (row for _headers, block in com_blocks for row in block)
        elif mode == "direct":
            headers = xlsx_reader.inspect(discovered.workspace_path, sheet=source.sheet,
                                          header_row=source.header_row)
            row_iter = xlsx_reader.iter_data_rows(discovered.workspace_path, sheet=source.sheet,
                                                   header_row=source.header_row)
        else:
            try:
                headers = xlsx_reader.inspect(discovered.workspace_path, sheet=source.sheet,
                                              header_row=source.header_row)
                row_iter = xlsx_reader.iter_data_rows(discovered.workspace_path, sheet=source.sheet,
                                                       header_row=source.header_row)
            except Exception:
                if not com_reader.available():
                    raise
                com_blocks = com_reader.iter_blocks(discovered.workspace_path, sheet=source.sheet,
                    header_row=source.header_row, chunk_rows=requested_chunk,
                    visible=bool(extraction.get("visible", False)))
                headers, _ = next(com_blocks)
                row_iter = (row for _headers, block in com_blocks for row in block)

        positions, optional = _map_headers(source, headers, discovered.file_name)
        missing_optional.extend(o for o in optional if o not in missing_optional)

        # Keep each database insert bounded by both rows and an approximate cell count.
        batch_limit = max(250, min(requested_chunk, max(250, 120000 // max(1, len(columns)))))
        batch: list[list[object]] = []
        file_rows = 0
        for row_number, values in row_iter:
            record: list[object] = [run_id, discovered.file_name, discovered.sha256, row_number]
            for column in source.columns:
                index = positions.get(column.field)
                value = values[index] if index is not None and index < len(values) else None
                text_value = _as_text(value)
                if text_value is not None and column.trim:
                    text_value = text_value.strip()
                record.append(text_value)
            batch.append(record)
            file_rows += 1
            if len(batch) >= batch_limit:
                database.insert_many(connection, table, columns, batch)
                rows_read += len(batch)
                batch = []
        if batch:
            database.insert_many(connection, table, columns, batch)
            rows_read += len(batch)
        connection.execute(
            "UPDATE run_files SET rows_read = ? WHERE run_id = ? AND source_id = ? AND file_name = ?",
            (file_rows, run_id, source.id, discovered.file_name))

    return StageResult(source_id=source.id, rows_read=rows_read,
                       files=[f.file_name for f in files],
                       missing_optional_columns=missing_optional)
