"""V14 hardening: streaming intake, safer files, richer decision signals and UI contracts."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from engine import config as config_module, pipeline
from engine.data import insights, staging
from engine.errors import UserError
from engine.excel import csv_reader, discovery
from tests.helpers import example_workspace, project_copy, remove_all


class IntakeHardeningTest(unittest.TestCase):
    def setUp(self):
        self.cleanup = []

    def tearDown(self):
        remove_all(self.cleanup)

    def temp_file(self, name: str, content: bytes) -> str:
        folder = tempfile.mkdtemp(prefix="uea_v14_")
        self.cleanup.append(folder)
        path = os.path.join(folder, name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def test_utf16_csv_is_read_without_loading_as_utf8_garbage(self):
        path = self.temp_file("legacy.csv", "ID;Name\r\n1;Café\r\n".encode("utf-16"))
        headers, rows = csv_reader.read_block(path)
        self.assertEqual(headers, ["ID", "Name"])
        self.assertEqual(rows[0][1], ["1", "Café"])

    def test_csv_row_with_extra_delimiter_is_blocked_not_truncated(self):
        path = self.temp_file("broken.csv", b"A,B\n1,2,3\n")
        with self.assertRaises(UserError) as caught:
            list(csv_reader.iter_rows(path))
        self.assertIn("more columns", caught.exception.what_happened)

    def test_empty_source_is_blocked_before_extraction(self):
        folder = tempfile.mkdtemp(prefix="uea_v14_")
        self.cleanup.append(folder)
        inbox = os.path.join(folder, "inbox"); work = os.path.join(folder, "work")
        os.makedirs(inbox)
        open(os.path.join(inbox, "sales.xlsx"), "wb").close()
        with self.assertRaises(UserError) as caught:
            discovery.collect("sales", inbox, ["sales*.xlsx"], work)
        self.assertIn("empty", caught.exception.what_happened.lower())

    def test_sources_with_same_filename_get_isolated_safe_copies(self):
        folder = tempfile.mkdtemp(prefix="uea_v14_")
        self.cleanup.append(folder)
        inbox = os.path.join(folder, "inbox"); work = os.path.join(folder, "work")
        os.makedirs(inbox)
        with open(os.path.join(inbox, "shared.csv"), "w", encoding="utf-8") as h:
            h.write("A\n1\n")
        a = discovery.collect("source_a", inbox, ["shared.csv"], work)[0]
        b = discovery.collect("source_b", inbox, ["shared.csv"], work)[0]
        self.assertNotEqual(a.workspace_path, b.workspace_path)
        self.assertTrue(a.workspace_path.endswith(os.path.join("source_a", "shared.csv")))

    def test_duplicate_mapped_header_is_blocked_as_ambiguous(self):
        class Col:
            def __init__(self, source, field, required=True):
                self.source, self.field, self.required = source, field, required
        class Src:
            id = "x"
            columns = [Col("Amount", "amount")]
        with self.assertRaises(UserError) as caught:
            staging._map_headers(Src(), ["Amount", "Amount"], "x.xlsx")
        self.assertIn("more than once", caught.exception.what_happened)


class DecisionDashboardTest(unittest.TestCase):
    def setUp(self):
        self.cleanup = []
        self.project = project_copy(self.cleanup)
        self.workspace = example_workspace(self.cleanup, with_fixtures=True)

    def tearDown(self):
        remove_all(self.cleanup)

    def test_dashboard_has_decision_confidence_and_source_freshness_metadata(self):
        result = pipeline.run(config_module.load(self.project), self.workspace)
        self.assertIn(result.status, ("PASS", "WARNING"))
        with open(self.workspace.dashboard, encoding="utf-8") as handle:
            document = json.load(handle)
        self.assertIn("decision", document)
        self.assertIn("acceptance_rate", document["decision"])
        self.assertTrue(all("modified_at" in f for f in document["run"]["files"]))

    def test_static_dashboard_contains_executive_cockpit_and_accessible_focus(self):
        root = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(root, "engine", "webapp", "static", "index.html"), encoding="utf-8") as handle:
            html = handle.read()
        with open(os.path.join(root, "engine", "webapp", "static", "styles.css"), encoding="utf-8") as handle:
            css = handle.read()
        self.assertIn('id="decision-cockpit"', html)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion", css)

    def test_robust_anomaly_and_reversal_are_evidence_backed(self):
        periods = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
        values = [100, 105, 110, 115, 120, 300]
        analytics = {
            "periods": periods,
            "dimensions": [],
            "additive": ["revenue"],
            "kpis": ["revenue"],
            "measures": [{"id": "revenue", "title": "Revenue", "aggregate": "sum", "goal_direction": "up"}],
            "cells": [{"p": p, "k": [], "m": [v]} for p, v in zip(periods, values)],
        }
        got = insights._automatic_analytics_insights(analytics)
        ids = {x["id"] for x in got}
        self.assertIn("auto_anomaly_revenue", ids)
        anomaly = next(x for x in got if x["id"] == "auto_anomaly_revenue")
        self.assertEqual(anomaly["evidence"]["type"], "robust_anomaly")


if __name__ == "__main__":
    unittest.main()
