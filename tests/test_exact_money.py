"""A trusted figure must not be rounded on its way into storage.

``types.parse`` used to turn every ``number`` into a float, so a money column was
stored as DOUBLE and project SQL summed it in binary floating point. Numbers now
stay Decimal from parsing to storage, and DuckDB - the backend the operator
package ships - declares them DECIMAL, so ``SUM(amount)`` is exact.

SQLite has no decimal type. These tests state that limit rather than papering
over it: the development fallback stores DOUBLE and loses cents at the top of the
range, while reconciliation stays exact on both backends because it reads the
staged text and adds in Decimal.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import unittest
from decimal import Decimal

from engine import config as config_module, paths, pipeline
from engine.data import types
from engine.db import database
from engine.excel.xlsx_writer import write_sheet
from tests.helpers import edit_config, project_copy, remove_all, temp_dir

HAS_DUCKDB = database.backend_available("duckdb")
HEAD = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product", "Quantity",
        "Unit Price", "Amount", "Status"]
CUSTOMER_HEAD = ["Customer ID", "Customer Name", "Segment", "Country"]
CUSTOMERS = [["C001", "Customer 01", "Retail", "Saudi Arabia"]]


class ParsingTest(unittest.TestCase):
    def test_a_number_stays_an_exact_decimal(self):
        value = types.parse("1234.56", "number")
        self.assertIsInstance(value, Decimal)
        self.assertEqual(value, Decimal("1234.56"))

    def test_a_value_double_cannot_hold_survives_parsing(self):
        self.assertEqual(types.parse("99999999999999.99", "number"),
                         Decimal("99999999999999.99"))

    def test_an_integer_column_is_still_an_int(self):
        self.assertIsInstance(types.parse("42", "integer"), int)

    def test_more_decimals_than_the_column_keeps_is_refused_clearly(self):
        with self.assertRaises(types.ParseError) as caught:
            types.parse("1.1234567890123", "number", scale=12)
        self.assertIn("decimal places", str(caught.exception))

    def test_a_narrower_scale_can_be_set_per_column(self):
        self.assertEqual(types.parse("1.23", "number", scale=2), Decimal("1.23"))
        with self.assertRaises(types.ParseError):
            types.parse("1.234", "number", scale=2)

    def test_the_json_boundary_produces_plain_numbers(self):
        self.assertEqual(types.as_json_number(Decimal("1479")), 1479)
        self.assertIsInstance(types.as_json_number(Decimal("1479")), int)
        self.assertEqual(types.as_json_number(Decimal("1234.56")), 1234.56)
        self.assertEqual(types.as_json_number("Retail"), "Retail")
        self.assertIsNone(types.as_json_number(None))

    def test_configured_thresholds_compare_as_decimals(self):
        """Decimal("0.1") == 0.1 is False, which would silently invert a filter."""

        self.assertTrue(types.same_number(Decimal("0.1"), 0.1))
        self.assertTrue(types.same_number(Decimal("5"), 5))
        self.assertFalse(types.same_number(Decimal("0.2"), 0.1))
        self.assertTrue(types.same_number("Retail", "Retail"))


class ColumnDeclarationTest(unittest.TestCase):
    def test_duckdb_declares_a_real_decimal(self):
        self.assertEqual(database.sql_type("duckdb", "number", 12), "DECIMAL(38, 12)")
        self.assertEqual(database.sql_type("duckdb", "number", 2), "DECIMAL(38, 2)")

    def test_sqlite_keeps_double_as_the_documented_fallback(self):
        self.assertEqual(database.sql_type("sqlite", "number"), "DOUBLE")

    def test_other_types_are_unchanged_on_both(self):
        for backend in ("sqlite", "duckdb"):
            self.assertEqual(database.sql_type(backend, "integer"), "BIGINT")
            self.assertEqual(database.sql_type(backend, "text"), "TEXT")
            self.assertEqual(database.sql_type(backend, "date"), "TEXT")


class ScaleConfigTest(unittest.TestCase):
    def source(self, column: dict):
        return config_module._parse_source(0, {
            "id": "s", "title": "s", "match": ["*.xlsx"],
            "columns": [column],
        })

    def test_scale_defaults_to_the_shared_default(self):
        source = self.source({"source": "A", "field": "a", "type": "number"})
        self.assertEqual(source.columns[0].scale, types.DEFAULT_SCALE)

    def test_scale_can_be_narrowed(self):
        source = self.source({"source": "A", "field": "a", "type": "number", "scale": 2})
        self.assertEqual(source.columns[0].scale, 2)

    def test_scale_beyond_the_maximum_is_refused(self):
        with self.assertRaises(Exception) as caught:
            self.source({"source": "A", "field": "a", "type": "number", "scale": 40})
        self.assertIn("scale", str(caught.exception.detail))

    def test_scale_on_a_non_number_column_is_refused(self):
        with self.assertRaises(Exception) as caught:
            self.source({"source": "A", "field": "a", "type": "text", "scale": 2})
        self.assertIn("number", str(caught.exception.detail))


@unittest.skipUnless(HAS_DUCKDB, "the production backend is not installed here")
class StorageFidelityTest(unittest.TestCase):
    """The difference between the two backends, measured rather than asserted."""

    CASES = [Decimal("12345678901234.56"), Decimal("0.000000000001"),
             Decimal("99999999999999.99")]

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def round_trip(self, backend):
        connection = database.connect(
            os.path.join(temp_dir(self.cleanup), "warehouse.db"), backend=backend)
        self.addCleanup(connection.close)
        database.create_table(connection, "m",
                              [("amount", database.sql_type(backend, "number", 12))])
        database.insert_many(connection, "m", ["amount"], [[value] for value in self.CASES])
        stored = [Decimal(str(row[0])) for row in connection.execute("SELECT amount FROM m")]
        total = Decimal(str(database.scalar(connection, "SELECT SUM(amount) FROM m")))
        return stored, total

    def test_duckdb_stores_and_sums_every_value_exactly(self):
        stored, total = self.round_trip("duckdb")
        self.assertEqual(stored, self.CASES)
        self.assertEqual(total, sum(self.CASES))

    def test_sqlite_loses_a_cent_at_the_top_of_the_range(self):
        """Not a bug to fix - the reason DuckDB is the production backend."""

        stored, total = self.round_trip("sqlite")
        self.assertNotEqual(stored, self.CASES)
        self.assertNotEqual(total, sum(self.CASES))


class ExactRunTest(unittest.TestCase):
    """End to end, on whichever backend the environment selected."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def run_with(self, rows, mutate=None, backend=None):
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        if mutate is not None:
            edit_config(project, mutate)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_money.xlsx"), HEAD, rows, "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                    CUSTOMERS, "Customers")
        config = config_module.load(project)
        if backend:
            config.database = {"backend": backend}
        return pipeline.run(config, workspace), workspace

    def control_total(self, result):
        for check in result.reconciliation:
            if check["name"] == "control_total_amount":
                return check
        self.fail("no control total was produced")

    def test_many_fractional_amounts_reconcile_exactly(self):
        rows = [["INV-%d" % index, 1, _dt.date(2026, 1, 5), "C001", "Pump", 1, 0.07, 0.07,
                 "Posted"] for index in range(1000)]
        result, _workspace = self.run_with(rows)

        self.assertEqual(result.status, "PASS", result.message)
        check = self.control_total(result)
        self.assertEqual(check["status"], "PASS")
        self.assertEqual(check["expected"], "70.00")
        self.assertEqual(check["actual"], "70.00")
        # A plain float sum of the same thousand values does not land on 70.
        self.assertNotEqual(sum([0.07] * 1000), 70.0)

    def test_a_value_needing_too_many_decimals_is_quarantined_not_rounded(self):
        rows = [
            ["INV-1", 1, _dt.date(2026, 1, 5), "C001", "Pump", 1, 100.0, 100.0, "Posted"],
            ["INV-2", 1, _dt.date(2026, 1, 6), "C001", "Valve", 1, 100.0, 1.234, "Posted"],
        ]

        def narrow(data):
            for column in data["sources"][0]["columns"]:
                if column["field"] == "amount":
                    column["scale"] = 2

        result, _workspace = self.run_with(rows, narrow)
        self.assertEqual(result.rows_rejected, 1)
        self.assertEqual(self.control_total(result)["status"], "PASS")

    def test_a_filter_on_a_fractional_value_still_matches(self):
        """The float/Decimal comparison trap: this filter must exclude, not keep."""

        rows = [
            ["INV-1", 1, _dt.date(2026, 1, 5), "C001", "Pump", 1, 0.1, 0.1, "Posted"],
            ["INV-2", 1, _dt.date(2026, 1, 6), "C001", "Valve", 1, 100.0, 100.0, "Posted"],
        ]

        def exclude_the_penny(data):
            data["sources"][0]["filters"] = [
                {"field": "amount", "operator": "not_equals", "value": 0.1}]

        result, _workspace = self.run_with(rows, exclude_the_penny)
        self.assertEqual(result.rows_filtered, 1)
        self.assertEqual(self.control_total(result)["actual"], "100.00")

    @unittest.skipUnless(HAS_DUCKDB, "the production backend is not installed here")
    def test_project_sql_sums_exactly_on_the_production_backend(self):
        """What A3 is actually for: SUM() in a project's metrics SQL."""

        rows = [["INV-%d" % index, 1, _dt.date(2026, 1, 5), "C001", "Pump", 1, 0.07, 0.07,
                 "Posted"] for index in range(1000)]
        result, workspace = self.run_with(rows, backend="duckdb")
        self.assertEqual(result.status, "PASS", result.message)

        document = pipeline.last_dashboard(workspace)
        revenue = next(item for item in document["metrics"] if item["id"] == "total_amount")
        self.assertEqual(revenue["value"], 70)


if __name__ == "__main__":
    unittest.main()
