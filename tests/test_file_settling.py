"""File settling: a real elapsed-time window, not two probes 80ms apart.

The regression this exists for (P0-4 from the project review): a file whose
size and mtime happened to match across two probes 80ms apart was accepted as
stable, but a slow network copy can easily pause between write batches for
well over that - so a still-transferring file could be accepted as complete.
"""

from __future__ import annotations

import os
import threading
import time
import unittest

from engine.errors import UserError
from engine.excel import discovery
from tests.helpers import remove_all, temp_dir


class StableStatTest(unittest.TestCase):
    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def path(self, name="file.xlsx"):
        return os.path.join(temp_dir(self.cleanup), name)

    def test_a_file_that_never_changes_settles_after_the_window(self):
        path = self.path()
        with open(path, "wb") as handle:
            handle.write(b"x" * 100)
        started = time.monotonic()
        discovery._stable_stat(path, min_settle_seconds=0.15, poll_interval=0.02)
        self.assertGreaterEqual(time.monotonic() - started, 0.15)

    def test_a_file_still_growing_past_the_settle_window_is_not_accepted_early(self):
        """The core of the fix: growth that stops only briefly - shorter than
        the settle window - must not be mistaken for completion."""

        path = self.path()
        with open(path, "wb") as handle:
            handle.write(b"x")

        def slow_writer():
            for _ in range(4):
                time.sleep(0.08)   # a pause shorter than the settle window below
                with open(path, "ab") as handle:
                    handle.write(b"y" * 10)

        writer = threading.Thread(target=slow_writer)
        writer.start()
        try:
            result = discovery._stable_stat(path, min_settle_seconds=0.2, poll_interval=0.02,
                                            max_wait_seconds=5)
        finally:
            writer.join()
        # Whatever size stability was finally observed, it must be the size
        # after the writer finished, not a snapshot taken mid-transfer.
        self.assertEqual(result.st_size, os.path.getsize(path))

    def test_a_file_still_changing_after_max_wait_is_reported_clearly(self):
        path = self.path()
        with open(path, "wb") as handle:
            handle.write(b"x")
        stop = threading.Event()

        def keep_writing():
            while not stop.is_set():
                with open(path, "ab") as handle:
                    handle.write(b"y")
                time.sleep(0.02)

        writer = threading.Thread(target=keep_writing)
        writer.start()
        try:
            with self.assertRaises(UserError) as caught:
                discovery._stable_stat(path, min_settle_seconds=0.5, poll_interval=0.02,
                                       max_wait_seconds=0.2)
            self.assertIn("still being written", caught.exception.what_happened)
        finally:
            stop.set()
            writer.join()

    def test_an_empty_file_is_refused_immediately_not_after_waiting(self):
        path = self.path()
        open(path, "wb").close()
        started = time.monotonic()
        with self.assertRaises(UserError) as caught:
            discovery._stable_stat(path, min_settle_seconds=5, max_wait_seconds=5)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIn("empty", caught.exception.what_happened.lower())

    def test_a_missing_file_reports_clearly(self):
        with self.assertRaises(UserError) as caught:
            discovery._stable_stat(self.path("nope.xlsx"), min_settle_seconds=0.05)
        self.assertIn("copied", caught.exception.next_action.lower())

    def test_the_default_settle_window_is_overridable_by_environment(self):
        previous = os.environ.get("UEA_FILE_SETTLE_SECONDS")
        try:
            os.environ["UEA_FILE_SETTLE_SECONDS"] = "0.05"
            self.assertEqual(discovery._default_settle_seconds(), 0.05)
            os.environ["UEA_FILE_SETTLE_SECONDS"] = "not-a-number"
            self.assertEqual(discovery._default_settle_seconds(), 1.0)
        finally:
            if previous is None:
                os.environ.pop("UEA_FILE_SETTLE_SECONDS", None)
            else:
                os.environ["UEA_FILE_SETTLE_SECONDS"] = previous


if __name__ == "__main__":
    unittest.main()
