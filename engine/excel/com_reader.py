"""Authorized Microsoft Excel desktop extraction for protected corporate workbooks.

This adapter is deliberately Windows-only and lazy-loaded.  It creates its own
Excel instance, opens the source read-only in the logged-in user's approved
session, reads large rectangular ``Value2`` blocks, and never edits the source.
Normal unprotected workbooks continue to use the dependency-free direct reader.
"""

from __future__ import annotations

import os
import sys
from typing import Iterator

from engine.errors import user_error

XL_UP = -4162
XL_TO_LEFT = -4159
XL_FORMULAS = -4123
XL_BY_ROWS = 1
XL_BY_COLUMNS = 2
XL_PREVIOUS = 2
XL_CALCULATION_MANUAL = -4135


def _activate_bundled_pywin32() -> None:
    """Expose pywin32's wheel layout inside an embeddable private runtime.

    A normal Python installation processes pywin32's ``.pth`` file through
    ``site``. The Windows embeddable runtime intentionally does not import site,
    so we add only the bundled pywin32 directories explicitly. Nothing is
    installed and no machine-wide path is changed.
    """
    root = os.path.dirname(sys.executable) if getattr(sys, "executable", None) else sys.prefix
    for relative in ("win32", os.path.join("win32", "lib"), "pywin32_system32", "Pythonwin"):
        candidate = os.path.join(root, relative)
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)
    system32 = os.path.join(root, "pywin32_system32")
    if os.name == "nt" and os.path.isdir(system32) and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(system32)
        except OSError:
            pass


def available() -> bool:
    if os.name != "nt":
        return False
    _activate_bundled_pywin32()
    try:
        import win32com.client  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def _as_matrix(value, rows: int, cols: int) -> list[list[object]]:
    if rows <= 0 or cols <= 0:
        return []
    if rows == 1 and cols == 1:
        return [[value]]
    if rows == 1:
        return [list(value)]
    if cols == 1:
        return [[row[0] if isinstance(row, (tuple, list)) else row] for row in value]
    return [list(row) for row in value]


