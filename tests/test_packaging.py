"""The final ZIP must have the simple operator shape, or it must fail."""

from __future__ import annotations

import os
import unittest
import zipfile

from tests.helpers import EXAMPLE_PROJECT, remove_all, temp_dir

from engine.packaging import builder, verifier


def fake_runtime(directory: str) -> str:
    runtime = os.path.join(directory, "runtime")
    os.makedirs(runtime, exist_ok=True)
    for name in ("python.exe", "pythonw.exe", "python311.zip"):
        with open(os.path.join(runtime, name), "wb") as handle:
            handle.write(b"x")
    return runtime


class PackagingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.work = temp_dir(self.cleanup)

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def build_package(self, project_name: str = "ExampleSales") -> str:
        app_dir = os.path.join(self.work, "app")
        builder.stage_application(EXAMPLE_PROJECT, app_dir, fake_runtime(self.work))
        result = builder.build(project_name, app_dir, os.path.join(self.work, "release"))
        return result.zip_path

    # -- the good shape ----------------------------------------------------
    def test_package_has_only_the_four_visible_entries(self) -> None:
        zip_path = self.build_package()
        with zipfile.ZipFile(zip_path) as archive:
            roots = {name.split("/")[1] for name in archive.namelist() if "/" in name}
        self.assertEqual(roots, {"START.bat", "SCHEDULE.bat", "QUICK_START.html", "Application"})

    def test_package_verifies(self) -> None:
        result = verifier.verify(self.build_package())
        self.assertTrue(result.ok, result.report())

    def test_package_carries_the_project_and_the_runtime(self) -> None:
        with zipfile.ZipFile(self.build_package()) as archive:
            names = archive.namelist()
        self.assertIn("ExampleSales/Application/app/project/project.json", names)
        self.assertIn("ExampleSales/Application/app/launch.py", names)
        self.assertTrue(any(name.endswith("runtime/python.exe") for name in names))

    def test_no_developer_material_is_shipped(self) -> None:
        with zipfile.ZipFile(self.build_package()) as archive:
            names = archive.namelist()
        for forbidden in ("/tests/", "/fixtures/", "/.git/", "__pycache__", ".pyc"):
            self.assertFalse([name for name in names if forbidden in name], forbidden)

    def test_start_bat_only_starts_the_private_runtime(self) -> None:
        with zipfile.ZipFile(self.build_package()) as archive:
            content = archive.read("ExampleSales/START.bat").decode()
        self.assertIn("%APP%\\runtime\\pythonw.exe", content)
        self.assertIn("%APP%\\app\\launch.py", content)
        for forbidden in ("pip", "git", "curl", "netsh", "runas", "winget"):
            self.assertNotIn(forbidden, content.lower())

    def test_schedule_bat_registers_an_unattended_run_without_elevation(self) -> None:
        with zipfile.ZipFile(self.build_package()) as archive:
            content = archive.read("ExampleSales/SCHEDULE.bat").decode()
        self.assertIn("pythonw.exe", content)
        self.assertIn("--run-once", content)
        self.assertIn("schtasks", content)
        for forbidden in ("pip", "git", "curl", "netsh", "runas", "winget", "/ru ", "/rp "):
            self.assertNotIn(forbidden, content.lower())

    # -- the shapes that must be refused -----------------------------------
    def _zip_with(self, entries: dict[str, str]) -> str:
        path = os.path.join(self.work, "bad.zip")
        if os.path.exists(path):
            os.remove(path)
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return path

    def _good_entries(self) -> dict[str, str]:
        return {
            "Demo/START.bat": 'start "" "%~dp0Application\\runtime\\pythonw.exe" "%~dp0Application\\app\\launch.py"',
            "Demo/SCHEDULE.bat": ('schtasks /create /tn "Demo" /tr "\\"%~dp0Application\\runtime\\'
                                  'pythonw.exe\\" \\"%~dp0Application\\app\\launch.py\\" --run-once"'
                                  ' /sc HOURLY /mo 1 /f'),
            "Demo/QUICK_START.html": "<html></html>",
            "Demo/Application/app/launch.py": "print('x')",
            "Demo/Application/app/project/project.json": "{}",
            "Demo/Application/runtime/python.exe": "x",
        }

    def _blocks(self, entries: dict[str, str]) -> list[str]:
        result = verifier.verify(self._zip_with(entries))
        return [finding.message for finding in result.findings if finding.level == "BLOCK"]

    def test_reference_shape_passes(self) -> None:
        self.assertEqual(self._blocks(self._good_entries()), [])

    def test_extra_root_entry_is_refused(self) -> None:
        entries = self._good_entries()
        entries["Demo/README.md"] = "hello"
        self.assertTrue(any("unexpected entry" in message for message in self._blocks(entries)))

    def test_missing_launcher_is_refused(self) -> None:
        entries = self._good_entries()
        del entries["Demo/START.bat"]
        self.assertTrue(any("START.bat is missing" in message for message in self._blocks(entries)))

    def test_missing_schedule_is_refused(self) -> None:
        entries = self._good_entries()
        del entries["Demo/SCHEDULE.bat"]
        self.assertTrue(any("SCHEDULE.bat is missing" in message
                            for message in self._blocks(entries)))

    def test_schedule_bat_that_would_need_elevation_is_refused(self) -> None:
        for command in ("runas /user:Administrator x.exe",
                        'schtasks /create /tn "Demo" /tr "x" /sc DAILY /ru SYSTEM',
                        'schtasks /create /tn "Demo" /tr "x" /sc DAILY /rp secret123'):
            entries = self._good_entries()
            entries["Demo/SCHEDULE.bat"] = entries["Demo/SCHEDULE.bat"] + "\r\n" + command
            self.assertTrue(self._blocks(entries), command)

    def test_schedule_bat_that_does_not_schedule_run_once_is_refused(self) -> None:
        entries = self._good_entries()
        entries["Demo/SCHEDULE.bat"] = 'schtasks /create /tn "Demo" /tr "x" /sc HOURLY /mo 1'
        self.assertTrue(any("does not schedule an unattended run" in message
                            for message in self._blocks(entries)))

    def test_missing_runtime_is_refused(self) -> None:
        entries = self._good_entries()
        del entries["Demo/Application/runtime/python.exe"]
        self.assertTrue(any("private runtime" in message for message in self._blocks(entries)))

    def test_missing_project_configuration_is_refused(self) -> None:
        entries = self._good_entries()
        del entries["Demo/Application/app/project/project.json"]
        self.assertTrue(any("project configuration" in message for message in self._blocks(entries)))

    def test_developer_folder_inside_application_is_refused(self) -> None:
        entries = self._good_entries()
        entries["Demo/Application/tests/test_x.py"] = "x"
        self.assertTrue(any("developer folder" in message for message in self._blocks(entries)))

    def test_unsafe_path_is_refused(self) -> None:
        entries = self._good_entries()
        entries["Demo/../evil.txt"] = "x"
        self.assertTrue(any("unsafe path" in message for message in self._blocks(entries)))

    def test_installer_commands_in_start_are_refused(self) -> None:
        for command in ("pip install openpyxl", "git pull", "curl https://example.com/x.zip",
                        "netsh http add urlacl", "winget install python"):
            entries = self._good_entries()
            entries["Demo/START.bat"] = entries["Demo/START.bat"] + "\r\n" + command
            self.assertTrue(self._blocks(entries), command)

    def test_two_folders_in_one_zip_are_refused(self) -> None:
        entries = self._good_entries()
        entries["Other/file.txt"] = "x"
        self.assertTrue(any("exactly one folder" in message for message in self._blocks(entries)))

    def test_duckdb_project_requires_bundled_duckdb(self) -> None:
        entries = self._good_entries()
        entries["Demo/Application/app/project/project.json"] = '{"database":{"backend":"duckdb"}}'
        self.assertTrue(any("requires DuckDB" in message for message in self._blocks(entries)))
        entries["Demo/Application/runtime/duckdb/__init__.py"] = "x"
        self.assertEqual(self._blocks(entries), [])

    def test_com_project_requires_bundled_pywin32(self) -> None:
        entries = self._good_entries()
        entries["Demo/Application/app/project/project.json"] = (
            '{"sources":[{"extraction":{"mode":"excel_com"}}]}'
        )
        self.assertTrue(any("requires Excel COM" in message for message in self._blocks(entries)))
        entries["Demo/Application/runtime/Lib/site-packages/win32com/__init__.py"] = "x"
        self.assertEqual(self._blocks(entries), [])

    def test_sql_server_project_requires_bundled_pyodbc(self) -> None:
        entries = self._good_entries()
        entries["Demo/Application/app/project/project.json"] = '{"sql_server":{"enabled":true}}'
        self.assertTrue(any("SQL Server sync" in message for message in self._blocks(entries)))
        entries["Demo/Application/runtime/Lib/site-packages/pyodbc.pyd"] = "x"
        self.assertEqual(self._blocks(entries), [])


class TemplateZipTest(unittest.TestCase):
    """The other package: what a chat session receives."""

    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.work = temp_dir(self.cleanup)

    def tearDown(self) -> None:
        remove_all(self.cleanup)

    def test_template_zip_contains_what_an_agent_reads_first(self) -> None:
        from tools import make_template_zip

        zip_path = make_template_zip.build(self.work)
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
        for required in make_template_zip.REQUIRED:
            self.assertIn(f"Project-Template/{required}", names)
        for junk in ("__pycache__", "/_work/", ".pyc", "/.git/", "/release/"):
            self.assertFalse([name for name in names if junk in name], junk)


if __name__ == "__main__":
    unittest.main()
