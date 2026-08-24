"""Configuration mistakes must fail immediately, with the exact fix."""

from __future__ import annotations

import json
import os
import unittest

from tests.helpers import EXAMPLE_PROJECT, edit_config, project_copy, remove_all

from engine import config as config_module
from engine.errors import UserError


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def _load_broken(self, mutate) -> UserError:
        project = project_copy(self.cleanup)
        edit_config(project, mutate)
        with self.assertRaises(UserError) as caught:
            config_module.load(project)
        return caught.exception

    def test_example_project_loads(self) -> None:
        config = config_module.load(EXAMPLE_PROJECT)
        self.assertEqual(config.project_name, "ExampleSales")
        self.assertTrue(config.is_approved)
        self.assertEqual(config_module.pending_approvals(config), [])
        self.assertEqual(config.source("sales").business_key, ["invoice_no", "line_no"])

    def test_template_project_is_not_approved(self) -> None:
        config = config_module.load(os.path.join(os.path.dirname(EXAMPLE_PROJECT), "_template"))
        self.assertFalse(config.is_approved)
        self.assertIn("approval.status", config_module.pending_approvals(config))

    def test_missing_file(self) -> None:
        with self.assertRaises(UserError) as caught:
            config_module.load(os.path.join(EXAMPLE_PROJECT, "nowhere"))
        self.assertEqual(caught.exception.code, "E-CFG-001")

    def test_invalid_json_points_at_the_line(self) -> None:
        project = project_copy(self.cleanup)
        with open(os.path.join(project, "project.json"), "w", encoding="utf-8") as handle:
            handle.write("{\n  \"project_name\": \"X\",\n")
        with self.assertRaises(UserError) as caught:
            config_module.load(project)
        self.assertEqual(caught.exception.code, "E-CFG-002")
        self.assertIn("line", caught.exception.next_action)

    def test_unknown_setting_is_rejected(self) -> None:
        error = self._load_broken(lambda data: data.update({"dashboardz": {}}))
        self.assertEqual(error.code, "E-CFG-004")
        self.assertIn("dashboardz", error.detail)

    def test_unknown_source_setting_is_rejected(self) -> None:
        error = self._load_broken(lambda data: data["sources"][0].update({"sheet_name": "Sales"}))
        self.assertEqual(error.code, "E-CFG-004")
        self.assertIn("sheet_name", error.detail)

    def test_unsupported_column_type(self) -> None:
        error = self._load_broken(lambda data: data["sources"][0]["columns"][0].update({"type": "money"}))
        self.assertEqual(error.code, "E-CFG-003")
        self.assertIn("money", error.detail)

    def test_business_key_must_be_mapped(self) -> None:
        error = self._load_broken(lambda data: data["sources"][0].update({"business_key": ["nope"]}))
        self.assertIn("nope", error.detail)

    def test_control_total_must_be_numeric(self) -> None:
        error = self._load_broken(
            lambda data: data["sources"][0].update({"control_totals": [{"field": "product"}]}))
        self.assertIn("product", error.detail)

    def test_duplicate_field_names(self) -> None:
        def mutate(data):
            data["sources"][0]["columns"][1]["field"] = data["sources"][0]["columns"][0]["field"]
        error = self._load_broken(mutate)
        self.assertIn("duplicate", error.detail)

    def test_relationship_must_point_at_real_sources(self) -> None:
        error = self._load_broken(lambda data: data["relationships"][0].update({"parent": "ghost"}))
        self.assertIn("parent", error.detail)

    def test_check_must_reference_mapped_fields(self) -> None:
        error = self._load_broken(
            lambda data: data["sources"][0]["checks"].append({"type": "not_null", "field": "ghost"}))
        self.assertIn("ghost", error.detail)

    def test_pending_approval_is_reported(self) -> None:
        project = project_copy(self.cleanup)
        edit_config(project, lambda data: data["business"].update({"purpose": "PENDING_APPROVAL"}))
        config = config_module.load(project)
        self.assertIn("business.purpose", config_module.pending_approvals(config))

    def test_template_config_is_valid_json_shape(self) -> None:
        template = os.path.join(os.path.dirname(EXAMPLE_PROJECT), "_template", "project.json")
        with open(template, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertIn("sources", data)


class AutomationConfigTest(unittest.TestCase):
    """C8: a typo here used to be silently swallowed - the watcher just
    looked permanently disabled, with nothing telling the operator why."""

    def setUp(self) -> None:
        self.cleanup: list[str] = []

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def _load_broken(self, mutate) -> UserError:
        project = project_copy(self.cleanup)
        edit_config(project, mutate)
        with self.assertRaises(UserError) as caught:
            config_module.load(project)
        return caught.exception

    def test_no_automation_section_means_disabled(self) -> None:
        config = config_module.load(EXAMPLE_PROJECT)
        self.assertEqual(config.automation,
                         {"watch_folder": "", "process_on_start": False,
                          "check_every_minutes": 10.0, "enabled": False})

    def test_misspelled_key_is_rejected_not_silently_ignored(self) -> None:
        error = self._load_broken(
            lambda data: data.update({"automation": {"check_every_minute": 5}}))
        self.assertEqual(error.code, "E-CFG-004")
        self.assertIn("check_every_minute", error.detail)

    def test_watch_folder_must_be_text(self) -> None:
        error = self._load_broken(
            lambda data: data.update({"automation": {"watch_folder": 123}}))
        self.assertIn("watch_folder", error.detail)

    def test_process_on_start_must_be_boolean(self) -> None:
        error = self._load_broken(
            lambda data: data.update({"automation": {"process_on_start": "yes"}}))
        self.assertIn("process_on_start", error.detail)

    def test_check_every_minutes_must_be_a_number(self) -> None:
        error = self._load_broken(
            lambda data: data.update({"automation": {"check_every_minutes": "often"}}))
        self.assertIn("check_every_minutes", error.detail)

    def test_check_every_minutes_must_be_positive(self) -> None:
        error = self._load_broken(
            lambda data: data.update({"automation": {"check_every_minutes": 0}}))
        self.assertIn("check_every_minutes", error.detail)

    def test_a_valid_automation_section_is_accepted(self) -> None:
        project = project_copy(self.cleanup)
        edit_config(project, lambda data: data.update({"automation": {
            "watch_folder": "C:\\Reports\\Incoming", "check_every_minutes": 2.5,
            "process_on_start": True}}))
        config = config_module.load(project)
        self.assertEqual(config.automation["watch_folder"], "C:\\Reports\\Incoming")
        self.assertEqual(config.automation["check_every_minutes"], 2.5)
        self.assertTrue(config.automation["process_on_start"])
        self.assertTrue(config.automation["enabled"])


if __name__ == "__main__":
    unittest.main()
