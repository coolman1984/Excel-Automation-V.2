"""Header auto-location, end to end through the pipeline.

This is the original P0-3 reproduction from the project review: one title
banner row above the header hard-blocked the whole run with 'add the
column(s) [...] or update the source mapping'. tests/test_layout.py covers
the row-scoring rules in isolation; this file proves the real pipeline
absorbs it.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import unittest

from engine import config as config_module, paths, pipeline
from engine.excel.xlsx_writer import write_sheet
from tests.helpers import edit_config, project_copy, remove_all, temp_dir

SALES_HEAD = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product",
             "Quantity", "Unit Price", "Amount", "Status"]
CUSTOMER_HEAD = ["Customer ID", "Customer Name", "Segment", "Country"]
CUSTOMERS = [["C001", "Customer 01", "Retail", "Saudi Arabia"],
             ["C002", "Customer 02", "Wholesale", "Saudi Arabia"]]


def sales_rows():
    return [
        ["INV-1", 1, _dt.date(2026, 1, 5), "C001", "Pump", 2, 100.0, 200.0, "Posted"],
        ["INV-2", 1, _dt.date(2026, 1, 6), "C002", "Valve", 3, 100.0, 300.0, "Posted"],
    ]


class BannerRowRunTest(unittest.TestCase):
    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def run_with_rows(self, sheet_rows, mutate=None):
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        if mutate is not None:
            edit_config(project, mutate)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_export.xlsx"),
                    ["Monthly Sales Export - Confidential"], sheet_rows, "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                    CUSTOMERS, "Customers")
        config = config_module.load(project)
        return pipeline.run(config, workspace), workspace

    def check(self, result, name, source_id="sales"):
        for item in result.reconciliation:
            if item["name"] == name and item["source_id"] == source_id:
                return item
        return None

    def test_the_original_p03_reproduction_now_publishes(self):
        """A single banner row above the header - the exact fixture from the
        original review - used to BLOCK with E-IN-003 and publish nothing."""

        sheet = [SALES_HEAD] + sales_rows()
        result, _workspace = self.run_with_rows(sheet)

        self.assertEqual(result.status, "WARNING", result.message)
        self.assertIsNone(result.error)
        for total in result.reconciliation:
            if total["name"] == "control_total_amount":
                self.assertEqual(total["actual"], "500.00")

    def test_the_header_move_is_named_in_the_reconciliation_evidence(self):
        sheet = [SALES_HEAD] + sales_rows()
        result, _workspace = self.run_with_rows(sheet)

        moved = self.check(result, "header_location")
        self.assertIsNotNone(moved)
        self.assertEqual(moved["status"], "WARNING")
        self.assertIn("row 2", moved["actual"])

    def test_two_banner_rows_are_both_absorbed(self):
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_export.xlsx"),
                   ["Confidential"], [["Draft - do not distribute"]] + [SALES_HEAD] + sales_rows(),
                   "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD, CUSTOMERS,
                   "Customers")
        config = config_module.load(project)
        result = pipeline.run(config, workspace)

        self.assertEqual(result.status, "WARNING", result.message)

    def test_a_normal_file_with_no_banner_is_unaffected(self):
        """The common case - a header exactly where it is configured - must
        not be flagged just because auto-location now exists."""

        project = project_copy(self.cleanup)
        workspace = paths.workspace_for(
            temp_dir(self.cleanup), os.path.join(temp_dir(self.cleanup), "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_export.xlsx"), SALES_HEAD,
                    sales_rows(), "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                    CUSTOMERS, "Customers")
        config = config_module.load(project)
        result = pipeline.run(config, workspace)

        self.assertEqual(result.status, "PASS", result.message)
        self.assertIsNone(self.check(result, "header_location"))

    def test_a_genuinely_headerless_file_still_blocks_clearly(self):
        """No configured column appears anywhere in the search window: no
        guess is made, and the ordinary missing-column error still fires."""

        sheet = [["x", "y", "z"], ["1", "2", "3"]]
        result, _workspace = self.run_with_rows(sheet)
        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(result.error["support_code"], "E-IN-003")

    def test_search_window_can_be_narrowed_per_source(self):
        """A one-row banner is well within the default window; narrowing the
        window below that must make the same file block again, proving the
        setting is actually doing something."""

        def narrow(data):
            for source in data["sources"]:
                if source["id"] == "sales":
                    source["header_search_rows"] = 1

        sheet = [SALES_HEAD] + sales_rows()
        result, _workspace = self.run_with_rows(sheet, narrow)
        self.assertEqual(result.status, "BLOCK")


if __name__ == "__main__":
    unittest.main()
