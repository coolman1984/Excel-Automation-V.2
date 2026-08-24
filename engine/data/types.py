"""Value parsing shared by cleaning, checks and reconciliation."""

from __future__ import annotations

import datetime as _dt
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_NUMBER_CLEAN_RE = re.compile(r"[\s, ٬']")
_TRUE = {"true", "yes", "y", "1", "t", "نعم"}
_FALSE = {"false", "no", "n", "0", "f", "لا"}

DEFAULT_DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%Y%m%d",
]


# Decimal places kept for a ``number`` column. 38 total digits minus 12 fractional
# leaves 26 for the integer part, which is far beyond any business figure, and 12
# fractional places cover money, unit prices, rates and percentages. Excel itself
# carries about 15 significant digits, so a value read from a workbook cannot need
# more than this.
DEFAULT_SCALE = 12
MAX_SCALE = 18
TOTAL_DIGITS = 38


class ParseError(ValueError):
    """The value cannot be understood as the configured type."""


def parse_decimal(text: str) -> Decimal:
    cleaned = _NUMBER_CLEAN_RE.sub("", str(text))
    cleaned = cleaned.replace("٫", ".")  # Arabic decimal separator
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    if cleaned.endswith("%"):
        raise ParseError(f"'{text}' is a percentage; map it as text or remove the % in the source")
    if cleaned.endswith("-"):  # trailing-minus exports
        cleaned = "-" + cleaned[:-1]
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ParseError(f"'{text}' is not a number") from exc
    return -value if negative else value


def parse_number(text: str, scale: int = DEFAULT_SCALE) -> Decimal:
    """A ``number`` stays a :class:`Decimal` all the way to storage.

    It used to become a float here, which meant every trusted total was summed in
    binary floating point. Rounding a money figure once is invisible; summing a
    million of them is not, and the drift landed in the published KPI.
    """

    value = parse_decimal(text)
    places = -value.as_tuple().exponent
    if places > scale:
        raise ParseError(
            f"'{text}' has {places} decimal places, more than the {scale} this column keeps")
    return value


def parse_integer(text: str) -> int:
    value = parse_decimal(text)
    if value != value.to_integral_value():
        raise ParseError(f"'{text}' is not a whole number")
    return int(value)


def parse_boolean(text: str) -> bool:
    lowered = str(text).strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ParseError(f"'{text}' is not yes/no")


def parse_date(text: str, formats: list[str] | None = None) -> _dt.date:
    value = str(text).strip()
    for fmt in list(formats or []) + DEFAULT_DATE_FORMATS:
        try:
            return _dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T].*", value):
        return _dt.date.fromisoformat(value[:10])
    if re.fullmatch(r"\d{1,6}(\.\d+)?", value):  # an Excel serial that lost its format
        serial = float(value)
        if 1 <= serial <= 400000:
            return (_dt.datetime(1899, 12, 30) + _dt.timedelta(days=serial)).date()
    raise ParseError(f"'{text}' is not a date")


def parse_datetime(text: str, formats: list[str] | None = None) -> _dt.datetime:
    value = str(text).strip()
    for fmt in list(formats or []) + ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"]:
        try:
            return _dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
    return _dt.datetime.combine(parse_date(value, formats), _dt.time())


def as_json_number(value: object) -> object:
    """Convert an exact value for the dashboard contract.

    This is the one place a trusted figure becomes a JSON number. Every browser
    parses JSON numbers as doubles, so the conversion has to happen somewhere; it
    happens here, once, on a figure that has already been aggregated and verified -
    never before the arithmetic.
    """

    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def same_number(left: object, right: object) -> bool:
    """Compare a parsed value against a value written in the configuration.

    ``Decimal("0.1") == 0.1`` is False, because the float is not exactly a tenth.
    Configured thresholds are decimal literals, so they are read as decimals.
    """

    if isinstance(left, Decimal) or isinstance(right, Decimal):
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (InvalidOperation, ValueError):
            return False
    return left == right


def parse(value: str | None, kind: str, formats: list[str] | None = None,
          scale: int = DEFAULT_SCALE) -> object:
    """Parse ``value`` into ``kind``. ``None``/empty stays ``None``."""

    if value is None or str(value).strip() == "":
        return None
    if kind == "text":
        return str(value)
    if kind == "number":
        return parse_number(value, scale)
    if kind == "integer":
        return parse_integer(value)
    if kind == "boolean":
        return 1 if parse_boolean(value) else 0
    if kind == "date":
        return parse_date(value, formats).isoformat()
    if kind == "datetime":
        return parse_datetime(value, formats).isoformat(sep=" ", timespec="seconds")
    raise ParseError(f"unsupported type '{kind}'")


def scaled(value: Decimal | float | int | None, precision: int) -> int:
    """Compare money exactly: convert to integer minor units."""

    if value is None:
        return 0
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    quantum = Decimal(1).scaleb(-precision)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    return int((rounded * (10 ** precision)).to_integral_value())
