"""Match a source's mapped columns against a file's actual header row.

An exact header match is the common case and always wins outright. Real
exports drift, though: a column gets renamed, reordered, translated, or
gains a unit suffix. This module works down a ladder of increasingly
permissive rules so an ordinary rename does not need the adaptation agent
called back, and records exactly how every column was found, so nothing is
ever silently guessed.

Rungs, in order:

1. ``exact``       - matches ``column.source`` verbatim, case-insensitive.
2. ``alias``       - matches one of ``column.aliases`` verbatim.
3. ``normalized``  - matches after folding case, whitespace, punctuation,
                     diacritics and digit forms (see :func:`structure.normalize`).
4. ``fuzzy``       - token-set similarity at or above 0.9 against the source
                     name or an alias - tolerant of reordered words
                     ("Invoice No" / "No Invoice") and small typos, not of a
                     genuinely different word ("No" / "Number").
5. ``positional``  - the column's position in ``project.json`` maps to the
                     same position in the file. Only tried when the source
                     declares ``column_order: "stable"``, and never for a
                     column used in a business key or a control total, since
                     a silently wrong mapping there would corrupt a trusted
                     figure rather than merely misname a field.

Every rung below ``exact`` is a guess, however confident, so a required column
resolved there raises the run to ``WARNING`` rather than staying silent, and
two candidates tying at the same rung is refused outright rather than picked
arbitrarily - see :func:`resolve`.

Rung 5 matches by position alone; it does not yet inspect the data type of the
rows beneath the header to corroborate the guess. That refinement is a natural
follow-up, not implemented here - the opt-in flag, the business-key/control-total
exclusion and the mandatory WARNING are what keep it safe without it.
"""

from __future__ import annotations

import dataclasses
import difflib

from engine.data import structure

RUNG_EXACT = "exact"
RUNG_ALIAS = "alias"
RUNG_NORMALIZED = "normalized"
RUNG_FUZZY = "fuzzy"
RUNG_POSITIONAL = "positional"

# Tried in this order; a match at an earlier rung always wins over a later one,
# for every column at once - so a rung-1 exact match for column B can never be
# stolen by a rung-4 fuzzy guess resolved for column A first.
RUNG_ORDER = (RUNG_EXACT, RUNG_ALIAS, RUNG_NORMALIZED, RUNG_FUZZY, RUNG_POSITIONAL)

RUNG_TITLES = {
    RUNG_EXACT: "exact match",
    RUNG_ALIAS: "known alias",
    RUNG_NORMALIZED: "matched after ignoring case, spacing and punctuation",
    RUNG_FUZZY: "matched by similarity",
    RUNG_POSITIONAL: "matched by column position",
}

FUZZY_THRESHOLD = 0.9


def _tokens(text: str) -> set[str]:
    return set(structure.normalize(text).split())


def _fuzzy_ratio(a: str, b: str) -> float:
    """Word-order-independent similarity, plus tolerance for small typos.

    Two different scores are combined because they catch different drift: a
    Dice coefficient on the token sets catches reordered words ("Invoice No"
    vs "No Invoice") that a straight character comparison would score low;
    :class:`difflib.SequenceMatcher` on the normalised strings catches a
    dropped or added character. Genuinely different words ("No" vs "Number")
    score low on both and correctly fail to match.
    """

    tokens_a, tokens_b = _tokens(a), _tokens(b)
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = len(tokens_a & tokens_b)
    dice = 2 * overlap / (len(tokens_a) + len(tokens_b))
    sequence = difflib.SequenceMatcher(None, structure.normalize(a), structure.normalize(b)).ratio()
    return max(dice, sequence)


@dataclasses.dataclass
class Resolution:
    """How one configured column was, or was not, found in this file."""

    field: str
    source_label: str
    required: bool
    header_index: int | None = None
    header_text: str | None = None
    rung: str | None = None
    score: float = 1.0

    @property
    def resolved(self) -> bool:
        return self.header_index is not None

    @property
    def is_guess(self) -> bool:
        """Anything below an exact or a declared alias is a guess."""

        return self.rung not in (None, RUNG_EXACT, RUNG_ALIAS)

    def describe(self) -> str:
        if not self.resolved:
            return f"'{self.source_label}' was not found."
        if self.rung in (RUNG_EXACT, RUNG_ALIAS):
            return f"'{self.source_label}' matched '{self.header_text}'."
        return (f"'{self.source_label}' was matched to '{self.header_text}' "
               f"({RUNG_TITLES.get(self.rung, self.rung)}).")


@dataclasses.dataclass
class Ambiguity:
    column: str
    rung: str
    candidates: list[str]


@dataclasses.dataclass
class ResolveResult:
    positions: dict[str, int]
    resolutions: list[Resolution]
    missing_required: list[str]
    missing_optional: list[str]
    ambiguous: list[Ambiguity]

    @property
    def guessed(self) -> list[Resolution]:
        return [r for r in self.resolutions if r.resolved and r.is_guess]


