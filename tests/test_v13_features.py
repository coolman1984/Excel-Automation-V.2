"""V13 product contracts: state machine, update modes, portable report and optional sync."""

from __future__ import annotations

import datetime as _dt
import json
import os
import unittest

from tests.helpers import edit_config, example_workspace, project_copy, remove_all
from engine import config as config_module, pipeline
from engine.db import database
from engine.excel.xlsx_writer import write_sheet

HEADERS = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product", "Quantity",
           "Unit Price", "Amount", "Status"]
CUSTOMERS = ["Customer ID", "Customer Name", "Segment", "Country"]


def sale(invoice: str, day: int, amount: float):
    return [invoice, 1, _dt.date(2026, 1, day), "C001", "Pump", 1, amount, amount, "Posted"]


class V13FeatureTest(unittest.TestCase):
    def setUp(self):
        self.cleanup = []
        self.project = project_copy(self.cleanup)
        self.workspace = example_workspace(self.cleanup, with_fixtures=False)
        write_sheet(os.path.join(self.workspace.inbox, "customers.xlsx"), CUSTOMERS,
                    [["C001", "Customer", "Retail", "Egypt"]], "Customers")

    def tearDown(self):
        remove_all(self.cleanup)

    def write_sales(self, rows):
        write_sheet(os.path.join(self.workspace.inbox, "sales_current.xlsx"), HEADERS, rows, "Sales")

    def run_once(self):
        return pipeline.run(config_module.load(self.project), self.workspace)

    def db_rows(self):
        # Through the engine, so this test is true on whichever backend ran.
        db = database.connect(self.workspace.database)
        try:
            return db.execute("SELECT _bk, _status, invoice_date, amount FROM hist__sales ORDER BY _bk").fetchall()
        finally:
            db.close()

    def test_pipeline_persists_the_product_state_machine_and_generates_html(self):
        self.write_sales([sale("INV-1", 10, 100)])
        result = self.run_once()
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.state, "COMPLETE")
        self.assertTrue(os.path.isfile(self.workspace.dashboard_html))
        state_path = os.path.join(self.workspace.run_dir(result.run_id), "state.json")
        with open(state_path, encoding="utf-8") as handle:
            state = json.load(handle)
        self.assertEqual(state["state"], "COMPLETE")
        with open(self.workspace.dashboard_html, encoding="utf-8") as handle:
            html = handle.read()
        self.assertIn("window.__DASHBOARD__", html)
        self.assertIn(result.run_id, html)

    def test_append_refuses_a_changed_existing_business_record(self):
        edit_config(self.project, lambda d: d["sources"][0].update({"update_mode": "APPEND"}))
        self.write_sales([sale("INV-1", 10, 100)])
        self.run_once()
        self.write_sales([sale("INV-1", 10, 150)])
        second = self.run_once()
        self.assertIn(second.status, ("PASS", "WARNING"))
        self.assertEqual(float(self.db_rows()[0]["amount"]), 100.0)
        sales = next(s for s in second.sources if s["source_id"] == "sales")
        self.assertEqual(sales["update_mode"], "APPEND")
        self.assertGreaterEqual(sales["rows_rejected"], 1)

    def test_replace_period_closes_missing_rows_only_inside_the_current_period(self):
        edit_config(self.project, lambda d: d["sources"][0].update(
            {"update_mode": "REPLACE_PERIOD", "period_field": "invoice_date"}))
        self.write_sales([sale("INV-1", 10, 100), sale("INV-2", 11, 200)])
        self.run_once()
        # Only Jan 10 is present in this replacement; Jan 11 must remain because the exact
        # date is the configured period in this test.
        self.write_sales([sale("INV-1", 10, 125)])
        self.run_once()
        statuses = {row["_bk"]: row["_status"] for row in self.db_rows()}
        self.assertEqual(statuses["inv-1|1"], "active")
        self.assertEqual(statuses["inv-2|1"], "active")

    def test_replace_period_requires_a_mapped_period_field(self):
        edit_config(self.project, lambda d: d["sources"][0].update(
            {"update_mode": "REPLACE_PERIOD", "period_field": "missing"}))
        with self.assertRaises(Exception) as caught:
            config_module.load(self.project)
        self.assertIn("period_field", getattr(caught.exception, "detail", str(caught.exception)))

    def test_automatic_insights_are_added_from_verified_analytics(self):
        self.write_sales([sale("INV-1", 10, 100), sale("INV-2", 11, 200)])
        result = self.run_once()
        self.assertEqual(result.status, "PASS")
        with open(self.workspace.dashboard, encoding="utf-8") as handle:
            document = json.load(handle)
        ids = {item["id"] for item in document["insights"]}
        self.assertTrue(any(item.startswith("auto_top_") for item in ids), ids)

    def test_sql_server_disabled_never_blocks_the_local_result(self):
        self.write_sales([sale("INV-1", 10, 100)])
        result = self.run_once()
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.enterprise_sync.get("status"), "DISABLED")

    def test_sql_server_missing_credentials_is_pending_not_blocking(self):
        edit_config(self.project, lambda d: d.update({"sql_server": {
            "enabled": True, "connection_string_env": "UEA_TEST_MISSING_SQLSERVER"}}))
        os.environ.pop("UEA_TEST_MISSING_SQLSERVER", None)
        self.write_sales([sale("INV-1", 10, 100)])
        result = self.run_once()
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.enterprise_sync.get("status"), "PENDING")


if __name__ == "__main__":
    unittest.main()
