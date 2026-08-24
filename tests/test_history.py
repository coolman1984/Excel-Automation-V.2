"""History must be connected, idempotent and honest about corrections."""

from __future__ import annotations

import datetime as _dt
import json
import os
import unittest

from tests.helpers import (edit_config, example_workspace, project_copy, remove_all, temp_dir)

from engine import config as config_module, pipeline
from engine.db import database
from engine.excel.xlsx_writer import write_sheet

HEADERS = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product", "Quantity",
           "Unit Price", "Amount", "Status"]
CUSTOMER_HEADERS = ["Customer ID", "Customer Name", "Segment", "Country"]


def sales_row(invoice: str, amount: float, quantity: int = 1) -> list:
    return [invoice, 1, _dt.date(2026, 1, 15), "C001", "Pump", quantity, amount, amount, "Posted"]


class HistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.project = project_copy(self.cleanup)
        self.workspace = example_workspace(self.cleanup, with_fixtures=False)
        write_sheet(os.path.join(self.workspace.inbox, "customers.xlsx"), CUSTOMER_HEADERS,
                    [["C001", "Customer 01", "Retail", "Saudi Arabia"]], "Customers")

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def write_sales(self, rows: list[list]) -> None:
        write_sheet(os.path.join(self.workspace.inbox, "sales_current.xlsx"), HEADERS, rows, "Sales")

    def run_once(self):
        return pipeline.run(config_module.load(self.project), self.workspace)

    def history_rows(self) -> list:
        # Through the engine, so this test is true on whichever backend ran.
        connection = database.connect(self.workspace.database)
        try:
            return connection.execute(
                "SELECT _bk, _version, _status, amount FROM hist__sales ORDER BY _bk").fetchall()
        finally:
            connection.close()

    def test_identical_rerun_creates_no_duplicates(self) -> None:
        self.write_sales([sales_row("INV-1", 100.0), sales_row("INV-2", 250.0)])
        first = self.run_once()
        second = self.run_once()
        self.assertEqual(first.status, "PASS", first.message)
        self.assertEqual(second.status, "PASS", second.message)
        self.assertEqual(len(self.history_rows()), 2)
        sales = [s for s in second.sources if s["source_id"] == "sales"][0]
        self.assertEqual(sales["new_records"], 0)
        self.assertEqual(sales["unchanged_records"], 2)

    def test_late_correction_updates_the_same_record(self) -> None:
        self.write_sales([sales_row("INV-1", 100.0)])
        self.run_once()
        self.write_sales([sales_row("INV-1", 175.0)])
        result = self.run_once()
        rows = self.history_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["_version"], 2)
        self.assertAlmostEqual(rows[0]["amount"], 175.0)
        sales = [s for s in result.sources if s["source_id"] == "sales"][0]
        self.assertEqual(sales["corrected_records"], 1)

    def test_correction_can_be_refused_and_stays_visible(self) -> None:
        edit_config(self.project,
                    lambda data: data["sources"][0].update({"corrections_allowed": False}))
        self.write_sales([sales_row("INV-1", 100.0)])
        self.run_once()
        self.write_sales([sales_row("INV-1", 175.0)])
        result = self.run_once()
        rows = self.history_rows()
        self.assertAlmostEqual(rows[0]["amount"], 100.0, msg="trusted value must not change")
        self.assertEqual(rows[0]["_version"], 1)
        with open(self.workspace.dashboard, "r", encoding="utf-8") as handle:
            dashboard = json.load(handle)
        reasons = [row["rule"] for row in dashboard["attention"]["rows"]]
        self.assertIn("correction_not_allowed", reasons)

    def test_disappearing_record_can_close_the_record(self) -> None:
        edit_config(self.project,
                    lambda data: data["sources"][0].update({"missing_record_policy": "close"}))
        self.write_sales([sales_row("INV-1", 100.0), sales_row("INV-2", 50.0)])
        self.run_once()
        self.write_sales([sales_row("INV-1", 100.0)])
        result = self.run_once()
        statuses = {row["_bk"]: row["_status"] for row in self.history_rows()}
        self.assertEqual(statuses["inv-2|1"], "closed")
        self.assertEqual(statuses["inv-1|1"], "active")
        sales = [s for s in result.sources if s["source_id"] == "sales"][0]
        self.assertEqual(sales["closed_records"], 1)

    def test_disappearing_record_is_kept_by_default(self) -> None:
        self.write_sales([sales_row("INV-1", 100.0), sales_row("INV-2", 50.0)])
        self.run_once()
        self.write_sales([sales_row("INV-1", 100.0)])
        self.run_once()
        statuses = {row["_bk"]: row["_status"] for row in self.history_rows()}
        self.assertEqual(set(statuses.values()), {"active"})

    def test_duplicate_inside_one_file_is_quarantined(self) -> None:
        edit_config(self.project,
                    lambda data: data["quality_gates"].update({"max_rejected_percent": 60}))
        self.write_sales([sales_row("INV-1", 100.0), sales_row("INV-1", 100.0)])
        result = self.run_once()
        sales = [s for s in result.sources if s["source_id"] == "sales"][0]
        self.assertEqual(sales["rows_clean"], 1)
        self.assertEqual(sales["rows_rejected"], 1)
        self.assertEqual(len(self.history_rows()), 1)


if __name__ == "__main__":
    unittest.main()
