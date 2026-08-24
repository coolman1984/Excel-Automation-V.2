"""Streaming CSV / TSV reader with Excel-compatible lineage.

Large delimited files are never loaded into memory at once.  Encoding is
selected conservatively: BOM-aware UTF variants first, then UTF-8, then an
explicit Windows-1252 fallback for common legacy exports.  The chosen encoding
is deterministic for the whole file.
"""

from __future__ import annotations

import csv
import io
import os
import sys
from collections.abc import Iterator

from engine.errors import UserError, user_error

_CANDIDATE_ENCODINGS = ("utf-8-sig", "utf-16", "cp1252")
# Large memo/description fields are common in exports; keep a bounded but practical ceiling.
csv.field_size_limit(min(sys.maxsize, 16 * 1024 * 1024))


def _encoding(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            sample = handle.read(128 * 1024)
    except OSError as exc:
        raise user_error("E-IN-002", "Re-save the file and add it again.",
                         detail=f"{path}: {exc}") from exc
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    # Some ERP exports omit the UTF-16 BOM. Alternating NUL bytes are a strong
    # signal and avoid mis-decoding the file as Windows-1252 garbage.
    if sample:
        even_nul = sample[0::2].count(0) / max(1, len(sample[0::2]))
        odd_nul = sample[1::2].count(0) / max(1, len(sample[1::2]))
        if odd_nul > 0.30 and even_nul < 0.05:
            return "utf-16-le"
        if even_nul > 0.30 and odd_nul < 0.05:
            return "utf-16-be"
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            sample.decode(encoding, errors="strict")
            return encoding
        except UnicodeDecodeError:
            continue
    return "cp1252"


def _dialect(path: str, encoding: str, delimiter: str | None) -> str:
    if delimiter:
        if len(delimiter) != 1:
            raise user_error("E-IN-002", next_action="Use one delimiter character such as comma, semicolon, tab or pipe.",
                             detail=f"delimiter={delimiter!r}")
        return delimiter
    try:
        with open(path, "r", encoding=encoding, newline="") as handle:
            sample = handle.read(64 * 1024)
    except (OSError, UnicodeError) as exc:
        raise user_error("E-IN-002", "Re-save the file and add it again.", detail=f"{path}: {exc}") from exc
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def inspect(path: str, delimiter: str | None = None, header_row: int = 1) -> tuple[list[str], str, str]:
    if header_row < 1:
        raise user_error("E-IN-002", next_action="Set header_row to 1 or greater.", detail=str(header_row))
    encoding = _encoding(path)
    delim = _dialect(path, encoding, delimiter)
    try:
        with open(path, "r", encoding=encoding, newline="") as handle:
            reader = csv.reader(handle, delimiter=delim)
            for index, values in enumerate(reader, start=1):
                if index == header_row:
                    return [v.strip() for v in values], encoding, delim
    except (OSError, UnicodeError, csv.Error) as exc:
        raise user_error("E-IN-002", "Re-save the file and add it again.", detail=f"{path}: {exc}") from exc
    raise user_error("E-IN-003", next_action="Check the configured header row and make sure the file is not empty.",
                     detail=f"{path}: header row {header_row} was not found")


def iter_rows(path: str, delimiter: str | None = None, header_row: int = 1,
              max_rows: int | None = None,
              strict_width: bool = True) -> Iterator[tuple[int, list[object]]]:
    """Stream data rows. ``strict_width`` controls what happens to a row with
    more columns than the header - typically an extra delimiter or a broken
    quote.

    The default, ``True``, raises immediately: a caller with no further context
    cannot safely decide what a stray extra column means, so refusing the whole
    file is the safe choice. A caller that can route the row somewhere visible
    (staging quarantines it as a malformed row and keeps reading) passes
    ``False`` and still receives the row, unmodified, so it can inspect and
    record it - the row is never silently truncated either way.
    """

    headers, encoding, delim = inspect(path, delimiter, header_row)
    width = len(headers)
    produced = 0
    try:
        with open(path, "r", encoding=encoding, newline="") as handle:
            reader = csv.reader(handle, delimiter=delim)
            for index, values in enumerate(reader, start=1):
                if index <= header_row:
                    continue
                if not any(v.strip() for v in values):
                    continue
                # Keep extra columns visible so header/data drift is not silently truncated.
                if len(values) > width and strict_width:
                    raise user_error(
                        "E-IN-003",
                        what_happened="A delimited row has more columns than its header.",
                        next_action=f"Check row {index} in '{os.path.basename(path)}' for an extra delimiter or broken quote.",
                        detail=f"header_columns={width} row_columns={len(values)} row={index}")
                yield index, list(values)
                produced += 1
                if max_rows is not None and produced >= max_rows:
                    return
    except UserError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise user_error("E-IN-002", "Re-save the file and add it again.", detail=f"{path}: {exc}") from exc


def read_block(path: str, delimiter: str | None = None, header_row: int = 1,
               max_rows: int | None = None) -> tuple[list[str], list[tuple[int, list[object]]]]:
    headers, _, _ = inspect(path, delimiter, header_row)
    return headers, list(iter_rows(path, delimiter, header_row, max_rows))
