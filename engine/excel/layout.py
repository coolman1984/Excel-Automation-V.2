"""Locate the header row within a sheet, before any column is mapped.

``header_row`` in ``project.json`` is a hint, not a hard requirement. A
one-line title banner added above the header - "Monthly Sales Export -
Confidential" - is one of the most ordinary things a re-exported report picks
up, and used to hard-block the run: the configured row no longer held the
header, so no configured column could be found, and the fix on offer was to
edit the project configuration - calling the adaptation agent back for a
change with no business meaning.

This module only decides which *row* holds the headers. Which *column* each
header text maps to is a separate question, answered by
:mod:`engine.data.resolve`; the two are combined in
:func:`engine.data.staging.stage`.

Scope: this samples only the direct ``.xlsx`` and ``.csv`` readers, the two
this repository can prove in an ordinary Linux test environment. The
Excel-COM path for protected workbooks keeps using the configured
``header_row`` unchanged, consistent with every other COM limitation already
documented in this codebase.
"""

from __future__ import annotations

import dataclasses

from engine.data import structure

DEFAULT_SEARCH_ROWS = 25


@dataclasses.dataclass
class Candidate:
    row_number: int
    values: list
    score: float
    matched_columns: int


def _text_fraction(values: list) -> float:
    if not values:
        return 0.0
    populated = [v for v in values if v is not None and str(v).strip() != ""]
    return len(populated) / len(values)


def _configured_names(source) -> set[str]:
    names: set[str] = set()
    for column in source.columns:
        names.add(structure.normalize(column.source))
        for alias in (getattr(column, "aliases", None) or []):
            names.add(structure.normalize(alias))
    names.discard("")
    return names


def _matches_configured_columns(values: list, targets: set[str]) -> int:
    """How many cells normalise to one of this source's configured column
    names or aliases. Cheap and order-independent - scoring needs only a
    count, not :mod:`engine.data.resolve`'s full ambiguity bookkeeping."""

    return sum(1 for value in values if structure.normalize(value) in targets)


def score_row(values: list, targets: set[str], column_count: int,
             next_values: list | None = None) -> Candidate:
    text_fraction = _text_fraction(values)
    matched = _matches_configured_columns(values, targets)
    populated = sum(1 for v in values if v is not None and str(v).strip() != "")

    score = matched * 10.0 + text_fraction * 2.0
    if populated <= 1 and column_count > 1:
        # A single populated cell is a title or a section label, not a header
        # naming several mapped columns.
        score -= 5.0
    if next_values is not None:
        next_populated = sum(1 for v in next_values if v is not None and str(v).strip() != "")
        if next_populated >= max(1, len(values) // 2):
            # A header is normally followed by a row that is at least about as
            # wide as itself; a banner is normally followed by a blank line or
            # another banner.
            score += 1.0
    return Candidate(row_number=0, values=values, score=score, matched_columns=matched)


@dataclasses.dataclass
class HeaderLocation:
    row_number: int
    values: list | None
    moved: bool


def find_header(sample: list[tuple[int, list]], source, hint: int,
                search_rows: int = DEFAULT_SEARCH_ROWS) -> HeaderLocation:
    """Choose which sampled row is the header.

    ``sample`` is the first physical rows of the sheet, in order, exactly as
    the reader produced them - blank rows included or not, whichever the
    reader already does; this function does not care. ``hint`` is
    ``source.header_row``.

    The configured row wins whenever it is competitive: this only overrides
    the operator's own setting when the file has actually drifted, never as
    a matter of routine second-guessing. When nothing in the sample matches
    any configured column at all, no guess is made - the hinted row is
    returned unchanged so the ordinary "missing column" error explains what
    happened, rather than a wrong row producing a more confusing one.
    """

    windowed = [item for item in sample if item[0] < sample[0][0] + search_rows] if sample else []
    if not windowed:
        return HeaderLocation(hint, None, False)

    targets = _configured_names(source)
    column_count = len(source.columns)
    candidates: list[Candidate] = []
    for index, (row_number, values) in enumerate(windowed):
        next_values = windowed[index + 1][1] if index + 1 < len(windowed) else None
        candidate = score_row(values, targets, column_count, next_values)
        candidate.row_number = row_number
        candidates.append(candidate)

    best = max(candidates, key=lambda c: (c.score, -c.row_number))
    if best.matched_columns == 0:
        return HeaderLocation(hint, None, False)

    hinted = next((c for c in candidates if c.row_number == hint), None)
    if hinted is not None and hinted.matched_columns > 0 and hinted.score >= best.score - 1e-9:
        return HeaderLocation(hint, hinted.values, False)

    return HeaderLocation(best.row_number, best.values, best.row_number != hint)
