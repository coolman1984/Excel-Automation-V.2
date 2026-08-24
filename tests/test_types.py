"""Real exports contain messy values. Typing must be predictable."""

from __future__ import annotations

import datetime as _dt
import unittest

from tests.helpers import remove_all  # noqa: F401  (keeps import style consistent)

from engine.data import types


class TypesTest(unittest.TestCase):
    def test_numbers_with_separators_and_brackets(self) -> None:
        self.assertEqual(types.parse("1,234.50", "number"), 1234.50)
        self.assertEqual(types.parse("(50)", "number"), -50.0)
        self.assertEqual(types.parse("1 234", "number"), 1234.0)
        self.assertEqual(types.parse("12-", "number"), -12.0)

    def test_arabic_decimal_separator(self) -> None:
        self.assertEqual(types.parse("12٫5", "number"), 12.5)

    def test_percentages_are_refused_rather_than_guessed(self) -> None:
        with self.assertRaises(types.ParseError):
            types.parse("15%", "number")

    def test_integer_rejects_fractions(self) -> None:
        self.assertEqual(types.parse("7", "integer"), 7)
        with self.assertRaises(types.ParseError):
            types.parse("7.5", "integer")

    def test_common_date_formats(self) -> None:
        for text in ("2026-03-01", "01/03/2026", "1-Mar-2026", "20260301"):
            self.assertEqual(types.parse(text, "date"), "2026-03-01", text)

    def test_configured_date_format_wins(self) -> None:
        self.assertEqual(types.parse("03/01/2026", "date", ["%m/%d/%Y"]), "2026-03-01")

    def test_excel_serial_that_lost_its_format(self) -> None:
        serial = (_dt.date(2026, 3, 1) - _dt.date(1899, 12, 30)).days
        self.assertEqual(types.parse(str(serial), "date"), "2026-03-01")

    def test_yes_no_values(self) -> None:
        self.assertEqual(types.parse("Yes", "boolean"), 1)
        self.assertEqual(types.parse("no", "boolean"), 0)
        self.assertEqual(types.parse("نعم", "boolean"), 1)
        with self.assertRaises(types.ParseError):
            types.parse("maybe", "boolean")

    def test_empty_stays_empty(self) -> None:
        for kind in ("text", "number", "date", "boolean", "integer"):
            self.assertIsNone(types.parse("   ", kind), kind)

    def test_nonsense_is_refused_not_silently_zeroed(self) -> None:
        with self.assertRaises(types.ParseError):
            types.parse("n/a", "number")


if __name__ == "__main__":
    unittest.main()
