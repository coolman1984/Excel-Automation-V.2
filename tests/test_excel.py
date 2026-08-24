"""The Excel reader must survive the files real businesses actually send."""

from __future__ import annotations

import datetime as _dt
import os
import unittest

from tests.helpers import FIXTURES, remove_all, temp_dir

from engine.errors import UserError
from engine.excel import csv_reader, xlsx_reader
from engine.excel.xlsx_writer import write_sheet


class ExcelReaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def test_round_trip_keeps_types(self) -> None:
        path = os.path.join(temp_dir(self.cleanup), "book.xlsx")
        write_sheet(path, ["Text", "Number", "Date", "Flag"],
                    [["hello", 12.5, _dt.date(2026, 2, 3), True],
                     ["عربي", -4, _dt.date(2026, 12, 31), False]], "Data")
        headers, rows = xlsx_reader.read_block(path, "Data")
        self.assertEqual(headers, ["Text", "Number", "Date", "Flag"])
        self.assertEqual(rows[0][1][0], "hello")
        self.assertEqual(rows[0][1][2], _dt.date(2026, 2, 3))
        self.assertEqual(rows[1][1][0], "عربي")
        self.assertIs(rows[1][1][3], False)

    def test_row_numbers_point_back_at_the_users_file(self) -> None:
        path = os.path.join(temp_dir(self.cleanup), "book.xlsx")
        write_sheet(path, ["A"], [[1], [2], [3]])
        _, rows = xlsx_reader.read_block(path)
        self.assertEqual([row[0] for row in rows], [2, 3, 4])

    def test_missing_sheet_is_a_plain_language_error(self) -> None:
        path = os.path.join(temp_dir(self.cleanup), "book.xlsx")
        write_sheet(path, ["A"], [[1]], "Sales")
        with self.assertRaises(UserError) as caught:
            xlsx_reader.read_block(path, "Missing")
        self.assertEqual(caught.exception.code, "E-IN-002")
        self.assertIn("Missing", caught.exception.next_action)

    def test_broken_file_is_a_plain_language_error(self) -> None:
        path = os.path.join(temp_dir(self.cleanup), "broken.xlsx")
        with open(path, "wb") as handle:
            handle.write(b"not really a workbook")
        with self.assertRaises(UserError) as caught:
            xlsx_reader.read_block(path)
        self.assertEqual(caught.exception.code, "E-IN-002")

    def test_fixtures_are_readable(self) -> None:
        headers, rows = xlsx_reader.read_block(os.path.join(FIXTURES, "sales_2026Q1.xlsx"), "Sales")
        self.assertIn("Invoice No", headers)
        self.assertGreater(len(rows), 50)

    def test_column_helpers(self) -> None:
        self.assertEqual(xlsx_reader.column_index("A1"), 0)
        self.assertEqual(xlsx_reader.column_index("AA10"), 26)
        self.assertEqual(xlsx_reader.column_letter(26), "AA")

    def test_csv_source(self) -> None:
        path = os.path.join(temp_dir(self.cleanup), "data.csv")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("A;B\n1;2\n3;4\n")
        headers, rows = csv_reader.read_block(path)
        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
