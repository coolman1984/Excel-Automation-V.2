"""Dependency-free .xlsx reader.

Reads block by block (streaming rows), never cell-by-cell through Excel
automation. Uses only the standard library so the packaged application needs
no wheels, no pip and no internet.

Supported: shared strings, inline strings, numbers, booleans, cached formula
values and date/time formats. Not supported (and not needed by the engine):
charts, pivot caches, macros and drawing objects.
"""

from __future__ import annotations

import datetime as _dt
import re
import zipfile
from typing import Iterator, Sequence
from xml.etree import ElementTree as ET

from engine.errors import user_error

_CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")
_BUILTIN_DATE_FORMATS = set(range(14, 23)) | {27, 30, 36, 45, 46, 47, 50, 57}
_DATE_TOKEN_RE = re.compile(r"(?<!\\)[ymdhs]", re.IGNORECASE)


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


def column_index(ref: str) -> int:
    """``"A1" -> 0``, ``"C7" -> 2``. Returns a zero-based column index."""

    match = _CELL_RE.match(ref)
    letters = match.group(1) if match else re.sub(r"[^A-Z]", "", ref.upper())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def column_letter(index: int) -> str:
    """Inverse of :func:`column_index` (zero-based in, letters out)."""

    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


class Workbook:
    """A read-only view over one .xlsx file."""

    def __init__(self, path: str):
        self.path = str(path)
        try:
            self._zip = zipfile.ZipFile(self.path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise user_error(
                "E-IN-002",
                next_action="Re-save the file as .xlsx and add it again.",
                detail=f"{self.path}: {exc}",
            ) from exc
        self._shared: list[str] | None = None
        self._date_styles: set[int] | None = None
        self._epoch = _dt.datetime(1899, 12, 30)
        self._sheets = self._read_sheets()

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> "Workbook":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- structure ---------------------------------------------------------
    @property
    def sheet_names(self) -> list[str]:
        return [name for name, _ in self._sheets]

    def _read_sheets(self) -> list[tuple[str, str]]:
        rels: dict[str, str] = {}
        try:
            rels_xml = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        except KeyError:
            rels_xml = None
        if rels_xml is not None:
            for rel in rels_xml:
                target = rel.get("Target", "")
                if target.startswith("/"):
                    target = target[1:]
                elif not target.startswith("xl/"):
                    target = "xl/" + target
                rels[rel.get("Id", "")] = target.replace("xl/worksheets/../", "xl/")

        book = ET.fromstring(self._zip.read("xl/workbook.xml"))
        sheets: list[tuple[str, str]] = []
        for element in book.iter():
            if _local(element.tag) != "sheet":
                continue
            name = element.get("name", "")
            rid = ""
            for key, value in element.attrib.items():
                if _local(key) == "id":
                    rid = value
            target = rels.get(rid, "")
            if target:
                sheets.append((name, target))
        if not sheets:  # last resort for hand-built files
            sheets = [("Sheet1", "xl/worksheets/sheet1.xml")]
        if "xl/workbook.xml" in self._zip.namelist():
            book_pr = book.find("{*}workbookPr")
            if book_pr is not None and book_pr.get("date1904") in ("1", "true"):
                self._epoch = _dt.datetime(1904, 1, 1)
        return sheets

    def _resolve(self, sheet: str | int | None) -> str:
        if sheet is None:
            return self._sheets[0][1]
        if isinstance(sheet, int):
            try:
                return self._sheets[sheet][1]
            except IndexError:
                raise user_error(
                    "E-IN-002",
                    next_action="Check that the file still has the expected tab.",
                    detail=f"{self.path}: sheet #{sheet} not found; tabs={self.sheet_names}",
                ) from None
        for name, target in self._sheets:
            if name.strip().lower() == str(sheet).strip().lower():
                return target
        raise user_error(
            "E-IN-002",
            next_action=f"Rename the tab to '{sheet}' or update the source in the project configuration.",
            detail=f"{self.path}: tab '{sheet}' not found; tabs={self.sheet_names}",
        )

    # -- shared parts ------------------------------------------------------
    def _shared_strings(self) -> list[str]:
        if self._shared is not None:
            return self._shared
        values: list[str] = []
        if "xl/sharedStrings.xml" in self._zip.namelist():
            with self._zip.open("xl/sharedStrings.xml") as handle:
                text_parts: list[str] = []
                for event, element in ET.iterparse(handle, ("start", "end")):
                    name = _local(element.tag)
                    if event == "start" and name == "si":
                        text_parts = []
                    elif event == "end":
                        if name == "t":
                            text_parts.append(element.text or "")
                        elif name == "si":
                            values.append("".join(text_parts))
                            element.clear()
        self._shared = values
        return values

    def _date_style_ids(self) -> set[int]:
        if self._date_styles is not None:
            return self._date_styles
        styles: set[int] = set()
        if "xl/styles.xml" in self._zip.namelist():
            root = ET.fromstring(self._zip.read("xl/styles.xml"))
            custom: dict[int, str] = {}
            for element in root.iter():
                if _local(element.tag) == "numFmt":
                    custom[int(element.get("numFmtId", "0"))] = element.get("formatCode", "")
            cell_xfs = None
            for element in root.iter():
                if _local(element.tag) == "cellXfs":
                    cell_xfs = element
                    break
            if cell_xfs is not None:
                for position, xf in enumerate(list(cell_xfs)):
                    fmt_id = int(xf.get("numFmtId", "0"))
                    code = custom.get(fmt_id)
                    is_date = fmt_id in _BUILTIN_DATE_FORMATS
                    if code and not is_date:
                        stripped = re.sub(r"\[[^\]]*\]|\"[^\"]*\"", "", code)
                        is_date = bool(_DATE_TOKEN_RE.search(stripped))
                    if is_date:
                        styles.add(position)
        self._date_styles = styles
        return styles

    def _serial_to_datetime(self, serial: float) -> _dt.datetime:
        return self._epoch + _dt.timedelta(days=float(serial))

    # -- reading -----------------------------------------------------------
    def iter_rows(self, sheet: str | int | None = None, max_rows: int | None = None
                  ) -> Iterator[tuple[int, list[object]]]:
        """Yield ``(excel_row_number, values)`` for every non-empty row."""

        target = self._resolve(sheet)
        shared = self._shared_strings()
        date_styles = self._date_style_ids()
        produced = 0
        with self._zip.open(target) as handle:
            row_number = 0
            values: list[object] = []
            cell_index = 0
            cell_type = ""
            style_id = -1
            text_parts: list[str] = []
            in_value = False
            for event, element in ET.iterparse(handle, ("start", "end")):
                name = _local(element.tag)
                if event == "start":
                    if name == "row":
                        row_number = int(element.get("r", row_number + 1))
                        values = []
                    elif name == "c":
                        ref = element.get("r") or ""
                        cell_index = column_index(ref) if ref else len(values)
                        cell_type = element.get("t", "n")
                        style_id = int(element.get("s", "-1"))
                        text_parts = []
                    elif name in ("v", "t"):
                        in_value = True
                        text_parts.append("")
                    continue

                # end events
                if name in ("v", "t") and in_value:
                    text_parts.append(element.text or "")
                    in_value = False
                elif name == "c":
                    raw = "".join(text_parts)
                    value = self._cast(raw, cell_type, style_id, shared, date_styles)
                    while len(values) < cell_index:
                        values.append(None)
                    values.append(value)
                    element.clear()
                elif name == "row":
                    element.clear()
                    if any(v is not None and v != "" for v in values):
                        yield row_number, values
                        produced += 1
                        if max_rows is not None and produced >= max_rows:
                            return

    def _cast(self, raw: str, cell_type: str, style_id: int, shared: Sequence[str],
              date_styles: set[int]) -> object:
        if raw == "":
            return None
        if cell_type == "s":
            try:
                return shared[int(raw)]
            except (ValueError, IndexError):
                return raw
        if cell_type in ("str", "inlineStr"):
            return raw
        if cell_type == "b":
            return raw in ("1", "true", "TRUE")
        if cell_type == "e":
            return raw  # keep the Excel error text visible; validation rejects it
        try:
            number = float(raw)
        except ValueError:
            return raw
        if style_id in date_styles:
            moment = self._serial_to_datetime(number)
            if moment.time() == _dt.time(0, 0):
                return moment.date()
            return moment
        if number.is_integer() and abs(number) < 1e15:
            return int(number)
        return number


def read_block(path: str, sheet: str | int | None = None, header_row: int = 1,
               max_rows: int | None = None) -> tuple[list[str], list[tuple[int, list[object]]]]:
    """Read a sheet as ``(headers, rows)``.

    ``rows`` keeps the original Excel row number so quarantine messages can
    point the user back at the exact line in their own file.
    """

    with Workbook(path) as book:
        headers: list[str] = []
        rows: list[tuple[int, list[object]]] = []
        for row_number, values in book.iter_rows(sheet):
            if row_number < header_row:
                continue
            if row_number == header_row and not headers:
                headers = [("" if v is None else str(v)).strip() for v in values]
                continue
            rows.append((row_number, values))
            if max_rows is not None and len(rows) >= max_rows:
                break
        return headers, rows



def inspect(path: str, sheet: str | int | None = None, header_row: int = 1) -> list[str]:
    """Read only the configured header and stop; useful before a huge streaming pass."""
    with Workbook(path) as book:
        for row_number, values in book.iter_rows(sheet):
            if row_number < header_row:
                continue
            if row_number == header_row:
                return [("" if v is None else str(v)).strip() for v in values]
            if row_number > header_row:
                break
    raise user_error("E-IN-003", next_action="Check the configured header row and worksheet.",
                     detail=f"{path}: header row {header_row} was not found")


def iter_data_rows(path: str, sheet: str | int | None = None, header_row: int = 1,
                   max_rows: int | None = None) -> Iterator[tuple[int, list[object]]]:
    """Stream data rows while retaining exact Excel row numbers."""
    produced = 0
    with Workbook(path) as book:
        for row_number, values in book.iter_rows(sheet):
            if row_number <= header_row:
                continue
            yield row_number, values
            produced += 1
            if max_rows is not None and produced >= max_rows:
                return
