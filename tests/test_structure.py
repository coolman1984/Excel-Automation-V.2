"""Layout rows must never be counted as data, and never be dropped in silence.

The regression these tests exist for: a subtotal line whose columns happened to
be populated was staged as a record, so the published revenue was the data plus
every subtotal, and every reconciliation check still reported PASS because both
sides of every comparison contained the same phantom rows.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import unittest

from engine import config as config_module, pipeline
from engine.data import structure
from engine.excel.xlsx_writer import write_sheet
from tests.helpers import edit_config, project_copy, remove_all, temp_dir
from engine import paths

HEAD = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product", "Quantity",
        "Unit Price", "Amount", "Status"]
CUSTOMER_HEAD = ["Customer ID", "Customer Name", "Segment", "Country"]
CUSTOMERS = [["C001", "Customer 01", "Retail", "Saudi Arabia"],
             ["C002", "Customer 02", "Wholesale", "Saudi Arabia"]]


def line(invoice, day, customer, product, quantity, price, month=1):
    amount = round(quantity * price, 2)
    return [invoice, 1, _dt.date(2026, month, day), customer, product, quantity, price,
            amount, "Posted"]


class StructureRunTest(unittest.TestCase):
    """End-to-end: a file with layout rows must publish the right number."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def run_with(self, rows, mutate=None):
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        if mutate is not None:
            edit_config(project, mutate)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_layout.xlsx"), HEAD, rows, "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                    CUSTOMERS, "Customers")
        config = config_module.load(project)
        return pipeline.run(config, workspace)

    def check(self, result, name, source_id="sales"):
        for item in result.reconciliation:
            if item["name"] == name and item["source_id"] == source_id:
                return item
        self.fail(f"reconciliation check {name!r} was not produced: "
                  f"{[c['name'] for c in result.reconciliation]}")

    def revenue(self, result):
        return self.check(result, "control_total_amount")["actual"]

    # -- the original defect ---------------------------------------------
    def test_subtotal_rows_with_every_column_populated_are_not_counted_as_data(self):
        """The exact V14 defect: 3 real lines worth 600 plus two fully populated
        total rows published 1700 with every check passing."""

        rows = [
            line("INV-1", 5, "C001", "Pump", 2, 100.0),
            line("INV-2", 6, "C002", "Valve", 3, 100.0),
            ["TOTAL-JAN", 99, _dt.date(2026, 1, 31), "C001", "Total", 5, 100.0, 500.0, "Posted"],
            line("INV-3", 7, "C001", "Filter", 1, 100.0, month=2),
            ["GRAND TOTAL", 99, _dt.date(2026, 2, 28), "C001", "Total", 6, 100.0, 600.0, "Posted"],
        ]
        result = self.run_with(rows)
        self.assertEqual(result.status, "PASS", result.message)
        self.assertEqual(self.revenue(result), "600.00")
        self.assertEqual(result.rows_clean, 5)          # 3 sales + 2 customers
        self.assertEqual(result.rows_excluded, 2)
        accounting = self.check(result, "row_accounting")
        self.assertEqual(accounting["status"], "PASS")
        self.assertIn("2 total or subtotal lines", accounting["actual"])

    def test_classic_subtotal_shape_no_longer_trips_the_rejected_row_gate(self):
        """Total rows with empty key columns used to be quarantined as broken
        records, and two of them exceeded the 20 % rejection gate and blocked."""

        rows = [
            line("INV-1", 5, "C001", "Pump", 2, 100.0),
            line("INV-2", 6, "C002", "Valve", 3, 100.0),
            ["Subtotal", None, None, None, None, 5, None, 500.0, None],
            line("INV-3", 7, "C001", "Filter", 1, 100.0, month=2),
            [None, None, None, None, None, 6, None, 600.0, None],
        ]
        result = self.run_with(rows)
        self.assertEqual(result.status, "PASS", result.message)
        self.assertEqual(self.revenue(result), "600.00")
        self.assertEqual(result.rows_rejected, 0)

    # -- the new independent proof ---------------------------------------
    def test_a_total_that_disagrees_with_its_own_rows_blocks_the_run(self):
        rows = [
            line("INV-1", 5, "C001", "Pump", 2, 100.0),
            line("INV-2", 6, "C002", "Valve", 3, 100.0),
            ["Total", None, None, None, None, None, None, 900.0, None],
        ]
        result = self.run_with(rows)
        self.assertEqual(result.status, "BLOCK")
        declared = self.check(result, "source_declared_total_amount")
        self.assertEqual(declared["status"], "BLOCK")
        self.assertEqual(declared["difference"], "400")
        self.assertFalse(result.dashboard_published)

    def test_total_mismatch_can_be_downgraded_to_a_warning(self):
        rows = [
            line("INV-1", 5, "C001", "Pump", 2, 100.0),
            line("INV-2", 6, "C002", "Valve", 3, 100.0),
            ["Total", None, None, None, None, None, None, 900.0, None],
        ]

        def relax(data):
            data["sources"][0]["structure"] = {"on_total_mismatch": "warn"}

        result = self.run_with(rows, relax)
        self.assertEqual(result.status, "WARNING")
        self.assertEqual(self.check(result, "source_declared_total_amount")["status"], "WARNING")
        self.assertEqual(self.revenue(result), "500.00")

    def test_agreeing_totals_are_reported_as_verified(self):
        rows = [
            line("INV-1", 5, "C001", "Pump", 2, 100.0),
            line("INV-2", 6, "C002", "Valve", 3, 100.0),
            ["Total", None, None, None, None, None, None, 500.0, None],
        ]
        result = self.run_with(rows)
        declared = self.check(result, "source_declared_total_amount")
        self.assertEqual(declared["status"], "PASS")
        self.assertIn("agrees with the rows it covers", declared["actual"])

    # -- false positives -------------------------------------------------
    def test_a_business_name_containing_total_is_kept_and_flagged(self):
        """'Total Energies' is a real company. Losing its rows would be worse
        than the defect this feature fixes, so one weak signal only warns."""

        rows = [
            line("INV-1", 5, "C001", "Total Energies Pump", 2, 100.0),
            line("INV-2", 6, "C002", "Valve", 3, 100.0),
            line("INV-3", 7, "C001", "Total Energies Filter", 1, 100.0),
        ]
        result = self.run_with(rows)
        self.assertEqual(self.revenue(result), "600.00")
        self.assertEqual(result.rows_excluded, 0)
        suspicion = self.check(result, "rows_that_may_be_totals")
        self.assertEqual(suspicion["status"], "WARNING")
        self.assertEqual(suspicion["difference"], "2")

    def test_arabic_total_label_is_detected(self):
        rows = [
            line("INV-1", 5, "C001", "Pump", 2, 100.0),
            line("INV-2", 6, "C002", "Valve", 3, 100.0),
            ["الإجمالي", None, None, None, None, 5, None, 500.0, None],
        ]
        result = self.run_with(rows)
        self.assertEqual(result.status, "PASS", result.message)
        self.assertEqual(self.revenue(result), "500.00")
        self.assertEqual(result.rows_excluded, 1)

    def test_detection_can_be_switched_off_per_source(self):
        rows = [
            line("INV-1", 5, "C001", "Pump", 2, 100.0),
            ["Total", 99, _dt.date(2026, 1, 31), "C001", "Total", 2, 100.0, 200.0, "Posted"],
        ]

        def off(data):
            data["sources"][0]["structure"] = {"detect_total_rows": False}

        result = self.run_with(rows, off)
        self.assertEqual(result.rows_excluded, 0)
        self.assertEqual(self.revenue(result), "400.00")

    def test_section_labels_can_be_captured_into_a_mapped_column(self):
        rows = [
            ["North region", None, None, None, None, None, None, None, None],
            line("INV-1", 5, "C001", "Pump", 2, 100.0),
            ["South region", None, None, None, None, None, None, None, None],
            line("INV-2", 6, "C002", "Valve", 3, 100.0),
        ]

        def capture(data):
            columns = data["sources"][0]["columns"]
            columns.append({"source": "Region", "field": "region", "type": "text"})
            data["sources"][0]["structure"] = {"capture_section_headers_into": "region"}

        result = self.run_with(rows, capture)
        self.assertEqual(result.status, "PASS", result.message)
        self.assertEqual(result.rows_excluded, 2)
        self.assertEqual(self.revenue(result), "500.00")


