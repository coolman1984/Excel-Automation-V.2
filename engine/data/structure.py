"""Tell layout rows apart from data rows.

Real exports are not clean rectangles. They carry title banners above the
header, section labels between blocks, subtotal lines inside the data and a
grand total at the end. Those rows are *layout*, not records - but they sit in
the same columns as records, so a reader that trusts the rectangle counts them
as data and every downstream total is quietly wrong.

Two rules govern everything here:

* **Never exclude a row on a weak signal.** A row is removed only when two
  independent signals agree, or when its label cell says nothing but "Total".
  A single weak hint produces a visible *suspicion*, never a silent deletion.
* **A detected total is evidence, not just noise.** A subtotal states what the
  file itself believes its rows add up to. Comparing that against the rows we
  actually kept is the one control in the engine that does not compare the
  system against itself, so it is recorded and reconciled rather than dropped.

Every excluded row keeps its Excel row number, its class and its original
values, and stays visible in the application.
"""

from __future__ import annotations

import dataclasses
import re
from decimal import Decimal

from engine.data import types

# ---------------------------------------------------------------------------
# text normalisation
# ---------------------------------------------------------------------------

_ARABIC_MARKS = re.compile(r"[ً-ْٰـ]")
_ARABIC_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي", "ة": "ه", "ؤ": "و",
})
_NON_WORD = re.compile(r"[^\w؀-ۿ]+")

# The whole cell says nothing but "total". Safe to act on alone.
STANDALONE_LABELS = {
    "total", "totals", "subtotal", "sub total", "grand total", "overall total",
    "net total", "running total", "group total", "page total", "report total",
    "sum", "sum total", "total sum", "count total",
    "الاجمالي", "اجمالي", "الاجمالي العام", "اجمالي عام", "المجموع", "مجموع",
    "المجموع الكلي", "المجموع العام", "الجمله", "جمله", "الكلي", "اجمالي الكل",
    "اجمالي عام للكل", "الاجمالي الكلي",
}

# The cell contains one of these as a word. A hint only - needs a second signal.
CONTAINED_LABELS = (
    "total", "subtotal", "totals",
    "اجمالي", "الاجمالي", "مجموع", "المجموع",
)

DATA = "data"
TOTAL = "total"
BANNER = "banner"
SECTION = "section"
NOTE = "note"
MALFORMED = "malformed"

CLASS_TITLES = {
    TOTAL: "Total or subtotal line",
    BANNER: "Title or banner line",
    SECTION: "Section label",
    NOTE: "Note or footer line",
    MALFORMED: "Malformed row (extra column)",
}


def normalize(text: object) -> str:
    """Fold a header/label cell to a comparable form.

    Casefolds, removes Arabic diacritics and tatweel, unifies alef/yeh/teh-marbuta
    variants, turns punctuation into spaces and collapses whitespace. ``"TOTAL-JAN"``
    and ``"الإجمالي"`` become ``"total jan"`` and ``"الاجمالي"``.
    """

    value = str("" if text is None else text).strip().casefold()
    value = _ARABIC_MARKS.sub("", value)
    value = value.translate(_ARABIC_FOLD)
    value = _NON_WORD.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def _has_label_word(normalized: str) -> bool:
    if not normalized:
        return False
    words = set(normalized.split())
    return any(label in words for label in CONTAINED_LABELS)


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

SETTING_KEYS = {
    "detect_total_rows", "total_label_fields", "extra_total_labels",
    "verify_totals_against_data", "on_total_mismatch",
    "capture_section_headers_into", "stop_after_blank_rows",
}


def settings(source) -> dict:
    raw = dict(getattr(source, "structure", None) or {})
    extra = {normalize(item) for item in (raw.get("extra_total_labels") or [])}
    return {
        "detect_total_rows": bool(raw.get("detect_total_rows", True)),
        "total_label_fields": list(raw.get("total_label_fields") or []),
        "standalone_labels": STANDALONE_LABELS | {item for item in extra if item},
        "verify_totals_against_data": bool(raw.get("verify_totals_against_data", True)),
        "on_total_mismatch": str(raw.get("on_total_mismatch", "block")).lower(),
        "capture_section_headers_into": str(raw.get("capture_section_headers_into") or ""),
        "stop_after_blank_rows": int(raw.get("stop_after_blank_rows", 0) or 0),
    }


# ---------------------------------------------------------------------------
# results
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Verdict:
    kind: str = DATA
    reason: str = ""
    signals: tuple[str, ...] = ()

    @property
    def is_data(self) -> bool:
        return self.kind == DATA


