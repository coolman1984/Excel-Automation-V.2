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

    def commit(self, seen: dict[str, str], candidates) -> None:
        """collect_new no longer mutates seen itself - a candidate is only
        forgotten once the caller confirms it was actually handed off. Tests
        that just want 'processed' commit every candidate immediately."""

        for _path, name, fingerprint in candidates:
            seen[name] = fingerprint

    def test_a_new_file_is_noticed_once(self) -> None:
        self.write("sales_january.xlsx", 100.0)
        seen: dict[str, str] = {}
        first = automation.collect_new(self.folder, self.patterns, seen)
        self.assertEqual(len(first), 1)
        self.commit(seen, first)
        self.assertEqual(automation.collect_new(self.folder, self.patterns, seen), [],
                         "the same file must not be processed twice")

    def test_a_changed_file_is_noticed_again(self) -> None:
        self.write("sales_january.xlsx", 100.0)
        seen: dict[str, str] = {}
        self.commit(seen, automation.collect_new(self.folder, self.patterns, seen))
        self.write("sales_january.xlsx", 175.0)
        self.assertEqual(len(automation.collect_new(self.folder, self.patterns, seen)), 1)

    def test_collect_new_does_not_mutate_seen_itself(self) -> None:
        """The regression this whole feature exists for: seen used to be
        updated as a side effect of merely looking, so a file the application
        was too busy to actually process was never tried again."""

        self.write("sales_january.xlsx", 100.0)
        seen: dict[str, str] = {}
        automation.collect_new(self.folder, self.patterns, seen)
        self.assertEqual(seen, {}, "collect_new must not commit anything by itself")

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


class WatcherHardeningTest(unittest.TestCase):
    """P0-5 from the project review: a file the application was too busy to
    process, or a callback that raised, used to be marked seen anyway and so
    was silently never tried again - and that memory lived only in the
    process, so a restart forgot it entirely and recopied everything."""

    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.folder = temp_dir(self.cleanup)
        self.workspace = example_workspace(self.cleanup, with_fixtures=False)

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def make_watcher(self, on_new_files):
        project = project_copy(self.cleanup)
        edit_config(project, lambda data: data.update(
            {"automation": {"watch_folder": self.folder}}))
        config = config_module.load(project)
        return automation.Watcher(config, self.workspace, on_new_files)

    def write(self, name: str = "sales_january.xlsx") -> str:
        path = os.path.join(self.folder, name)
        write_sheet(path, HEADERS,
                   [["INV-1", 1, _dt.date(2026, 1, 15), "C001", "Pump", 1, 100.0, 100.0,
                     "Posted"]], "Sales")
        return path

    def test_a_file_the_application_was_too_busy_for_is_retried_not_dropped(self) -> None:
        self.write()
        watcher = self.make_watcher(lambda files: {"started": False, "reason": "busy"})
        self.assertEqual(watcher.check_once(), 0, "a deferred hand-off is not a processed count")
        self.assertEqual(watcher.seen, {}, "a file that was never actually started must not be forgotten")

        # The application is free now; the very next check must offer it again.
        watcher.on_new_files = lambda files: {"started": True}
        self.assertEqual(watcher.check_once(), 1)
        self.assertIn("sales_january.xlsx", watcher.seen)

    def test_a_raising_callback_does_not_mark_the_file_seen(self) -> None:
        self.write()

        def explode(files):
            raise RuntimeError("boom")

        watcher = self.make_watcher(explode)
        with self.assertRaises(RuntimeError):
            watcher.check_once()
        self.assertEqual(watcher.seen, {})

    def test_a_started_run_commits_and_persists_the_fingerprint(self) -> None:
        self.write()
        watcher = self.make_watcher(lambda files: {"started": True})
        watcher.check_once()
        self.assertIn("sales_january.xlsx", watcher.seen)
        self.assertTrue(os.path.isfile(self.workspace.watcher_state))

    def test_a_restart_remembers_what_was_already_handed_off(self) -> None:
        self.write()
        first = self.make_watcher(lambda files: {"started": True})
        first.check_once()

        second = self.make_watcher(lambda files: {"started": True})
        self.assertEqual(second.seen, first.seen)
        self.assertEqual(second.check_once(), 0,
                         "a restarted watcher must not recopy what it already handed off")

    def test_a_callback_with_no_started_key_is_treated_as_success(self) -> None:
        """Backward compatible with a callback that returns None or an
        unrelated value, matching the pre-existing server.py wiring
        (lambda files: self.process()) whose return shape this test does not
        need to know about."""

        self.write()
        watcher = self.make_watcher(lambda files: None)
        self.assertEqual(watcher.check_once(), 1)
        self.assertIn("sales_january.xlsx", watcher.seen)


if __name__ == "__main__":
    unittest.main()