class ClassifierUnitTest(unittest.TestCase):
    """Signal-level behaviour, where the safety rules live."""

    def classifier(self, **overrides):
        source = config_module._parse_source(0, {
            "id": "s", "title": "s", "match": ["*.xlsx"],
            "business_key": ["ref"],
            "columns": [
                {"source": "Ref", "field": "ref", "type": "text", "required": True},
                {"source": "Label", "field": "label", "type": "text"},
                {"source": "Amount", "field": "amount", "type": "number"},
            ],
            "control_totals": [{"field": "amount", "precision": 2}],
            **overrides,
        })
        return structure.Classifier(source)

    def test_normalisation_folds_arabic_and_punctuation(self):
        self.assertEqual(structure.normalize("TOTAL-JAN"), "total jan")
        self.assertEqual(structure.normalize("الإجمالي"), "الاجمالي")
        self.assertEqual(structure.normalize("  Grand   Total:  "), "grand total")

    def test_a_single_data_row_is_never_read_as_its_own_subtotal(self):
        """One row followed by an equal figure is ambiguous; guessing would
        delete a real record, so arithmetic needs two accumulated rows."""

        classifier = self.classifier()
        self.assertTrue(classifier.classify(2, {"ref": "A", "label": "x", "amount": "100"}).is_data)
        verdict = classifier.classify(3, {"ref": "B", "label": "y", "amount": "100"})
        self.assertTrue(verdict.is_data)
        self.assertEqual(classifier.declared_totals, [])

    def test_two_weak_signals_together_are_enough(self):
        classifier = self.classifier()
        classifier.classify(2, {"ref": "A", "label": "x", "amount": "100"})
        classifier.classify(3, {"ref": "B", "label": "y", "amount": "200"})
        # No key, figures present, and the figure equals the rows above.
        verdict = classifier.classify(4, {"ref": None, "label": None, "amount": "300"})
        self.assertEqual(verdict.kind, structure.TOTAL)
        self.assertIn("shape", verdict.signals)
        self.assertIn("arithmetic", verdict.signals)

    def test_a_standalone_total_label_is_enough_on_its_own(self):
        classifier = self.classifier()
        verdict = classifier.classify(2, {"ref": "Total", "label": None, "amount": "50"})
        self.assertEqual(verdict.kind, structure.TOTAL)
        self.assertEqual(verdict.signals[0], "label")

    def test_a_label_hint_alone_is_only_a_suspicion(self):
        classifier = self.classifier()
        verdict = classifier.classify(2, {"ref": "R1", "label": "Total Energies", "amount": "50"})
        self.assertTrue(verdict.is_data)
        self.assertEqual(len(classifier.suspicions), 1)
        self.assertEqual(classifier.suspicions[0].text, "Total Energies")

    def test_banner_above_data_and_section_between_blocks_are_told_apart(self):
        classifier = self.classifier()
        first = classifier.classify(1, {"ref": "Monthly report", "label": None, "amount": None})
        self.assertEqual(first.kind, structure.BANNER)
        classifier.classify(3, {"ref": "A", "label": "x", "amount": "100"})
        later = classifier.classify(5, {"ref": "North region", "label": None, "amount": None})
        self.assertEqual(later.kind, structure.SECTION)
        self.assertEqual(classifier.section, "North region")

    def test_a_row_empty_in_every_mapped_column_is_a_note(self):
        classifier = self.classifier()
        self.assertEqual(classifier.classify(9, {"ref": None, "label": None, "amount": None}).kind,
                         structure.NOTE)

    def test_grand_total_after_a_subtotal_matches_the_whole_file(self):
        classifier = self.classifier()
        classifier.classify(2, {"ref": "A", "label": None, "amount": "200"})
        classifier.classify(3, {"ref": "B", "label": None, "amount": "300"})
        classifier.classify(4, {"ref": "Subtotal", "label": None, "amount": "500"})
        classifier.classify(5, {"ref": "C", "label": None, "amount": "100"})
        verdict = classifier.classify(6, {"ref": "Grand Total", "label": None, "amount": "600"})
        self.assertEqual(verdict.kind, structure.TOTAL)
        totals = {total.excel_row: total for total in classifier.declared_totals}
        self.assertEqual(totals[4].covers, "block")
        self.assertTrue(totals[4].matched)
        self.assertEqual(totals[6].covers, "all")
        self.assertTrue(totals[6].matched)

    def test_an_unmatched_total_is_recorded_with_its_difference(self):
        classifier = self.classifier()
        classifier.classify(2, {"ref": "A", "label": None, "amount": "200"})
        classifier.classify(3, {"ref": "B", "label": None, "amount": "300"})
        classifier.classify(4, {"ref": "Total", "label": None, "amount": "900"})
        unverified = structure.unverified_totals(classifier.declared_totals)
        self.assertEqual(len(unverified), 1)
        self.assertEqual(str(unverified[0].declared), "900")
        self.assertEqual(str(unverified[0].data_sum), "500")

    def test_a_run_of_blank_rows_can_mark_the_end_of_the_data(self):
        classifier = self.classifier(structure={"stop_after_blank_rows": 2})
        classifier.classify(2, {"ref": "A", "label": None, "amount": "100"})
        self.assertFalse(classifier.should_stop(3))
        classifier.classify(3, {"ref": "B", "label": None, "amount": "100"})
        # Rows 4 and 5 were blank, so the reader jumps to 6.
        self.assertTrue(classifier.should_stop(6))


