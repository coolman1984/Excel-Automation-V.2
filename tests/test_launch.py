"""The launcher must survive a Windows console, or the absence of one."""

from __future__ import annotations

import logging
import os
import sys
import unittest

from tests.helpers import EXAMPLE_PROJECT, remove_all, temp_dir

from engine import launch, logging_setup


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


if __name__ == "__main__":
    unittest.main()
