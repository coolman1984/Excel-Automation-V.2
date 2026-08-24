"""The unattended-run alert file: appears on failure, clears itself on success."""

from __future__ import annotations

import os
import unittest

from tests.helpers import remove_all, temp_dir

from engine import alerts


class AlertsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.package_root = temp_dir(self.cleanup)

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def test_write_creates_a_readable_file_with_the_key_facts(self) -> None:
        alerts.write(self.package_root, "Sales Report", "The input file was missing a column.",
                     "Add the column and try again.", "E-IN-003")
        with open(alerts.path(self.package_root), "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("Sales Report", content)
        self.assertIn("The input file was missing a column.", content)
        self.assertIn("Add the column and try again.", content)
        self.assertIn("E-IN-003", content)

    def test_support_code_is_omitted_cleanly_when_not_given(self) -> None:
        alerts.write(self.package_root, "Sales Report", "Something went wrong.", "Try again.")
        with open(alerts.path(self.package_root), "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertNotIn("Support code:", content)

    def test_clear_removes_the_file(self) -> None:
        alerts.write(self.package_root, "Sales Report", "x", "y")
        self.assertTrue(os.path.isfile(alerts.path(self.package_root)))
        alerts.clear(self.package_root)
        self.assertFalse(os.path.exists(alerts.path(self.package_root)))

    def test_clear_without_a_prior_write_is_a_safe_no_op(self) -> None:
        alerts.clear(self.package_root)   # must not raise

    def test_a_second_write_replaces_the_first_rather_than_appending(self) -> None:
        alerts.write(self.package_root, "Sales Report", "first problem", "fix one")
        alerts.write(self.package_root, "Sales Report", "second problem", "fix two")
        with open(alerts.path(self.package_root), "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertNotIn("first problem", content)
        self.assertIn("second problem", content)

    def test_write_to_an_unwritable_location_does_not_raise(self) -> None:
        blocked = os.path.join(self.package_root, "a_file_not_a_folder")
        with open(blocked, "w", encoding="utf-8") as handle:
            handle.write("x")
        alerts.write(blocked, "Sales Report", "x", "y")   # must not raise


if __name__ == "__main__":
    unittest.main()
