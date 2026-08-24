"""The cross-process run lock.

Without this, the interactive web application and a scheduled
``launch.py --run-once`` invocation are two separate operating-system
processes with no shared memory: an operator pressing Process at the exact
moment a scheduled run fires could put two processes writing to the same
warehouse file at once. A ``threading.Lock`` or the web application's own busy
flag cannot see across process boundaries; only a file on disk can.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from engine.runlock import LockHeld, RunLock, _pid_alive
from tests.helpers import remove_all, temp_dir


class RunLockTest(unittest.TestCase):
    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def path(self):
        return os.path.join(temp_dir(self.cleanup), "run.lock")

    def test_acquire_creates_the_lock_file(self):
        lock = RunLock(self.path())
        lock.acquire()
        self.assertTrue(os.path.isfile(lock.path))
        lock.release()

    def test_release_removes_the_lock_file(self):
        lock = RunLock(self.path())
        lock.acquire()
        lock.release()
        self.assertFalse(os.path.exists(lock.path))

    def test_a_second_acquire_by_a_live_holder_is_refused(self):
        path = self.path()
        first = RunLock(path)
        first.acquire()
        second = RunLock(path)
        with self.assertRaises(LockHeld) as caught:
            second.acquire()
        self.assertEqual(caught.exception.pid, os.getpid())
        first.release()

    def test_after_release_a_new_acquire_succeeds(self):
        path = self.path()
        first = RunLock(path)
        first.acquire()
        first.release()
        second = RunLock(path)
        second.acquire()   # must not raise
        second.release()

    def test_context_manager_releases_on_a_clean_exit(self):
        path = self.path()
        with RunLock(path):
            self.assertTrue(os.path.isfile(path))
        self.assertFalse(os.path.exists(path))

    def test_context_manager_releases_even_when_the_body_raises(self):
        path = self.path()
        with self.assertRaises(ValueError):
            with RunLock(path):
                raise ValueError("boom")
        self.assertFalse(os.path.exists(path))

    def test_release_without_a_successful_acquire_is_a_safe_no_op(self):
        lock = RunLock(self.path())
        lock.release()   # never acquired; must not raise

    def test_double_release_is_a_safe_no_op(self):
        lock = RunLock(self.path())
        lock.acquire()
        lock.release()
        lock.release()   # must not raise a second time


class StaleLockTest(unittest.TestCase):
    """The real reason this cannot use a simple 'file exists' check forever:
    a crash must never leave every future run permanently blocked."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def path(self):
        return os.path.join(temp_dir(self.cleanup), "run.lock")

    def dead_pid(self) -> int:
        """A PID guaranteed not to be running: start a subprocess, capture
        its PID, wait for it to exit, then hand back a PID that recently
        existed but is now free - a closer proxy for 'the process that made
        this lock crashed' than a made-up huge number."""

        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        return process.pid

    def test_a_lock_from_a_dead_process_is_taken_over_automatically(self):
        path = self.path()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"{self.dead_pid()}\n0\n")

        lock = RunLock(path)
        lock.acquire()   # must not raise LockHeld; the recorded PID is gone
        self.assertIn(str(os.getpid()), open(path).read())
        lock.release()

    def test_a_lock_file_with_unreadable_content_is_also_treated_as_stale(self):
        path = self.path()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("not a pid at all")

        lock = RunLock(path)
        lock.acquire()
        lock.release()

    def test_pid_alive_is_true_for_this_very_process(self):
        self.assertTrue(_pid_alive(os.getpid()))

    def test_pid_alive_is_false_for_a_pid_that_just_exited(self):
        self.assertFalse(_pid_alive(self.dead_pid()))


if __name__ == "__main__":
    unittest.main()