@dataclasses.dataclass
class DeclaredTotal:
    """A total the source file states about itself."""

    excel_row: int
    field: str
    declared: Decimal
    data_sum: Decimal
    covers: str            # "block" | "all" | "none"
    matched: bool
    confirmed_by_arithmetic: bool


@dataclasses.dataclass
class Suspicion:
    """A row that looks like a total but was kept, because one signal is not enough."""

    excel_row: int
    field: str
    text: str


class Classifier:
    """Streaming classifier. One instance per source file.

    Accumulates the running sums the arithmetic signal needs, so it must see
    every row of the file in order.
    """

    def __init__(self, source):
        self.source = source
        self.config = settings(source)
        self.columns = {column.field: column for column in source.columns}

        self.numeric_fields = self._numeric_fields()
        self.precision = self._precision_map()
        self.label_fields = self._label_fields()
        self.key_fields = [f for f in (source.business_key or []) if f in self.columns]
        self.required_fields = [c.field for c in source.columns if c.required]

        self._block: dict[str, Decimal] = {f: Decimal(0) for f in self.numeric_fields}
        self._all: dict[str, Decimal] = {f: Decimal(0) for f in self.numeric_fields}
        self._block_rows = 0
        self._all_rows = 0
        self._last_row_number = 0
        self._stop = False
        self._data_seen = False

        self.section = ""
        self.declared_totals: list[DeclaredTotal] = []
        self.suspicions: list[Suspicion] = []
        self.counts: dict[str, int] = {}

    # -- setup ------------------------------------------------------------
    def _numeric_fields(self) -> list[str]:
        controls = [t["field"] for t in (self.source.control_totals or [])
                    if t.get("field") in self.columns]
        if controls:
            return controls
        return [c.field for c in self.source.columns if c.type in ("number", "integer")]

    def _precision_map(self) -> dict[str, int]:
        precision = {}
        for total in self.source.control_totals or []:
            field = total.get("field")
            if field in self.columns:
                precision[field] = int(total.get("precision", 2))
        for field in self.numeric_fields:
            if field not in precision:
                precision[field] = 0 if self.columns[field].type == "integer" else 2
        return precision

    def _label_fields(self) -> list[str]:
        configured = [f for f in self.config["total_label_fields"] if f in self.columns]
        if configured:
            return configured
        return [c.field for c in self.source.columns if c.type == "text"]

    # -- end of data ------------------------------------------------------
    def should_stop(self, row_number: int) -> bool:
        """True when a run of blank rows marks the end of the data block.

        Readers skip empty rows silently but keep the real Excel row numbers, so
        a gap in those numbers is how many blank rows were passed over.
        """

        limit = self.config["stop_after_blank_rows"]
        if self._stop:
            return True
        if limit > 0 and self._last_row_number and self._data_seen:
            if row_number - self._last_row_number - 1 >= limit:
                self._stop = True
        return self._stop

    # -- classification ---------------------------------------------------
    def classify(self, row_number: int, values: dict[str, object]) -> Verdict:
        self._last_row_number = row_number
        populated = {field: value for field, value in values.items()
                     if value is not None and str(value).strip() != ""}

        if not populated:
            return self._record(Verdict(NOTE, "The row is empty in every mapped column."))

        # A single populated text cell is a title above the data or a section
        # label between blocks; it is never a record.
        if len(populated) == 1:
            field, value = next(iter(populated.items()))
            if field not in self.numeric_fields and self.columns[field].type == "text":
                text = str(value).strip()
                if self._data_seen:
                    self.section = text
                    return self._record(Verdict(SECTION, f"Section label {text!r}."))
                return self._record(Verdict(BANNER, f"Title line {text!r} above the data."))

        if not self.config["detect_total_rows"]:
            return self._data(populated)

        signals: list[str] = []
        label_text = ""
        label_field = ""
        weak_label = ""
        weak_field = ""

        for field in self.label_fields:
            value = populated.get(field)
            if value is None:
                continue
            folded = normalize(value)
            if folded in self.config["standalone_labels"]:
                label_text, label_field = str(value).strip(), field
                break
            if _has_label_word(folded) and not weak_label:
                weak_label, weak_field = str(value).strip(), field
        if label_text:
            signals.append("label")
        elif weak_label:
            signals.append("label_hint")

        if self._shape_of_a_total(populated):
            signals.append("shape")

        arithmetic = self._arithmetic_match(populated)
        if arithmetic:
            signals.append("arithmetic")

        strong = [s for s in signals if s != "label_hint"]
        decided = (
            "label" in signals                                    # the cell says only "Total"
            or len(strong) >= 2                                   # two independent signals
            or ("label_hint" in signals and len(strong) >= 1)      # a hint, corroborated
        )

        if decided:
            reason = self._reason(label_text or weak_label, label_field or weak_field, signals)
            self._register_total(row_number, populated, arithmetic)
            self._reset_block()
            return self._record(Verdict(TOTAL, reason, tuple(signals)))

        if weak_label:
            # Kept as data, but the operator is told, so nothing is silent either way.
            self.suspicions.append(Suspicion(row_number, weak_field, weak_label))

        return self._data(populated)

    def enrich(self, values: dict[str, object]) -> dict[str, object]:
        """Fill the configured section field from the last section label seen."""

        field = self.config["capture_section_headers_into"]
        if not field or not self.section or field not in self.columns:
            return values
        current = values.get(field)
        if current is None or str(current).strip() == "":
            values = dict(values)
            values[field] = self.section
        return values

    # -- signals ----------------------------------------------------------
    def _shape_of_a_total(self, populated: dict) -> bool:
        """The identity of the row is missing but its figures are present.

        Such a row can never become a record - it has no key - so treating it as
        layout loses nothing that would have been kept, and it stops a pair of
        subtotal lines from tripping the rejected-rows gate and blocking the run.
        """

        identity = self.key_fields or self.required_fields
        if not identity:
            return False
        if any(field in populated for field in identity):
            return False
        return any(field in populated for field in self.numeric_fields)

    def _arithmetic_match(self, populated: dict) -> dict[str, str]:
        """Fields whose value equals the running sum of the rows above.

        Requires at least two accumulated rows: with one, a subtotal and its
        single data row are indistinguishable, and guessing there would delete
        a real record.
        """

        matches: dict[str, str] = {}
        for field in self.numeric_fields:
            if field not in populated:
                continue
            value = self._decimal(populated[field])
            if value is None:
                continue
            scale = self.precision[field]
            target = types.scaled(value, scale)
            if self._block_rows >= 2 and target == types.scaled(self._block[field], scale):
                matches[field] = "block"
            elif self._all_rows >= 2 and target == types.scaled(self._all[field], scale):
                matches[field] = "all"
        return matches

    # -- bookkeeping ------------------------------------------------------
    def _data(self, populated: dict) -> Verdict:
        self._data_seen = True
        self._block_rows += 1
        self._all_rows += 1
        for field in self.numeric_fields:
            value = self._decimal(populated.get(field))
            if value is not None:
                self._block[field] += value
                self._all[field] += value
        return self._record(Verdict(DATA))

    def _record(self, verdict: Verdict) -> Verdict:
        self.counts[verdict.kind] = self.counts.get(verdict.kind, 0) + 1
        return verdict

    def _reset_block(self) -> None:
        self._block = {field: Decimal(0) for field in self.numeric_fields}
        self._block_rows = 0

    def _register_total(self, row_number: int, populated: dict, arithmetic: dict) -> None:
        for field in self.numeric_fields:
            if field not in populated:
                continue
            declared = self._decimal(populated[field])
            if declared is None:
                continue
            scale = self.precision[field]
            covers = arithmetic.get(field, "")
            if covers == "block":
                data_sum, matched = self._block[field], True
            elif covers == "all":
                data_sum, matched = self._all[field], True
            else:
                # Compare against whichever running sum is closer, so the
                # recorded difference is the smallest honest one.
                block, whole = self._block[field], self._all[field]
                if abs(declared - block) <= abs(declared - whole):
                    data_sum, covers = block, "block"
                else:
                    data_sum, covers = whole, "all"
                matched = types.scaled(declared, scale) == types.scaled(data_sum, scale)
            self.declared_totals.append(DeclaredTotal(
                excel_row=row_number, field=field, declared=declared, data_sum=data_sum,
                covers=covers, matched=matched,
                confirmed_by_arithmetic=bool(arithmetic.get(field))))

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return types.parse_decimal(str(value))
        except types.ParseError:
            return None

    def _reason(self, label: str, field: str, signals: list[str]) -> str:
        if label:
            column = self.columns[field].source if field in self.columns else field
            base = f"'{column}' reads {label!r}"
        elif "shape" in signals:
            base = "the row has figures but no record identity"
        else:
            base = "the row repeats the total of the rows above it"
        if "arithmetic" in signals:
            return f"{base}, and its figures equal the rows above it."
        return f"{base}."


def unverified_totals(totals: list[DeclaredTotal]) -> list[DeclaredTotal]:
    """Totals whose stated figure does not equal the rows it covers."""

    return [total for total in totals if not total.matched]
