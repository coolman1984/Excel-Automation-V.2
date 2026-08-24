"""Raw staging with lineage.

Every value is stored exactly as the file presented it (as text) together with
the file it came from, its hash and its original Excel row number. Nothing is
interpreted yet - interpretation happens in :mod:`engine.data.clean` - so any
later question ("where did this number come from?") has an answer.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os

from engine.data import resolve, structure
from engine.db import database
from engine.errors import user_error
from engine.excel import com_reader, csv_reader, layout, xlsx_reader

LINEAGE_COLUMNS = [("_run_id", "TEXT"), ("_file", "TEXT"), ("_sha256", "TEXT"),
                   ("_row_no", "INTEGER")]


@dataclasses.dataclass
class StageResult:
    source_id: str
    rows_read: int
    files: list[str]
    missing_optional_columns: list[str]
    rows_seen: int = 0
    rows_excluded: int = 0
    excluded_by_class: dict = dataclasses.field(default_factory=dict)
    declared_totals: list = dataclasses.field(default_factory=list)
    suspected_totals: list = dataclasses.field(default_factory=list)
    guessed_columns: list = dataclasses.field(default_factory=list)   # (file_name, Resolution)
    header_moves: list = dataclasses.field(default_factory=list)       # (file_name, hint, found)


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


def _map_headers(source, headers: list[str], file_name: str
                 ) -> tuple[dict[str, int], list[str], list[resolve.Resolution]]:
    """Resolve every mapped column against this file's header row.

    An exact rename or a declared alias is resolved silently. Anything found
    only through the normalised, fuzzy or positional rungs is still resolved -
    the run is not blocked over an ordinary rename - but is returned as a
    "guess" so the caller can name it in the drift report and keep the run at
    WARNING rather than a silent PASS.
    """

    result = resolve.resolve(source, headers)
    if result.ambiguous:
        first = result.ambiguous[0]
        if first.rung == resolve.RUNG_EXACT:
            raise user_error(
                "E-IN-003",
                what_happened="A required column name appears more than once in the source header.",
                next_action=(f"Rename the duplicate column(s) {sorted({first.column})} in "
                             f"'{file_name}' so each mapped column is unique."),
                detail=f"headers={headers}")
        raise user_error(
            "E-IN-003",
            what_happened=f"More than one column in '{file_name}' could be '{first.column}'.",
            next_action=(f"Rename one of {first.candidates} in '{file_name}', or map "
                         f"'{first.column}' to an unambiguous name."),
            detail=f"rung={first.rung} headers={headers}")
    if result.missing_required:
        raise user_error(
            "E-IN-003",
            next_action=(f"Add the column(s) {result.missing_required} to '{file_name}', or update "
                         f"the source mapping for '{source.id}'."),
            detail=f"file columns = {headers}",
        )
    return result.positions, result.missing_optional, result.guessed


def stage(connection, run_id: str, source, files) -> StageResult:
    """Load discovered files incrementally; never materialise a huge workbook in RAM."""

    table = stage_table(source.id)
    database.drop_table(connection, table)
    database.create_table(connection, table,
                          LINEAGE_COLUMNS + [(c.field, "TEXT") for c in source.columns])
    columns = [c[0] for c in LINEAGE_COLUMNS] + [c.field for c in source.columns]

    rows_read = 0
    rows_seen = 0
    rows_excluded = 0
    excluded_by_class: dict[str, int] = {}
    declared_totals: list = []
    suspected_totals: list = []
    guessed_columns: list = []
    header_moves: list = []
    missing_optional: list[str] = []
    extraction = source.extraction or {}
    requested_chunk = max(250, int(extraction.get("chunk_rows", 5000)))

    for discovered in files:
        ext = os.path.splitext(discovered.file_name)[1].lower()
        mode = str(extraction.get("mode", "auto")).lower()
        use_com = mode == "excel_com" or ext in {".xls", ".xlsb"}

        if source.format == "csv":
            sample = csv_reader.sample_rows(discovered.workspace_path, delimiter=source.delimiter,
                                            limit=source.header_search_rows)
            location = layout.find_header(sample, source, source.header_row,
                                          source.header_search_rows)
            if location.moved:
                header_moves.append((discovered.file_name, source.header_row, location.row_number))
            headers, _, _ = csv_reader.inspect(discovered.workspace_path,
                                                delimiter=source.delimiter,
                                                header_row=location.row_number)
            row_iter = csv_reader.iter_rows(discovered.workspace_path,
                                             delimiter=source.delimiter,
                                             header_row=location.row_number,
                                             strict_width=False)
        elif use_com:
            # The header-search above samples only the direct .xlsx/.csv readers this
            # environment can prove; the COM route for protected workbooks keeps using
            # the configured header_row exactly as before.
            com_blocks = com_reader.iter_blocks(discovered.workspace_path, sheet=source.sheet,
                header_row=source.header_row, chunk_rows=requested_chunk,
                visible=bool(extraction.get("visible", False)))
            headers, _ = next(com_blocks)
            row_iter = (row for _headers, block in com_blocks for row in block)
        elif mode == "direct":
            sample = list(xlsx_reader.Workbook(discovered.workspace_path).iter_rows(
                sheet=source.sheet, max_rows=source.header_search_rows))
            location = layout.find_header(sample, source, source.header_row,
                                          source.header_search_rows)
            if location.moved:
                header_moves.append((discovered.file_name, source.header_row, location.row_number))
            headers = xlsx_reader.inspect(discovered.workspace_path, sheet=source.sheet,
                                          header_row=location.row_number)
            row_iter = xlsx_reader.iter_data_rows(discovered.workspace_path, sheet=source.sheet,
                                                   header_row=location.row_number)
        else:
            try:
                sample = list(xlsx_reader.Workbook(discovered.workspace_path).iter_rows(
                    sheet=source.sheet, max_rows=source.header_search_rows))
                location = layout.find_header(sample, source, source.header_row,
                                              source.header_search_rows)
                headers = xlsx_reader.inspect(discovered.workspace_path, sheet=source.sheet,
                                              header_row=location.row_number)
                row_iter = xlsx_reader.iter_data_rows(discovered.workspace_path, sheet=source.sheet,
                                                       header_row=location.row_number)
                if location.moved:
                    header_moves.append(
                        (discovered.file_name, source.header_row, location.row_number))
            except Exception:
                if not com_reader.available():
                    raise
                com_blocks = com_reader.iter_blocks(discovered.workspace_path, sheet=source.sheet,
                    header_row=source.header_row, chunk_rows=requested_chunk,
                    visible=bool(extraction.get("visible", False)))
                headers, _ = next(com_blocks)
                row_iter = (row for _headers, block in com_blocks for row in block)

        positions, optional, guessed = _map_headers(source, headers, discovered.file_name)
        missing_optional.extend(o for o in optional if o not in missing_optional)
        guessed_columns.extend((discovered.file_name, resolution) for resolution in guessed)

        # Keep each database insert bounded by both rows and an approximate cell count.
        batch_limit = max(250, min(requested_chunk, max(250, 120000 // max(1, len(columns)))))
        batch: list[list[object]] = []
        file_rows = 0
        file_seen = 0
        file_excluded = 0
        classifier = structure.Classifier(source)

        header_width = len(headers)
        for row_number, values in row_iter:
            if classifier.should_stop(row_number):
                break
            file_seen += 1

            if source.format == "csv" and len(values) > header_width:
                # An extra delimiter or a broken quote, not a business row: the
                # header can't say which mapped field the stray value belongs to,
                # so it is quarantined rather than guessed at or silently dropped.
                file_excluded += 1
                excluded_by_class[structure.MALFORMED] = (
                    excluded_by_class.get(structure.MALFORMED, 0) + 1)
                reason = (f"the row has {len(values)} columns but the header has "
                         f"{header_width}; check for an extra delimiter or a broken quote.")
                # zip() would silently drop exactly the stray value that makes
                # the row malformed, so the extra column(s) are kept visible
                # under their own key instead of being truncated away.
                mapped_raw = dict(zip(headers, values[:header_width]))
                if len(values) > header_width:
                    mapped_raw["_extra_columns"] = values[header_width:]
                _record_excluded(connection, run_id, source.id, discovered.file_name,
                                 row_number, structure.Verdict(structure.MALFORMED, reason),
                                 mapped_raw)
                continue

            mapped: dict[str, object] = {}
            for column in source.columns:
                index = positions.get(column.field)
                value = values[index] if index is not None and index < len(values) else None
                text_value = _as_text(value)
                if text_value is not None and column.trim:
                    text_value = text_value.strip()
                mapped[column.field] = text_value

            verdict = classifier.classify(row_number, mapped)
            if not verdict.is_data:
                file_excluded += 1
                excluded_by_class[verdict.kind] = excluded_by_class.get(verdict.kind, 0) + 1
                _record_excluded(connection, run_id, source.id, discovered.file_name,
                                 row_number, verdict, mapped)
                continue

            mapped = classifier.enrich(mapped)
            record: list[object] = [run_id, discovered.file_name, discovered.sha256, row_number]
            record.extend(mapped.get(column.field) for column in source.columns)
            batch.append(record)
            file_rows += 1
            if len(batch) >= batch_limit:
                database.insert_many(connection, table, columns, batch)
                rows_read += len(batch)
                batch = []
        if batch:
            database.insert_many(connection, table, columns, batch)
            rows_read += len(batch)

        rows_seen += file_seen
        rows_excluded += file_excluded
        declared_totals.extend((discovered.file_name, total)
                               for total in classifier.declared_totals)
        suspected_totals.extend((discovered.file_name, item)
                                for item in classifier.suspicions)
        _record_declared_totals(connection, run_id, source.id, discovered.file_name,
                                classifier.declared_totals)
        connection.execute(
            "UPDATE run_files SET rows_read = ?, rows_seen = ?, rows_excluded = ?"
            " WHERE run_id = ? AND source_id = ? AND file_name = ?",
            (file_rows, file_seen, file_excluded, run_id, source.id, discovered.file_name))

    return StageResult(source_id=source.id, rows_read=rows_read,
                       files=[f.file_name for f in files],
                       missing_optional_columns=missing_optional,
                       rows_seen=rows_seen, rows_excluded=rows_excluded,
                       excluded_by_class=excluded_by_class,
                       declared_totals=declared_totals,
                       suspected_totals=suspected_totals,
                       guessed_columns=guessed_columns,
                       header_moves=header_moves)


def _record_excluded(connection, run_id: str, source_id: str, file_name: str, row_number: int,
                     verdict, values: dict) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO excluded_rows(run_id, source_id, file_name, excel_row,"
        " row_class, reason, row_json) VALUES (?,?,?,?,?,?,?)",
        (run_id, source_id, file_name, row_number, verdict.kind, verdict.reason,
         json.dumps(values, ensure_ascii=False, default=str)))


def _record_declared_totals(connection, run_id: str, source_id: str, file_name: str,
                            totals: list) -> None:
    for total in totals:
        connection.execute(
            "INSERT OR REPLACE INTO source_totals(run_id, source_id, file_name, excel_row,"
            " field, declared, data_sum, covers, matched, confirmed) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, source_id, file_name, total.excel_row, total.field, str(total.declared),
             str(total.data_sum), total.covers, 1 if total.matched else 0,
             1 if total.confirmed_by_arithmetic else 0))
