"""A malformed CSV row must not take down the whole file.

The regression: one row with an extra delimiter or a broken quote raised
immediately from the reader and aborted extraction for every other row in the
file - so a single stray comma in a daily export could block an otherwise
unattended run. The row is now quarantined as ``malformed`` and reading
continues, exactly like an ordinary quality reject.

The low-level reader keeps its stricter default: called directly, with no
source configuration or quarantine ledger to route the row into, refusing the
whole file is still the safe choice (covered in test_v14_hardening.py). This
file covers the pipeline path, where staging can and does route the row
somewhere visible.
"""

from __future__ import annotations

import csv
import io
import json
import os
import unittest

from engine import config as config_module, paths, pipeline
from engine.data import structure
from tests.helpers import project_copy, remove_all, temp_dir


def write_csv(path: str, rows: list[list[str]]) -> None:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(buffer.getvalue())


def customers_as_csv(project: str) -> None:
    """Point the example project's customers source at a CSV file, and make
    sales optional so a run can complete on customers data alone."""

    raw_path = os.path.join(project, "project.json")
    with open(raw_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    for entry in payload["sources"]:
        if entry["id"] == "customers":
            entry["format"] = "csv"
            entry["match"] = ["customers_wide.csv"]
            entry.pop("sheet", None)
        if entry["id"] == "sales":
            entry["required"] = False
    with open(raw_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


class CsvWideRowTest(unittest.TestCase):
    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def run_with(self, rows):
        project = project_copy(self.cleanup)
        customers_as_csv(project)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_csv(os.path.join(workspace.inbox, "customers_wide.csv"), rows)
        config = config_module.load(project)
        return pipeline.run(config, workspace)

    def check(self, result, name, source_id="customers"):
        for item in result.reconciliation:
            if item["name"] == name and item["source_id"] == source_id:
                return item
        self.fail(f"reconciliation check {name!r} was not produced")

    def test_a_wide_row_no_longer_blocks_the_whole_file(self):
        rows = [
            ["Customer ID", "Customer Name", "Segment", "Country"],
            ["C001", "Customer 01", "Retail", "Saudi Arabia"],
            ["C002", "Customer 02", "Wholesale", "Saudi Arabia", "EXTRA"],
            ["C003", "Customer 03", "Retail", "Saudi Arabia"],
        ]
        result = self.run_with(rows)

        self.assertEqual(result.status, "PASS", result.message)
        self.assertEqual(result.rows_clean, 2)
        self.assertEqual(result.rows_excluded, 1)

        accounting = self.check(result, "row_accounting")
        self.assertEqual(accounting["status"], "PASS")
        self.assertIn("1 malformed row", accounting["actual"])

    def test_the_malformed_row_is_recorded_with_its_own_columns(self):
        rows = [
            ["Customer ID", "Customer Name", "Segment", "Country"],
            ["C001", "Customer 01", "Retail", "Saudi Arabia"],
            ["C002", "Customer 02", "Wholesale", "Saudi Arabia", "EXTRA"],
        ]
        project = project_copy(self.cleanup)
        customers_as_csv(project)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_csv(os.path.join(workspace.inbox, "customers_wide.csv"), rows)
        config = config_module.load(project)
        result = pipeline.run(config, workspace)
        self.assertEqual(result.status, "PASS", result.message)

        from engine.db import database
        connection = database.connect(workspace.database)
        try:
            excluded = connection.execute(
                "SELECT excel_row, row_class, reason, row_json FROM excluded_rows"
                " WHERE source_id = 'customers'").fetchall()
        finally:
            connection.close()
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["row_class"], structure.MALFORMED)
        self.assertIn("extra delimiter", excluded[0]["reason"])
        self.assertIn("EXTRA", excluded[0]["row_json"])

    def test_several_wide_rows_are_all_quarantined_not_just_the_first(self):
        rows = [
            ["Customer ID", "Customer Name", "Segment", "Country"],
            ["C001", "Customer 01", "Retail", "Saudi Arabia", "X"],
            ["C002", "Customer 02", "Wholesale", "Saudi Arabia"],
            ["C003", "Customer 03", "Retail", "Saudi Arabia", "Y"],
        ]
        result = self.run_with(rows)
        self.assertEqual(result.status, "PASS", result.message)
        self.assertEqual(result.rows_clean, 1)
        self.assertEqual(result.rows_excluded, 2)


class CsvReaderDirectCallTest(unittest.TestCase):
    """The low-level reader's own default is unchanged by this fix."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def test_strict_width_true_still_raises_by_default(self):
        from engine.errors import UserError
        from engine.excel import csv_reader

        folder = temp_dir(self.cleanup)
        path = os.path.join(folder, "broken.csv")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("A,B\n1,2,3\n")

        with self.assertRaises(UserError):
            list(csv_reader.iter_rows(path))

    def test_strict_width_false_yields_the_row_unmodified(self):
        from engine.excel import csv_reader

        folder = temp_dir(self.cleanup)
        path = os.path.join(folder, "wide.csv")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("A,B\n1,2,3\n")

        rows = list(csv_reader.iter_rows(path, strict_width=False))
        self.assertEqual(rows, [(2, ["1", "2", "3"])])


if __name__ == "__main__":
    unittest.main()