class StructureConfigTest(unittest.TestCase):
    def test_unknown_structure_setting_is_refused(self):
        with self.assertRaises(Exception) as caught:
            config_module._parse_source(0, {
                "id": "s", "title": "s", "match": ["*.xlsx"],
                "columns": [{"source": "A", "field": "a", "type": "text"}],
                "structure": {"detect_total_row": True},
            })
        self.assertIn("detect_total_row", str(caught.exception.detail))

    def test_unknown_on_total_mismatch_is_refused(self):
        with self.assertRaises(Exception) as caught:
            config_module._parse_source(0, {
                "id": "s", "title": "s", "match": ["*.xlsx"],
                "columns": [{"source": "A", "field": "a", "type": "text"}],
                "structure": {"on_total_mismatch": "ignore"},
            })
        self.assertIn("on_total_mismatch", str(caught.exception.detail))

    def test_section_field_must_be_mapped(self):
        with self.assertRaises(Exception) as caught:
            config_module._parse_source(0, {
                "id": "s", "title": "s", "match": ["*.xlsx"],
                "columns": [{"source": "A", "field": "a", "type": "text"}],
                "structure": {"capture_section_headers_into": "region"},
            })
        self.assertIn("region", str(caught.exception.detail))


if __name__ == "__main__":
    unittest.main()
