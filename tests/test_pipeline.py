"""The golden path: the numbers, the reconciliation and the quarantine."""

from __future__ import annotations

import json
import os
import unittest

from tests.helpers import example_config, example_workspace, golden, remove_all

from engine import pipeline


class GoldenRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cleanup: list[str] = []
        cls.workspace = example_workspace(cls.cleanup)
        cls.config = example_config()
        cls.result = pipeline.run(cls.config, cls.workspace)
        with open(cls.workspace.dashboard, "r", encoding="utf-8") as handle:
            cls.dashboard = json.load(handle)
        cls.golden = golden()

    @classmethod
    def tearDownClass(cls) -> None:
        remove_all(cls.cleanup)

    def test_status_matches_golden(self) -> None:
        self.assertEqual(self.result.status, self.golden["expected_status"], self.result.message)

    def test_row_population_matches_golden(self) -> None:
        expected = self.golden["expected_rows"]
        self.assertEqual(self.result.rows_in, expected["read"])
        self.assertEqual(self.result.rows_clean, expected["accepted"])
        self.assertEqual(self.result.rows_rejected, expected["needs_attention"])
        self.assertEqual(self.result.rows_filtered, expected["out_of_scope"])

    def test_kpis_match_golden(self) -> None:
        values = {metric["id"]: metric["value"] for metric in self.dashboard["metrics"]}
        for metric_id, expected in self.golden["expected_kpis"].items():
            self.assertAlmostEqual(values[metric_id], expected, places=2, msg=metric_id)

    def test_control_totals_reconcile_exactly(self) -> None:
        totals = [c for c in self.result.reconciliation if c["name"].startswith("control_total_")]
        self.assertTrue(totals)
        for check in totals:
            self.assertEqual(check["status"], "PASS", check)
            self.assertEqual(float(check["difference"]), 0.0)

    def test_every_row_is_accounted_for(self) -> None:
        population = [c for c in self.result.reconciliation if c["name"] == "row_population"]
        self.assertTrue(population)
        for check in population:
            self.assertEqual(check["status"], "PASS", check)

    def test_rejected_rows_stay_visible_with_their_location(self) -> None:
        attention = self.dashboard["attention"]
        self.assertEqual(attention["total"], self.golden["expected_rows"]["needs_attention"])
        for row in attention["rows"]:
            self.assertTrue(row["file_name"])
            self.assertGreater(row["excel_row"], 1)
            self.assertTrue(row["message"])

    def test_unknown_customer_is_a_warning_not_a_silent_pass(self) -> None:
        link = [c for c in self.result.reconciliation if c["name"] == "link_to_customers"]
        self.assertEqual(link[0]["status"], "WARNING")

    def test_lineage_records_every_input_file(self) -> None:
        names = {item["file_name"] for item in self.dashboard["run"]["files"]}
        self.assertEqual(names, set(self.golden["fixtures"]))
        for item in self.dashboard["run"]["files"]:
            self.assertEqual(len(item["sha256"]), 64)

    def test_dashboard_carries_the_evidence(self) -> None:
        self.assertTrue(self.dashboard["reconciliation"])
        for kpi in self.dashboard["kpis"]:
            self.assertIn("sql", kpi["evidence"])

    def test_source_files_are_not_modified(self) -> None:
        from tests.helpers import FIXTURES
        from engine.excel.discovery import hash_file
        for name in self.golden["fixtures"]:
            original = hash_file(os.path.join(FIXTURES, name))
            copied = [f for f in self.dashboard["run"]["files"] if f["file_name"] == name][0]
            self.assertEqual(original, copied["sha256"])


if __name__ == "__main__":
    unittest.main()
