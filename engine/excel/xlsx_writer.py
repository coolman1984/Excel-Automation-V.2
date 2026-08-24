"""Minimal dependency-free .xlsx writer.

Used for test fixtures and for user-facing exports. Writes a single sheet of
strings, numbers, dates and booleans - which is everything the product needs.
"""

from __future__ import annotations

import datetime as _dt
import zipfile
from typing import Iterable, Sequence

_EPOCH = _dt.datetime(1899, 12, 30)

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_BOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

# style 0 = general, style 1 = yyyy-mm-dd (numFmtId 14)
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>
</styleSheet>"""


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _cell(ref: str, value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, _dt.datetime):
        serial = (value - _EPOCH).total_seconds() / 86400.0
        return f'<c r="{ref}" s="1"><v>{serial:.10f}</v></c>'
    if isinstance(value, _dt.date):
        serial = (_dt.datetime(value.year, value.month, value.day) - _EPOCH).days
        return f'<c r="{ref}" s="1"><v>{serial}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{_escape(str(value))}</t></is></c>'


def write_sheet(path: str, headers: Sequence[str], rows: Iterable[Sequence[object]],
                sheet_name: str = "Sheet1") -> str:
    """Write ``headers`` + ``rows`` to ``path`` and return the path."""

    parts: list[str] = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
                        "<sheetData>"]
    row_number = 1
    parts.append(f'<row r="{row_number}">' +
                 "".join(_cell(f"{_letter(i)}{row_number}", h) for i, h in enumerate(headers)) +
                 "</row>")
    for row in rows:
        row_number += 1
        parts.append(f'<row r="{row_number}">' +
                     "".join(_cell(f"{_letter(i)}{row_number}", v) for i, v in enumerate(row)) +
                     "</row>")
    parts.append("</sheetData></worksheet>")

    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
                ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets><sheet name="{_escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
                "</workbook>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", _BOOK_RELS)
        archive.writestr("xl/styles.xml", _STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", "".join(parts))
    return str(path)
