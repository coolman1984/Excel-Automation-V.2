"""The trusted formula lives once, in SQL, and the dashboard must match it."""

from __future__ import annotations

import os
import unittest

from tests.helpers import EXAMPLE_PROJECT, remove_all, temp_dir

from engine.data import metrics
from engine.errors import UserError
from engine.report import dashboard as dashboard_module


class MetricsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def write(self, content: str) -> str:
        path = os.path.join(temp_dir(self.cleanup), "metrics.sql")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def test_example_metrics_parse(self) -> None:
        definitions = metrics.parse_file(os.path.join(EXAMPLE_PROJECT, "sql", "metrics.sql"))
        identifiers = [definition.id for definition in definitions]
        self.assertIn("total_amount", identifiers)
        total = [d for d in definitions if d.id == "total_amount"][0]
        self.assertEqual(total.kind, "kpi")
        self.assertEqual(total.title, "Total revenue")
        self.assertEqual(total.format, "money")
        self.assertEqual(total.unit, "SAR")
        self.assertTrue(total.sql.lower().startswith("select"))

    def test_missing_file_is_not_a_crash(self) -> None:
        self.assertEqual(metrics.parse_file("/no/such/file.sql"), [])

    def test_metric_without_sql_is_rejected(self) -> None:
        path = self.write("-- metric: empty\n-- kind: kpi\n")
        with self.assertRaises(UserError) as caught:
            metrics.parse_file(path)
        self.assertEqual(caught.exception.code, "E-SQL-001")

    def test_duplicate_metric_id_is_rejected(self) -> None:
        path = self.write("-- metric: a\nSELECT 1 AS value;\n-- metric: a\nSELECT 2 AS value;\n")
        with self.assertRaises(UserError):
            metrics.parse_file(path)

    def test_unknown_kind_is_rejected(self) -> None:
        path = self.write("-- metric: a\n-- kind: gauge\nSELECT 1 AS value;\n")
        with self.assertRaises(UserError):
            metrics.parse_file(path)

    def test_a_metric_may_not_write_to_the_database(self) -> None:
        import sqlite3

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        definition = metrics.MetricDefinition(id="bad", sql="DELETE FROM runs")
        with self.assertRaises(UserError) as caught:
            metrics.compute(connection, [definition])
        self.assertEqual(caught.exception.code, "E-SQL-001")

    def test_broken_sql_names_the_metric(self) -> None:
        import sqlite3

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        definition = metrics.MetricDefinition(id="oops", sql="SELECT * FROM v_missing")
        with self.assertRaises(UserError) as caught:
            metrics.compute(connection, [definition])
        self.assertIn("oops", caught.exception.next_action)

    def test_kpi_series_and_table_shapes(self) -> None:
        import sqlite3

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        payloads = metrics.compute(connection, [
            metrics.MetricDefinition(id="one", sql="SELECT 42 AS value", kind="kpi"),
            metrics.MetricDefinition(id="two", sql="SELECT 'a' AS label, 1 AS value", kind="series"),
            metrics.MetricDefinition(id="three", sql="SELECT 1 AS x, 2 AS y", kind="table"),
        ])
        self.assertEqual(payloads[0]["value"], 42)
        self.assertEqual(payloads[1]["points"], [{"label": "a", "value": 1, "series": None}])
        self.assertEqual(payloads[2]["columns"], ["x", "y"])
        self.assertEqual(payloads[2]["rows"], [[1, 2]])

    def test_dashboard_verify_catches_a_changed_number(self) -> None:
        payloads = [{"id": "total", "kind": "kpi", "value": 100.0, "title": "Total"}]
        document = {"schema_version": 1, "project": {}, "run": {}, "charts": [], "tables": [],
                    "reconciliation": [],
                    "kpis": [{"id": "total", "title": "Total", "value": 101.0}]}
        with self.assertRaises(UserError) as caught:
            dashboard_module.verify(document, payloads)
        self.assertIn("did not match", caught.exception.what_happened)

    def test_dashboard_verify_accepts_matching_numbers(self) -> None:
        payloads = [{"id": "total", "kind": "kpi", "value": 100.0, "title": "Total"}]
        document = {"schema_version": 1, "project": {}, "run": {}, "charts": [], "tables": [],
                    "reconciliation": [],
                    "kpis": [{"id": "total", "title": "Total", "value": 100}]}
        dashboard_module.verify(document, payloads)


if __name__ == "__main__":
    unittest.main()
