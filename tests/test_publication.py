"""Publication has one commit point.

The regression here: the result was two separate atomic writes followed by two
more after enterprise synchronization. Each write was atomic on its own, but the
set was not, so a crash between them left ``dashboard.json`` from this run beside
``dashboard.html`` from the previous one - and the first pair was published while
the run still said ``VERIFYING``.
"""

from __future__ import annotations

import json
import os
import unittest

from engine import config as config_module, paths, pipeline
from engine.data import archive
from tests.helpers import (edit_config, example_workspace, project_copy, remove_all,
                           temp_dir)


class PublicationTest(unittest.TestCase):
    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def complete_run(self):
        workspace = example_workspace(self.cleanup)
        result = pipeline.run(config_module.load(project_copy(self.cleanup)), workspace)
        self.assertIn(result.status, ("PASS", "WARNING"), result.message)
        return workspace, result

    def read(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    # -- the commit point -------------------------------------------------
    def test_pointer_names_the_run_and_holds_a_matching_pair(self):
        workspace, result = self.complete_run()

        self.assertEqual(archive.current_run(workspace), result.run_id)
        folder = os.path.join(workspace.published, result.run_id)
        document = json.loads(self.read(os.path.join(folder, "dashboard.json")))
        html = self.read(os.path.join(folder, "dashboard.html"))

        self.assertEqual(document["run"]["run_id"], result.run_id)
        self.assertIn(result.run_id, html)

    def test_the_published_result_is_already_complete(self):
        """Nothing intermediate is ever published: the state is final first."""

        workspace, _result = self.complete_run()
        document = pipeline.last_dashboard(workspace)
        self.assertEqual(document["run"]["state"], "COMPLETE")
        self.assertIn("enterprise_sync", document)
        self.assertIn(document["run"]["state"], self.read(workspace.dashboard_html))

    def test_legacy_copies_match_the_published_pair(self):
        workspace, result = self.complete_run()
        folder = os.path.join(workspace.published, result.run_id)
        self.assertEqual(self.read(workspace.dashboard),
                         self.read(os.path.join(folder, "dashboard.json")))
        self.assertEqual(self.read(workspace.dashboard_html),
                         self.read(os.path.join(folder, "dashboard.html")))

    # -- recovery ---------------------------------------------------------
    def test_a_mixed_legacy_pair_does_not_change_what_is_read(self):
        workspace, result = self.complete_run()

        # Simulate a crash partway through refreshing the convenience copies.
        with open(workspace.dashboard_html, "w", encoding="utf-8") as handle:
            handle.write("<html>a dashboard from an older run</html>")
        with open(workspace.dashboard, "w", encoding="utf-8") as handle:
            handle.write("{ not json")

        document = pipeline.last_dashboard(workspace)
        self.assertIsNotNone(document)
        self.assertEqual(document["run"]["run_id"], result.run_id)

    def test_mirror_repairs_the_legacy_copies(self):
        workspace, result = self.complete_run()
        with open(workspace.dashboard, "w", encoding="utf-8") as handle:
            handle.write("{ not json")

        repaired = archive.mirror(workspace)
        self.assertIn(workspace.dashboard, repaired)
        self.assertEqual(json.loads(self.read(workspace.dashboard))["run"]["run_id"],
                         result.run_id)

    def test_mirror_is_a_no_op_when_nothing_drifted(self):
        workspace, _result = self.complete_run()
        self.assertEqual(archive.mirror(workspace), [])

    def test_a_failed_run_leaves_the_pointer_on_the_last_good_result(self):
        workspace = example_workspace(self.cleanup)
        project = project_copy(self.cleanup)
        good = pipeline.run(config_module.load(project), workspace)
        self.assertTrue(good.dashboard_published)

        def require_a_missing_column(data):
            data["sources"][0]["columns"].append(
                {"source": "Not In The File", "field": "missing", "type": "text",
                 "required": True})

        edit_config(project, require_a_missing_column)
        failed = pipeline.run(config_module.load(project), workspace)

        self.assertEqual(failed.status, "BLOCK")
        self.assertFalse(failed.dashboard_published)
        self.assertEqual(archive.current_run(workspace), good.run_id)
        self.assertEqual(pipeline.last_dashboard(workspace)["run"]["run_id"], good.run_id)

    def test_a_second_run_moves_the_pointer_forward(self):
        workspace = example_workspace(self.cleanup)
        config = config_module.load(project_copy(self.cleanup))
        first = pipeline.run(config, workspace)
        second = pipeline.run(config, workspace)

        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(archive.current_run(workspace), second.run_id)

    # -- housekeeping -----------------------------------------------------
    def test_pruning_keeps_the_live_run(self):
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        for index in range(4):
            archive.publish(workspace, f"run_{index}", {"dashboard.json": "{}"}, keep=2)

        remaining = sorted(name for name in os.listdir(workspace.published)
                           if os.path.isdir(os.path.join(workspace.published, name)))
        self.assertEqual(archive.current_run(workspace), "run_3")
        self.assertIn("run_3", remaining)
        self.assertLessEqual(len(remaining), 2)

    def test_no_pointer_means_nothing_is_published(self):
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        self.assertIsNone(archive.current_run(workspace))
        self.assertIsNone(pipeline.last_dashboard(workspace))
        self.assertEqual(archive.mirror(workspace), [])

    def test_a_pointer_to_a_missing_folder_is_ignored(self):
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        archive.atomic_write(workspace.published_pointer, "run_that_was_deleted")
        self.assertIsNone(archive.current_run(workspace))
        self.assertEqual(archive.published_file(workspace, "dashboard.json"),
                         os.path.join(workspace.data, "dashboard.json"))


if __name__ == "__main__":
    unittest.main()
