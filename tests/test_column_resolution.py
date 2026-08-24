"""The column resolution ladder, end to end through the pipeline.

The regression: any header drift at all - a rename, a moved column, a
translated label, a unit suffix - hard-blocked the run and told the operator
to 'update the source mapping', which in practice meant calling the
adaptation agent back for a change with no business meaning. These tests run
the real pipeline against files with that drift and check the run completes,
not just that the resolver's own unit tests pass.

tests/test_resolve.py covers the matching rules themselves in isolation; this
file covers what the operator actually sees: run status, the published
figure, and the column_mapping evidence on the dashboard.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import unittest

from engine import config as config_module, paths, pipeline
from engine.excel.xlsx_writer import write_sheet
from tests.helpers import edit_config, project_copy, remove_all, temp_dir

CUSTOMER_HEAD = ["Customer ID", "Customer Name", "Segment", "Country"]
CUSTOMERS = [["C001", "Customer 01", "Retail", "Saudi Arabia"],
             ["C002", "Customer 02", "Wholesale", "Saudi Arabia"]]


def sales_rows():
    return [
        ["INV-1", 1, _dt.date(2026, 1, 5), "C001", "Pump", 2, 100.0, 200.0, "Posted"],
        ["INV-2", 1, _dt.date(2026, 1, 6), "C002", "Valve", 3, 100.0, 300.0, "Posted"],
    ]


class ColumnDriftRunTest(unittest.TestCase):
    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def run_with_header(self, header, mutate=None):
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        if mutate is not None:
            edit_config(project, mutate)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_2026.xlsx"), header, sales_rows(), "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                    CUSTOMERS, "Customers")
        config = config_module.load(project)
        return pipeline.run(config, workspace), workspace

    def check(self, result, name, source_id="sales"):
        for item in result.reconciliation:
            if item["name"] == name and item["source_id"] == source_id:
                return item
        return None

    def test_a_unit_suffix_is_absorbed_with_a_warning_not_a_block(self):
        header = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product",
                 "Quantity", "Unit Price", "Amount (SAR)", "Status"]
        result, _workspace = self.run_with_header(header)

        self.assertEqual(result.status, "WARNING", result.message)
        for total in result.reconciliation:
            if total["name"] == "control_total_amount":
                self.assertEqual(total["actual"], "500.00")
        mapping = self.check(result, "column_mapping")
        self.assertIsNotNone(mapping)
        self.assertIn("Amount", mapping["actual"])
        self.assertIn("Amount (SAR)", mapping["actual"])

    def test_reordered_words_are_absorbed_with_a_warning(self):
        header = ["No Invoice", "Line", "Invoice Date", "Customer ID", "Product",
                 "Quantity", "Unit Price", "Amount", "Status"]
        result, _workspace = self.run_with_header(header)

        self.assertEqual(result.status, "WARNING", result.message)
        mapping = self.check(result, "column_mapping")
        self.assertIn("Invoice No", mapping["actual"])
        self.assertIn("No Invoice", mapping["actual"])

    def test_a_declared_alias_absorbs_a_genuine_rename_silently(self):
        """The one case the ladder deliberately refuses to guess - a
        semantically different-looking name - is exactly what an alias is
        for, and an alias match is not a guess: PASS, not WARNING."""

        header = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product",
                 "Quantity", "Unit Price", "Total Amount", "Status"]

        def add_alias(data):
            for source in data["sources"]:
                if source["id"] == "sales":
                    for column in source["columns"]:
                        if column["field"] == "amount":
                            column["aliases"] = ["Total Amount"]

        result, _workspace = self.run_with_header(header, add_alias)
        self.assertEqual(result.status, "PASS", result.message)
        self.assertIsNone(self.check(result, "column_mapping"))

    def test_an_undeclared_semantic_rename_still_blocks(self):
        """Without the alias, the same file must still block - the ladder
        does not become less safe than before for a genuinely ambiguous
        rename."""

        header = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product",
                 "Quantity", "Unit Price", "Total Amount", "Status"]
        result, _workspace = self.run_with_header(header)
        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(result.error["support_code"], "E-IN-003")
        self.assertIn("Amount", result.error["next_action"])

    def test_a_duplicated_exact_header_still_blocks_as_ambiguous(self):
        header = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Amount",
                 "Quantity", "Unit Price", "Amount", "Status"]
        result, _workspace = self.run_with_header(header)
        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(result.error["support_code"], "E-IN-003")

    def test_the_drift_is_visible_in_the_published_dashboard(self):
        header = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product",
                 "Quantity", "Unit Price", "Amount (SAR)", "Status"]
        result, workspace = self.run_with_header(header)
        self.assertEqual(result.status, "WARNING", result.message)

        document = pipeline.last_dashboard(workspace)
        names = {check["check"] for check in document["reconciliation"]}
        self.assertIn("column_mapping", names)


class PositionalFallbackRunTest(unittest.TestCase):
    """column_order: stable is opt-in and never touches a trusted key or total."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def run_with_header(self, header, mutate):
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        edit_config(project, mutate)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_2026.xlsx"), header, sales_rows(), "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                    CUSTOMERS, "Customers")
        config = config_module.load(project)
        return pipeline.run(config, workspace)

    def test_an_unrecognisable_rename_still_blocks_without_stable_order(self):
        # invoice_date is required but is neither a business key nor a control
        # total field, so it is exactly the case positional resolution exists for.
        header = ["Invoice No", "Line", "Date Of Sale", "Customer ID", "Product",
                 "Quantity", "Unit Price", "Amount", "Status"]
        result = self.run_with_header(header, lambda data: None)
        self.assertEqual(result.status, "BLOCK")

    def test_stable_order_resolves_an_unrecognisable_rename_by_position(self):
        header = ["Invoice No", "Line", "Date Of Sale", "Customer ID", "Product",
                 "Quantity", "Unit Price", "Amount", "Status"]

        def declare_stable(data):
            for source in data["sources"]:
                if source["id"] == "sales":
                    source["column_order"] = "stable"

        result = self.run_with_header(header, declare_stable)
        self.assertEqual(result.status, "WARNING", result.message)
        self.assertEqual(result.rows_clean, 4)   # 2 sales + 2 customers


if __name__ == "__main__":
    unittest.main()
