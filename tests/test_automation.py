"""Recurring runs: notice a genuinely new file, ignore the same one twice."""

from __future__ import annotations

import datetime as _dt
import os
import unittest

from tests.helpers import (edit_config, example_config, example_workspace, project_copy,
                           remove_all, temp_dir)

from engine import automation, config as config_module
from engine.excel.xlsx_writer import write_sheet

HEADERS = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product", "Quantity",
           "Unit Price", "Amount", "Status"]


class AutomationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.folder = temp_dir(self.cleanup)
        self.workspace = example_workspace(self.cleanup, with_fixtures=False)
        self.config = example_config()
        self.patterns = automation.matching_patterns(self.config)

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def write(self, name: str, amount: float) -> str:
        path = os.path.join(self.folder, name)
        write_sheet(path, HEADERS,
                    [["INV-1", 1, _dt.date(2026, 1, 15), "C001", "Pump", 1, amount, amount,
                      "Posted"]], "Sales")
        return path

    def test_defaults_are_off(self) -> None:
        settings = automation.settings(self.config)
        self.assertFalse(settings["enabled"])
        self.assertEqual(settings["watch_folder"], "")

    def test_settings_are_read(self) -> None:
        project = project_copy(self.cleanup)
        edit_config(project, lambda data: data.update({"automation": {
            "watch_folder": self.folder, "check_every_minutes": 5, "process_on_start": True}}))
        settings = automation.settings(config_module.load(project))
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["check_every_minutes"], 5)

    def test_a_new_file_is_noticed_once(self) -> None:
        self.write("sales_january.xlsx", 100.0)
        seen: dict[str, str] = {}
        first = automation.collect_new(self.folder, self.patterns, seen)
        self.assertEqual(len(first), 1)
        self.assertEqual(automation.collect_new(self.folder, self.patterns, seen), [],
                         "the same file must not be processed twice")

    def test_a_changed_file_is_noticed_again(self) -> None:
        self.write("sales_january.xlsx", 100.0)
        seen: dict[str, str] = {}
        automation.collect_new(self.folder, self.patterns, seen)
        self.write("sales_january.xlsx", 175.0)
        self.assertEqual(len(automation.collect_new(self.folder, self.patterns, seen)), 1)

    def test_files_the_report_does_not_want_are_ignored(self) -> None:
        for name in ("notes.txt", "~$sales_january.xlsx", ".hidden.xlsx", "invoice_list.xlsx"):
            with open(os.path.join(self.folder, name), "wb") as handle:
                handle.write(b"x")
        self.assertEqual(automation.collect_new(self.folder, self.patterns, {}), [])

    def test_a_missing_folder_is_not_a_crash(self) -> None:
        self.assertEqual(automation.collect_new("/no/such/folder", self.patterns, {}), [])

    def test_the_watcher_copies_into_the_inbox_and_asks_for_a_run(self) -> None:
        project = project_copy(self.cleanup)
        edit_config(project, lambda data: data.update({"automation": {"watch_folder": self.folder}}))
        config = config_module.load(project)
        self.write("sales_january.xlsx", 100.0)

        started: list[list[str]] = []
        watcher = automation.Watcher(config, self.workspace, started.append)
        self.assertTrue(watcher.enabled)
        self.assertEqual(watcher.check_once(), 1)
        self.assertEqual(len(started), 1)
        self.assertIn("sales_january.xlsx", os.listdir(self.workspace.inbox))
        self.assertEqual(watcher.check_once(), 0, "an unchanged folder must start no run")

    def test_no_folder_means_no_watcher(self) -> None:
        watcher = automation.Watcher(self.config, self.workspace, lambda files: None)
        self.assertFalse(watcher.enabled)
        watcher.start()
        self.assertIsNone(watcher._thread)


if __name__ == "__main__":
    unittest.main()
