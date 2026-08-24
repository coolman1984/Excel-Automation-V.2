"""The launcher must survive a Windows console, or the absence of one."""

from __future__ import annotations

import logging
import os
import shutil
import sys
import unittest

from tests.helpers import EXAMPLE_PROJECT, FIXTURES, edit_config, project_copy, remove_all, temp_dir

from engine import alerts as alerts_module
from engine import launch, logging_setup, paths
from engine.errors import UserError


class LaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.argv = sys.argv[:]

    def tearDown(self) -> None:
        sys.argv = self.argv
        remove_all(self.cleanup)

    def test_arguments_can_be_written_either_way(self) -> None:
        sys.argv = ["launch.py", "--port", "8123", "--project=/tmp/x", "--no-browser"]
        self.assertEqual(launch._argument("port"), "8123")
        self.assertEqual(launch._argument("project"), "/tmp/x")
        self.assertIsNone(launch._argument("data"))

    def test_preparing_the_console_never_raises(self) -> None:
        launch.prepare_console()          # a normal console
        saved = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = None, None   # pythonw.exe has no console
            launch.prepare_console()
        finally:
            sys.stdout, sys.stderr = saved

    def test_printing_a_non_ascii_title_does_not_stop_the_application(self) -> None:
        launch.prepare_console()
        print("أداء المبيعات is starting...")   # would raise on a cp1252 console

    def test_logging_works_without_a_console(self) -> None:
        saved_stderr = sys.stderr
        logger = logging.getLogger("engine")
        saved_handlers = logger.handlers[:]
        saved_flag = logging_setup._CONFIGURED
        log_file = os.path.join(temp_dir(self.cleanup), "application.log")
        try:
            sys.stderr = None
            logger.handlers = []
            logging_setup._CONFIGURED = False
            logging_setup.configure(log_file)
            self.assertEqual([h for h in logger.handlers
                              if isinstance(h, logging.StreamHandler)
                              and not isinstance(h, logging.FileHandler)], [])
            logger.info("عربي - a message with characters a Windows console cannot print")
        finally:
            for handler in logger.handlers:
                handler.close()
            sys.stderr = saved_stderr
            logger.handlers = saved_handlers
            logging_setup._CONFIGURED = saved_flag
        with open(log_file, "r", encoding="utf-8") as handle:
            self.assertIn("عربي", handle.read())

    def test_a_packaged_layout_finds_its_own_project(self) -> None:
        sys.argv = ["launch.py", "--project", EXAMPLE_PROJECT]
        self.assertEqual(launch.resolve_project_dir(), os.path.abspath(EXAMPLE_PROJECT))


class PackageRootTest(unittest.TestCase):
    """The alert file belongs next to START.bat, only when there is one."""

    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.here = launch.HERE
        self.parent = launch.PARENT

    def tearDown(self) -> None:
        launch.HERE = self.here
        launch.PARENT = self.parent
        remove_all(self.cleanup)

    def test_a_development_checkout_has_no_package_root(self) -> None:
        self.assertIsNone(launch._package_root())

    def test_an_extracted_package_reports_its_root(self) -> None:
        package_root = temp_dir(self.cleanup)
        app_dir = os.path.join(package_root, "Application")
        project_dir = os.path.join(app_dir, "app", "project")
        os.makedirs(project_dir, exist_ok=True)
        with open(os.path.join(project_dir, "project.json"), "w", encoding="utf-8") as handle:
            handle.write("{}")
        launch.HERE = os.path.join(app_dir, "app")
        launch.PARENT = app_dir
        self.assertEqual(launch._package_root(), package_root)


