"""The commands the adaptation guide tells the agent to run must work."""

from __future__ import annotations

import io
import os
import shutil
import unittest
from contextlib import redirect_stdout

from tests.helpers import EXAMPLE_PROJECT, FIXTURES, remove_all, temp_dir

from engine import cli


def run_cli(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli.main(argv)
    return code, buffer.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.work = temp_dir(self.cleanup)

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def test_doctor_passes_on_the_example_project(self) -> None:
        code, output = run_cli(["doctor", "--project", EXAMPLE_PROJECT])
        self.assertEqual(code, 0, output)
        self.assertIn("RESULT: PASS", output)

    def test_doctor_blocks_an_unapproved_project(self) -> None:
        template = os.path.join(os.path.dirname(EXAMPLE_PROJECT), "_template")
        code, output = run_cli(["doctor", "--project", template])
        self.assertEqual(code, 1)
        self.assertIn("not approved", output)

    def test_new_project_creates_a_starting_point(self) -> None:
        target = os.path.join(self.work, "MyReport")
        code, output = run_cli(["new-project", "MyReport", "--directory", target])
        self.assertEqual(code, 0, output)
        self.assertTrue(os.path.isfile(os.path.join(target, "project.json")))
        self.assertTrue(os.path.isfile(os.path.join(target, "sql", "metrics.sql")))
        code, _ = run_cli(["new-project", "MyReport", "--directory", target])
        self.assertEqual(code, 1, "an existing folder must never be overwritten")

    def test_new_project_works_on_another_drive(self) -> None:
        """On Windows the target may be on C: while the repository is on D:."""

        import os.path as ntpath_like

        original = ntpath_like.relpath

        def relpath_across_drives(path, start=None):
            raise ValueError(f"path is on mount 'C:', start on mount 'D:' ({path})")

        target = os.path.join(self.work, "OtherDrive")
        ntpath_like.relpath = relpath_across_drives
        try:
            code, output = run_cli(["new-project", "OtherDrive", "--directory", target])
        finally:
            ntpath_like.relpath = original
        self.assertEqual(code, 0, output)
        self.assertIn(target, output)
        self.assertTrue(os.path.isfile(os.path.join(target, "project.json")))

    def test_new_project_prints_a_short_path_inside_the_repository(self) -> None:
        target = os.path.join(cli.REPO_ROOT, "projects", "TempCliProject")
        try:
            code, output = run_cli(["new-project", "TempCliProject"])
            self.assertEqual(code, 0, output)
            self.assertIn("projects", output)
            self.assertNotIn(cli.REPO_ROOT, output.split("next:")[1])
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_run_processes_an_inbox(self) -> None:
        data = os.path.join(self.work, "data")
        code, output = run_cli(["run", "--project", EXAMPLE_PROJECT, "--inbox", FIXTURES,
                                "--data", data])
        self.assertEqual(code, 0, output)
        self.assertIn("status     : WARNING", output)
        self.assertTrue(os.path.isfile(os.path.join(data, "data", "dashboard.json")))

    def test_deliver_builds_and_verifies_the_operator_zip(self) -> None:
        runtime = os.path.join(self.work, "runtime")
        os.makedirs(runtime)
        for name in ("python.exe", "pythonw.exe"):
            with open(os.path.join(runtime, name), "wb") as handle:
                handle.write(b"x")
        release = os.path.join(self.work, "release")
        code, output = run_cli(["deliver", "--project", EXAMPLE_PROJECT, "--output-dir", release,
                                "--runtime", runtime])
        self.assertEqual(code, 0, output)
        self.assertIn("RESULT: PASS", output)
        self.assertTrue(os.path.isfile(os.path.join(release, "ExampleSales.zip")))

    def test_deliver_without_a_runtime_fails_the_gate(self) -> None:
        release = os.path.join(self.work, "release2")
        code, output = run_cli(["deliver", "--project", EXAMPLE_PROJECT, "--output-dir", release])
        self.assertEqual(code, 1)
        self.assertIn("private runtime", output)

    def test_package_verify_reports_a_bad_zip(self) -> None:
        release = os.path.join(self.work, "release3")
        run_cli(["deliver", "--project", EXAMPLE_PROJECT, "--output-dir", release,
                 "--allow-missing-runtime"])
        code, output = run_cli(["package", "verify", "--zip",
                                os.path.join(release, "ExampleSales.zip")])
        self.assertEqual(code, 1)
        self.assertIn("RESULT: FAIL", output)


if __name__ == "__main__":
    unittest.main()
