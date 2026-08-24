"""Reconciliation must actually catch a wrong number, not just report PASS."""

from __future__ import annotations

import sqlite3
import unittest
from decimal import Decimal

from tests.helpers import example_config, example_workspace, remove_all

from engine import pipeline
from engine.data import reconcile, types
from engine.db import database


class ReconcileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.workspace = example_workspace(self.cleanup)
        self.config = example_config()
        self.result = pipeline.run(self.config, self.workspace)
        self.connection = database.connect(self.workspace.database)
        self.run_id = self.result.run_id

    def tearDown(self) -> None:
        self.connection.close()
        remove_all(self.cleanup)

    def test_totals_pass_on_the_golden_run(self) -> None:
        checks = reconcile.run(self.connection, self.run_id, self.config.source("sales"))
        totals = [c for c in checks if c.name == "control_total_amount"]
        self.assertEqual(totals[0].status, "PASS")

    def test_a_changed_clean_value_is_detected(self) -> None:
        self.connection.execute(
            "UPDATE clean__sales SET amount = amount + 1 WHERE _row_no = (SELECT MIN(_row_no) "
            "FROM clean__sales)")
        checks = reconcile.run(self.connection, self.run_id, self.config.source("sales"))
        totals = [c for c in checks if c.name == "control_total_amount"]
        self.assertEqual(totals[0].status, "BLOCK")

    def test_a_lost_row_is_detected(self) -> None:
        self.connection.execute(
            "DELETE FROM clean__sales WHERE _row_no = (SELECT MIN(_row_no) FROM clean__sales)")
        checks = reconcile.run(self.connection, self.run_id, self.config.source("sales"))
        population = [c for c in checks if c.name == "row_population"][0]
        self.assertEqual(population.status, "BLOCK")

    def test_money_is_compared_as_exact_minor_units(self) -> None:
        self.assertEqual(types.scaled(Decimal("0.1") + Decimal("0.2"), 2), 30)
        self.assertEqual(types.scaled(0.1 + 0.2, 2), 30)
        self.assertNotEqual(types.scaled(Decimal("10.005"), 2), types.scaled(Decimal("10.00"), 2))

    def test_summary_uses_the_worst_status(self) -> None:
        make = lambda status: reconcile.Check("s", "c", "1", "1", "0", status)
        self.assertEqual(reconcile.summary([make("PASS"), make("WARNING")]), "WARNING")
        self.assertEqual(reconcile.summary([make("PASS"), make("BLOCK"), make("WARNING")]), "BLOCK")
        self.assertEqual(reconcile.summary([make("PASS")]), "PASS")

    def test_a_blocking_relationship_stops_the_run(self) -> None:
        for relationship in self.config.relationships:
            relationship["on_missing"] = "block"
        checks = reconcile.relationships(self.connection, self.config, self.run_id)
        self.assertEqual(checks[0].status, "BLOCK")


if __name__ == "__main__":
    unittest.main()
