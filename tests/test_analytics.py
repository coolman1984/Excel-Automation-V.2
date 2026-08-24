"""Filtering must be arithmetic, not a second calculation engine.

The cube is only trustworthy if a filtered figure equals what the database
would answer for the same question. These tests ask both, and compare.
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

from tests.helpers import (edit_config, example_config, example_workspace, project_copy,
                           remove_all)

from engine import config as config_module, pipeline
from engine.data import cube
from engine.db import database
from engine.errors import UserError


class CubeConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def _broken(self, mutate) -> UserError:
        project = project_copy(self.cleanup)
        edit_config(project, mutate)
        config = config_module.load(project)
        with self.assertRaises(UserError) as caught:
            cube.parse(config)
        return caught.exception

    def test_example_project_parses(self) -> None:
        spec = cube.parse(example_config())
        self.assertEqual(spec["grain"], "month")
        self.assertEqual([d.id for d in spec["dimensions"]], ["segment", "product", "country"])
        self.assertEqual([m.id for m in spec["measures"]],
                         ["revenue", "units", "lines", "average_line"])

    def test_absent_analytics_is_not_an_error(self) -> None:
        project = project_copy(self.cleanup)
        edit_config(project, lambda data: data.pop("analytics"))
        self.assertIsNone(cube.parse(config_module.load(project)))

    def test_unknown_setting_is_refused(self) -> None:
        error = self._broken(lambda data: data["analytics"].update({"dimension": []}))
        self.assertEqual(error.code, "E-CFG-004")

    def test_unsupported_grain_is_refused(self) -> None:
        error = self._broken(lambda data: data["analytics"]["date"].update({"grain": "fortnight"}))
        self.assertIn("grain", error.next_action)

    def test_a_distinct_count_is_refused_with_the_reason(self) -> None:
        error = self._broken(lambda data: data["analytics"]["measures"].append(
            {"id": "customers", "aggregate": "count_distinct", "field": "customer_id"}))
        self.assertIn("cannot be filtered", error.next_action)

    def test_a_ratio_of_a_ratio_is_refused(self) -> None:
        error = self._broken(lambda data: data["analytics"]["measures"].append(
            {"id": "silly", "aggregate": "ratio", "numerator": "average_line",
             "denominator": "lines"}))
        self.assertIn("additive", error.next_action)

    def test_a_chart_must_name_a_real_measure(self) -> None:
        error = self._broken(lambda data: data["analytics"]["charts"].append(
            {"id": "x", "measure": "profit", "by": "date"}))
        self.assertIn("measure", error.next_action)

    def test_a_chart_must_name_a_real_dimension(self) -> None:
        error = self._broken(lambda data: data["analytics"]["charts"].append(
            {"id": "x", "measure": "revenue", "by": "region"}))
        self.assertIn("by", error.next_action)


class CubeArithmeticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cleanup: list[str] = []
        cls.workspace = example_workspace(cls.cleanup)
        cls.config = example_config()
        cls.result = pipeline.run(cls.config, cls.workspace)
        cls.connection = database.connect(cls.workspace.database)
        cls.spec = cube.parse(cls.config)
        cls.payload = cube.build(cls.connection, cls.config, cls.spec)
        with open(cls.workspace.dashboard, "r", encoding="utf-8") as handle:
            cls.dashboard = json.load(handle)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        remove_all(cls.cleanup)

    # -- the same arithmetic the browser does -----------------------------
    def sum_cells(self, measure_id: str, period_from=None, period_to=None,
                  dimension=None, value=None) -> float:
        index = self.payload["additive"].index(measure_id)
        dimension_index = None
        value_index = None
        if dimension is not None:
            names = [d["id"] for d in self.payload["dimensions"]]
            dimension_index = names.index(dimension)
            value_index = self.payload["dimensions"][dimension_index]["values"].index(value)
        total = Decimal(0)
        for cell in self.payload["cells"]:
            if period_from and cell["p"] < period_from:
                continue
            if period_to and cell["p"] > period_to:
                continue
            if dimension_index is not None and cell["k"][dimension_index] != value_index:
                continue
            total += Decimal(str(cell["m"][index]))
        return float(total)

    def ask_database(self, where: str = "") -> float:
        statement = cube.fact_sql(self.config, self.spec)
        row = self.connection.execute(
            f'SELECT SUM(amount) AS total FROM ({statement}) AS facts '
            f'WHERE invoice_date IS NOT NULL {where}').fetchone()
        return float(row["total"] or 0)

    def test_the_whole_cube_equals_the_trusted_total(self) -> None:
        metrics = {m["id"]: m["value"] for m in self.dashboard["metrics"]}
        self.assertAlmostEqual(self.sum_cells("revenue"), metrics["total_amount"], places=2)

    def test_filtering_by_a_dimension_matches_the_database(self) -> None:
        for segment in ("Retail", "Wholesale", "Government"):
            filtered = self.sum_cells("revenue", dimension="segment", value=segment)
            expected = self.ask_database(f"AND segment = '{segment}'")
            self.assertAlmostEqual(filtered, expected, places=2, msg=segment)

    def test_filtering_by_period_matches_the_database(self) -> None:
        for period in self.payload["periods"]:
            filtered = self.sum_cells("revenue", period_from=period, period_to=period)
            expected = self.ask_database(f"AND substr(invoice_date, 1, 7) = '{period}'")
            self.assertAlmostEqual(filtered, expected, places=2, msg=period)

    def test_a_ratio_filters_by_dividing_after_summing(self) -> None:
        revenue = self.sum_cells("revenue", dimension="segment", value="Retail")
        lines = self.sum_cells("lines", dimension="segment", value="Retail")
        row = self.connection.execute(
            f'SELECT SUM(amount) AS revenue, COUNT(*) AS lines FROM '
            f'({cube.fact_sql(self.config, self.spec)}) AS facts WHERE segment = \'Retail\''
        ).fetchone()
        self.assertAlmostEqual(revenue / lines, row["revenue"] / row["lines"], places=6)

    # -- the guard rails ---------------------------------------------------
    def test_the_run_proves_the_cube_against_a_second_pass(self) -> None:
        names = {check["name"] for check in self.result.reconciliation}
        self.assertIn("analytics_total_revenue", names)
        for check in self.result.reconciliation:
            if check["name"].startswith("analytics"):
                self.assertEqual(check["status"], "PASS", check)

    def test_a_cube_that_lost_a_row_is_detected(self) -> None:
        damaged = json.loads(json.dumps(self.payload))
        damaged["cells"].pop()
        checks = cube.verify(self.connection, self.config, self.spec, damaged)
        statuses = {name: status for name, _, _, status in checks}
        self.assertEqual(statuses["analytics_total_revenue"], "BLOCK")

    def test_the_payload_stays_small_enough_to_filter_in_a_browser(self) -> None:
        self.assertLess(len(self.payload["cells"]), 200)
        self.assertLess(len(json.dumps(self.payload)), 200000)

    def test_the_dashboard_carries_the_cube(self) -> None:
        analytics = self.dashboard["analytics"]
        self.assertEqual([c["id"] for c in analytics["charts"]],
                         ["revenue_trend", "revenue_by_segment", "revenue_by_product",
                          "units_by_month_segment"])
        self.assertEqual(analytics["periods"], ["2026-01", "2026-02", "2026-03"])


if __name__ == "__main__":
    unittest.main()