def resolve(source, headers: list[str], column_order: str = "unstable") -> ResolveResult:
    """Resolve every mapped column of ``source`` against ``headers``.

    ``column_order`` is read from ``source`` when present (see
    :mod:`engine.config`); the parameter exists so the small mock objects some
    unit tests use, which carry only ``.source``/``.field``/``.required``,
    still work without needing every attribute the real config dataclass has.
    """

    columns = list(source.columns)
    order = str(getattr(source, "column_order", column_order) or column_order)
    key_fields = set(getattr(source, "business_key", None) or [])
    total_fields = {t.get("field") for t in (getattr(source, "control_totals", None) or [])}

    resolutions = {
        column.field: Resolution(field=column.field, source_label=column.source,
                                 required=bool(getattr(column, "required", False)))
        for column in columns
    }
    claimed: dict[int, str] = {}          # header index -> field that took it
    ambiguous: list[Ambiguity] = []

    def fuzzy_score(column, header: str) -> float:
        names = [column.source.strip()] + [a.strip() for a in (getattr(column, "aliases", None) or [])]
        return max(_fuzzy_ratio(header, name) for name in names)

    def candidates_at(column, rung: str) -> list[int]:
        """Every header position that matches at this rung. More than one
        means a genuine tie, at any rung, including fuzzy - a highest-scoring
        fuzzy candidate is not returned alone unless it clearly beats the rest,
        so two equally-plausible guesses are refused rather than one being
        picked arbitrarily.
        """

        label = column.source.strip()
        aliases = [a.strip() for a in (getattr(column, "aliases", None) or [])]
        if rung == RUNG_EXACT:
            targets = {label.casefold()}
            return [i for i, header in enumerate(headers)
                   if i not in claimed and str(header).strip().casefold() in targets]
        if rung == RUNG_ALIAS:
            targets = {a.casefold() for a in aliases}
            if not targets:
                return []
            return [i for i, header in enumerate(headers)
                   if i not in claimed and str(header).strip().casefold() in targets]
        if rung == RUNG_NORMALIZED:
            targets = {structure.normalize(label)} | {structure.normalize(a) for a in aliases}
            targets.discard("")
            return [i for i, header in enumerate(headers)
                   if i not in claimed and structure.normalize(header) in targets]
        if rung == RUNG_FUZZY:
            scored = [(fuzzy_score(column, headers[i]), i) for i in range(len(headers))
                     if i not in claimed and str(headers[i]).strip()]
            scored = [(score, i) for score, i in scored if score >= FUZZY_THRESHOLD]
            if not scored:
                return []
            best = max(score for score, _ in scored)
            return [i for score, i in scored if best - score < 1e-9]
        return []

    # A column that is ambiguous at one rung must not be probed at a weaker
    # one - a looser rule silently resolving what a stricter rule refused to
    # would defeat the point of refusing it.
    abandoned: set[str] = set()

    for rung in (RUNG_EXACT, RUNG_ALIAS, RUNG_NORMALIZED, RUNG_FUZZY):
        for column in columns:
            if column.field in abandoned:
                continue
            resolution = resolutions[column.field]
            if resolution.resolved:
                continue
            found = candidates_at(column, rung)
            if not found:
                continue
            if len(found) > 1:
                ambiguous.append(Ambiguity(
                    column=column.source, rung=rung,
                    candidates=[str(headers[i]) for i in found]))
                abandoned.add(column.field)
                continue
            index = found[0]
            score = fuzzy_score(column, headers[index]) if rung == RUNG_FUZZY else 1.0
            resolution.header_index = index
            resolution.header_text = str(headers[index]).strip()
            resolution.rung = rung
            resolution.score = score
            claimed[index] = column.field

    if order == "stable":
        unclaimed_headers = [i for i in range(len(headers)) if i not in claimed]
        unresolved_columns = [c for c in columns if not resolutions[c.field].resolved
                              and c.field not in key_fields and c.field not in total_fields]
        for column, index in zip(unresolved_columns, unclaimed_headers):
            resolution = resolutions[column.field]
            resolution.header_index = index
            resolution.header_text = str(headers[index]).strip()
            resolution.rung = RUNG_POSITIONAL
            resolution.score = 0.0
            claimed[index] = column.field

    missing_required, missing_optional = [], []
    for column in columns:
        resolution = resolutions[column.field]
        if not resolution.resolved:
            (missing_required if resolution.required else missing_optional).append(column.source)

    return ResolveResult(
        positions={f: r.header_index for f, r in resolutions.items() if r.resolved},
        resolutions=[resolutions[c.field] for c in columns],
        missing_required=missing_required,
        missing_optional=missing_optional,
        ambiguous=ambiguous,
    )