class FatalStartupErrorTest(unittest.TestCase):
    """A crash before the server starts must never be completely silent -
    that is exactly what happens under pythonw.exe without this handler."""

    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.log_file = os.path.join(temp_dir(self.cleanup), "application.log")
        logging_setup._CONFIGURED = False
        logging.getLogger("engine").handlers = []
        logging_setup.configure(self.log_file)

    def tearDown(self) -> None:
        for handler in logging.getLogger("engine").handlers:
            handler.close()
        logging.getLogger("engine").handlers = []
        logging_setup._CONFIGURED = False
        remove_all(self.cleanup)

    def log_content(self) -> str:
        with open(self.log_file, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_a_user_error_is_logged_with_its_plain_language_fields(self) -> None:
        error = UserError("E-CFG-003", what_happened="bad config", next_action="fix it")
        launch._fatal_startup_error(error)
        content = self.log_content()
        self.assertIn("bad config", content)
        self.assertIn("fix it", content)
        self.assertIn("E-CFG-003", content)

    def test_an_unexpected_exception_never_raises_out_of_the_handler(self) -> None:
        launch._fatal_startup_error(RuntimeError("boom"))   # must not raise
        self.assertIn("boom", self.log_content())

    def test_a_system_exit_message_is_captured(self) -> None:
        launch._fatal_startup_error(SystemExit("no project found"))
        self.assertIn("no project found", self.log_content())

    def test_with_no_console_at_all_it_still_does_not_raise(self) -> None:
        saved_out, saved_err = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = None, None
            launch._fatal_startup_error(RuntimeError("boom"))   # must not raise
        finally:
            sys.stdout, sys.stderr = saved_out, saved_err


class RunOnceAlertsTest(unittest.TestCase):
    """--run-once is meant for a scheduler with nobody watching: a failure
    there must leave something behind for whoever opens the folder next,
    since pythonw.exe's console - if there even is one - is long gone by
    the time anyone would look."""

    def setUp(self) -> None:
        self.cleanup: list[str] = []
        self.argv = sys.argv[:]
        self.here = launch.HERE
        self.parent = launch.PARENT

    def tearDown(self) -> None:
        sys.argv = self.argv
        launch.HERE = self.here
        launch.PARENT = self.parent
        remove_all(self.cleanup)

    def fake_package(self) -> str:
        """Just enough shape for launch._package_root() to recognise an
        extracted package: the marker file, nothing else."""

        package_root = temp_dir(self.cleanup)
        app_dir = os.path.join(package_root, "Application")
        project_dir = os.path.join(app_dir, "app", "project")
        os.makedirs(project_dir, exist_ok=True)
        with open(os.path.join(project_dir, "project.json"), "w", encoding="utf-8") as handle:
            handle.write("{}")
        launch.HERE = os.path.join(app_dir, "app")
        launch.PARENT = app_dir
        return package_root

    def run_once(self, project_dir: str, data_dir: str) -> int:
        sys.argv = ["launch.py", "--run-once", "--project", project_dir, "--data", data_dir]
        return launch._run_once()

    def test_a_broken_configuration_writes_an_alert(self) -> None:
        package_root = self.fake_package()
        project = project_copy(self.cleanup)
        edit_config(project, lambda data: data.update({"not_a_real_setting": True}))

        code = self.run_once(project, temp_dir(self.cleanup))
        self.assertEqual(code, 1)
        alert = os.path.join(package_root, alerts_module.FILENAME)
        self.assertTrue(os.path.isfile(alert))
        with open(alert, "r", encoding="utf-8") as handle:
            self.assertIn("E-CFG-004", handle.read())

    def test_a_successful_run_clears_a_previous_alert(self) -> None:
        package_root = self.fake_package()
        alerts_module.write(package_root, "x", "previous problem", "y")
        project = project_copy(self.cleanup)
        workspace = paths.workspace_for(project, temp_dir(self.cleanup))
        for name in ("sales_2026Q1.xlsx", "customers.xlsx"):
            shutil.copy2(os.path.join(FIXTURES, name), os.path.join(workspace.inbox, name))

        code = self.run_once(project, workspace.root)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(package_root, alerts_module.FILENAME)))

    def test_no_package_root_means_no_alert_file_is_written(self) -> None:
        """A development checkout or an explicit --project outside a
        package has nowhere sensible to put an alert - it must be skipped
        silently, not crash the scheduled run."""

        project = project_copy(self.cleanup)
        edit_config(project, lambda data: data.update({"not_a_real_setting": True}))
        code = self.run_once(project, temp_dir(self.cleanup))
        self.assertEqual(code, 1)   # still fails correctly; there is just no folder to alert in


if __name__ == "__main__":
    unittest.main()