def iter_blocks(path: str, sheet: str | int | None = None, header_row: int = 1,
                max_rows: int | None = None, chunk_rows: int = 5000,
                visible: bool = False):
    """Yield ``(headers, rows)`` once per rectangular Excel COM block.

    The first yielded item carries the headers. Subsequent items carry only one
    data block at a time. Keeping the workbook open inside the generator avoids
    materializing million-row protected workbooks in Python memory.
    """
    if os.name != "nt":
        raise user_error(
            "E-IN-002",
            what_happened="This protected workbook needs Microsoft Excel on Windows.",
            next_action="Run this project on the approved Windows PC where the workbook opens normally.",
            detail=f"Excel COM requested for {path!r} on non-Windows platform")
    _activate_bundled_pywin32()
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise user_error(
            "E-IN-002",
            what_happened="The protected-workbook connector is not bundled in this application.",
            next_action="Rebuild the application with the approved Windows Excel connector dependency.",
            detail="pywin32 is missing") from exc

    pythoncom.CoInitialize()
    excel = None
    workbook = None
    try:
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
        except Exception as exc:
            raise user_error(
                "E-IN-002",
                what_happened="Microsoft Excel desktop is not available to this application.",
                next_action="Run the project on the approved Windows PC with Microsoft Excel installed and activated.",
                detail=f"Excel.Application could not start: {exc}") from exc
        excel.Visible = bool(visible)
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False
        try: excel.EnableEvents = False
        except Exception: pass
        try: excel.AskToUpdateLinks = False
        except Exception: pass
        try: excel.Calculation = XL_CALCULATION_MANUAL
        except Exception: pass
        try: excel.AutomationSecurity = 3
        except Exception: pass
        try:
            workbook = excel.Workbooks.Open(
                os.path.abspath(path), UpdateLinks=0, ReadOnly=True, IgnoreReadOnlyRecommended=True,
                AddToMru=False, Notify=False)
        except Exception as exc:
            raise user_error(
                "E-IN-002",
                what_happened="Microsoft Excel could not open the protected workbook in the approved user session.",
                next_action="Open the workbook manually once. If Excel can open it, close it and process again.",
                detail=f"{path}: {exc}") from exc

        if sheet is None:
            worksheet = workbook.Worksheets(1)
        elif isinstance(sheet, int):
            worksheet = workbook.Worksheets(sheet + 1)
        else:
            wanted = str(sheet).strip().casefold()
            matches = [workbook.Worksheets(i) for i in range(1, workbook.Worksheets.Count + 1)
                       if str(workbook.Worksheets(i).Name).strip().casefold() == wanted]
            if not matches:
                names = [workbook.Worksheets(i).Name for i in range(1, workbook.Worksheets.Count + 1)]
                raise user_error(
                    "E-IN-002",
                    next_action=f"Rename the tab to '{sheet}' or update the project mapping.",
                    detail=f"tab {sheet!r} not found; tabs={names}")
            worksheet = matches[0]

        used = worksheet.UsedRange
        first_col = max(1, int(used.Column))
        try:
            last_by_row = worksheet.Cells.Find(What="*", After=worksheet.Cells(1, 1),
                LookIn=XL_FORMULAS, SearchOrder=XL_BY_ROWS, SearchDirection=XL_PREVIOUS)
            last_by_col = worksheet.Cells.Find(What="*", After=worksheet.Cells(1, 1),
                LookIn=XL_FORMULAS, SearchOrder=XL_BY_COLUMNS, SearchDirection=XL_PREVIOUS)
            last_row = int(last_by_row.Row) if last_by_row is not None else int(used.Row) + int(used.Rows.Count) - 1
            last_col = int(last_by_col.Column) if last_by_col is not None else first_col + int(used.Columns.Count) - 1
        except Exception:
            last_col = first_col + int(used.Columns.Count) - 1
            last_row = int(used.Row) + int(used.Rows.Count) - 1
        if last_row < header_row or last_col < first_col:
            yield [], []
            return

        header_value = worksheet.Range(
            worksheet.Cells(header_row, first_col), worksheet.Cells(header_row, last_col)).Value2
        header_matrix = _as_matrix(header_value, 1, last_col - first_col + 1)
        headers = [("" if v is None else str(v)).strip() for v in (header_matrix[0] if header_matrix else [])]
        yield headers, []

        data_start = header_row + 1
        if max_rows is not None:
            last_row = min(last_row, data_start + max_rows - 1)
        column_count = max(1, last_col - first_col + 1)
        chunk_rows = max(250, min(int(chunk_rows or 5000), max(250, 150000 // column_count)))
        start = data_start
        while start <= last_row:
            current_chunk = min(chunk_rows, last_row - start + 1)
            while True:
                end = start + current_chunk - 1
                try:
                    value = worksheet.Range(
                        worksheet.Cells(start, first_col), worksheet.Cells(end, last_col)).Value2
                    break
                except Exception as exc:
                    if current_chunk <= 250:
                        raise user_error("E-IN-002",
                            what_happened="Microsoft Excel could not read part of this workbook reliably.",
                            next_action="Close other Excel files and process again. If it repeats, save a fresh copy of the workbook.",
                            detail=f"rows {start}:{end}, columns={column_count}: {exc}") from exc
                    current_chunk = max(250, current_chunk // 2)
            matrix = _as_matrix(value, current_chunk, column_count)
            block = [(start + offset, values) for offset, values in enumerate(matrix)
                     if any(v is not None and v != "" for v in values)]
            if block:
                yield [], block
            start += current_chunk
    finally:
        if workbook is not None:
            try: workbook.Close(SaveChanges=False)
            except Exception: pass
        if excel is not None:
            try: excel.Quit()
            except Exception: pass
        pythoncom.CoUninitialize()


def read_block(path: str, sheet: str | int | None = None, header_row: int = 1,
               max_rows: int | None = None, chunk_rows: int = 5000,
               visible: bool = False) -> tuple[list[str], list[tuple[int, list[object]]]]:
    """Compatibility collector for callers that explicitly need all rows in memory."""
    headers: list[str] = []
    rows: list[tuple[int, list[object]]] = []
    for block_headers, block_rows in iter_blocks(path, sheet=sheet, header_row=header_row,
                                                  max_rows=max_rows, chunk_rows=chunk_rows,
                                                  visible=visible):
        if block_headers:
            headers = block_headers
        rows.extend(block_rows)
    return headers, rows
