"""A failed run must never damage what the business already trusts."""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import sqlite3
import unittest

from tests.helpers import (edit_config, example_workspace, project_copy, remove_all)

from engine import config as config_module, pipeline
from engine.data import archive
from engine.excel.xlsx_writer import write_sheet

HEADERS = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product", "Quantity",
           "Unit Price", "Amount", "Status"]


class RecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.project = project_copy(self.cleanup)
        self.workspace = example_workspace(self.cleanup, with_fixtures=False)
        write_sheet(os.path.join(self.workspace.inbox, "customers.xlsx"),
                    ["Customer ID", "Customer Name", "Segment", "Country"],
                    [["C001", "Customer 01", "Retail", "Saudi Arabia"]], "Customers")
        self.write_sales([["INV-1", 1, _dt.date(2026, 1, 15), "C001", "Pump", 2, 50.0, 100.0,
                           "Posted"]])
        self.first = pipeline.run(config_module.load(self.project), self.workspace)
        self.assertEqual(self.first.status, "PASS", self.first.message)
        with open(self.workspace.dashboard, "r", encoding="utf-8") as handle:
            self.good_dashboard = json.load(handle)

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def write_sales(self, rows, headers=None) -> None:
        write_sheet(os.path.join(self.workspace.inbox, "sales_current.xlsx"),
                    headers or HEADERS, rows, "Sales")

    def _run(self):
        return pipeline.run(config_module.load(self.project), self.workspace)

    def _history(self):
        connection = sqlite3.connect(self.workspace.database)
        try:
            return connection.execute("SELECT COUNT(*), SUM(amount) FROM hist__sales").fetchone()
        finally:
            connection.close()

    def test_missing_column_blocks_and_keeps_the_last_dashboard(self) -> None:
        before = self._history()
        headers = [header for header in HEADERS if header != "Amount"]
        self.write_sales([["INV-2", 1, _dt.date(2026, 1, 16), "C001", "Pump", 1, 10.0, "Posted"]],
                         headers=headers)
        result = self._run()
        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(result.error["support_code"], "E-IN-003")
        self.assertTrue(result.error["trusted_data_safe"])
        self.assertFalse(result.dashboard_published)
        with open(self.workspace.dashboard, "r", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), self.good_dashboard)
        self.assertEqual(self._history(), before)

    def test_missing_required_file_blocks_with_a_clear_next_action(self) -> None:
        os.remove(os.path.join(self.workspace.inbox, "sales_current.xlsx"))
        result = self._run()
        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(result.error["support_code"], "E-IN-001")
        self.assertIn("press Process again", result.error["next_action"])

    def test_too_many_bad_rows_rolls_the_whole_run_back(self) -> None:
        before = self._history()
        edit_config(self.project,
                    lambda data: data["quality_gates"].update({"max_rejected_percent": 10}))
        self.write_sales([["INV-2", 1, _dt.date(2026, 1, 16), "C001", "Pump", "many", 10.0, 10.0,
                           "Posted"],
                          ["INV-3", 1, _dt.date(2026, 1, 17), "C001", "Pump", "lots", 10.0, 10.0,
                           "Posted"]])
        result = self._run()
        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(result.error["support_code"], "E-VAL-001")
        self.assertEqual(self._history(), before, "history must be untouched after a failed run")

    def test_unapproved_meaning_blocks_before_any_work(self) -> None:
        edit_config(self.project, lambda data: data["approval"].update(
            {"status": "PENDING_APPROVAL"}))
        result = self._run()
        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(result.error["support_code"], "E-CFG-005")

    def test_archive_holds_a_restorable_copy(self) -> None:
        run_id = self.first.run_id
        archived = os.path.join(self.workspace.archive, run_id)
        self.assertTrue(os.path.isdir(archived))
        self.assertEqual(archive.latest(self.workspace.archive), run_id)

        os.remove(self.workspace.dashboard)
        archive.restore(self.workspace.archive, run_id, self.workspace.data)
        with open(self.workspace.dashboard, "r", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["run"]["run_id"], run_id)

    def test_archive_keeps_only_the_agreed_number_of_runs(self) -> None:
        base = os.path.join(self.workspace.archive)
        for index in range(5):
            os.makedirs(os.path.join(base, f"run_x{index}"), exist_ok=True)
        archive.prune(base, keep=2)
        self.assertLessEqual(len([n for n in os.listdir(base)
                                  if os.path.isdir(os.path.join(base, n))]), 2)

    def test_atomic_write_never_leaves_a_half_file(self) -> None:
        target = os.path.join(self.workspace.data, "atomic.json")
        archive.atomic_write(target, json.dumps({"a": 1}))
        archive.atomic_write(target, json.dumps({"a": 2}))
        with open(target, "r", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"a": 2})
        leftovers = [n for n in os.listdir(self.workspace.data) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
