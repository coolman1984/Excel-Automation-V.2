"""``PROJECT_TOOL doctor --probe`` - a read-only dry run against a real file.

Before an adaptation agent, or an operator wondering why a file drifted, has
to guess what a run would do, this reports the sheet, the header row, how
every column resolved and at which rung, and how the file's rows classify -
without touching the warehouse, copying a file, or merging a single row.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import io
import os
import shutil
import unittest

from engine import cli
from engine.excel.xlsx_writer import write_sheet
from tests.helpers import project_copy, remove_all, temp_dir

SALES_HEAD = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product",
             "Quantity", "Unit Price", "Amount", "Status"]
CUSTOMER_HEAD = ["Customer ID", "Customer Name", "Segment", "Country"]


def sales_rows():
    return [
        ["INV-1", 1, _dt.date(2026, 1, 5), "C001", "Pump", 2, 100.0, 200.0, "Posted"],
        ["INV-2", 1, _dt.date(2026, 1, 6), "C002", "Valve", 3, 100.0, 300.0, "Posted"],
    ]


class DoctorProbeTest(unittest.TestCase):
    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def probe(self, project, sample_dir):
        args = cli.build_parser().parse_args(
            ["doctor", "--project", project, "--probe", sample_dir])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = args.func(args)
        return code, buffer.getvalue()

    def project_with(self, sheet_rows, customers=True):
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        sample = temp_dir(self.cleanup)
        write_sheet(os.path.join(sample, "sales_2026.xlsx"), *sheet_rows, "Sales")
        if customers:
            write_sheet(os.path.join(sample, "customers.xlsx"), CUSTOMER_HEAD,
                       [["C001", "Customer 01", "Retail", "Saudi Arabia"],
                        ["C002", "Customer 02", "Wholesale", "Saudi Arabia"]], "Customers")
        return project, sample

    def test_a_clean_file_reports_every_column_resolved_exactly(self):
        project, sample = self.project_with((SALES_HEAD, sales_rows()))
        code, output = self.probe(project, sample)

        self.assertEqual(code, 0)
        self.assertIn("header      : row 1", output)
        self.assertIn("'Invoice No' matched 'Invoice No'", output)
        self.assertIn("rows        : 2 seen -> 2 data", output)
        self.assertNotIn("MISSING", output)
        self.assertNotIn("AMBIGUOUS", output)

    def test_a_banner_row_is_named_without_processing_anything(self):
        project, sample = self.project_with(
            (["Monthly Sales Export - Confidential"], [SALES_HEAD] + sales_rows()))
        code, output = self.probe(project, sample)

        self.assertEqual(code, 0)
        self.assertIn("row 2 (configured row 1 did not look like the header)", output)
        self.assertIn("rows        : 2 seen -> 2 data", output)

    def test_a_total_row_is_classified_and_verified(self):
        rows = sales_rows() + [
            ["Total", None, None, None, None, None, None, 500.0, None]]
        project, sample = self.project_with((SALES_HEAD, rows))
        code, output = self.probe(project, sample)

        self.assertEqual(code, 0)
        self.assertIn("3 seen -> 2 data + 1 total or subtotal line", output)
        self.assertIn("totals      : 1 total line(s) found, all verified", output)

    def test_a_disagreeing_total_is_flagged_not_silently_accepted(self):
        rows = sales_rows() + [
            ["Total", None, None, None, None, None, None, 999.0, None]]
        project, sample = self.project_with((SALES_HEAD, rows))
        code, output = self.probe(project, sample)

        self.assertIn("1 DISAGREE with their rows", output)

    def test_a_missing_required_column_is_named(self):
        header = [h for h in SALES_HEAD if h != "Amount"]
        rows = [[c for c, h in zip(row, SALES_HEAD) if h != "Amount"] for row in sales_rows()]
        project, sample = self.project_with((header, rows))
        code, output = self.probe(project, sample)

        self.assertIn("'Amount' -> MISSING (required)", output)

    def test_no_file_in_the_folder_matches_the_source(self):
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        empty = temp_dir(self.cleanup)
        code, output = self.probe(project, empty)

        self.assertIn("no file in", output)
        self.assertIn("matches", output)

    def test_the_probe_touches_no_workspace_or_warehouse(self):
        """Read-only means read-only: no _work directory appears anywhere the
        probe was given, since nothing is copied, hashed or merged."""

        project, sample = self.project_with((SALES_HEAD, sales_rows()))
        self.probe(project, sample)
        self.assertFalse(os.path.isdir(os.path.join(sample, "_work")))
        self.assertFalse(any(name.endswith(".db") for name in os.listdir(sample)))


if __name__ == "__main__":
    unittest.main()
