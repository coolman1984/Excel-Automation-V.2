"""A cross-process lock so two runs can never touch the warehouse at once.

The interactive web application and a scheduled ``launch.py --run-once``
invocation are two separate operating-system processes with no shared memory,
so an in-process guard (a ``threading.Lock``, or the busy flag the web
application already keeps) cannot see each other. Without this, an operator
pressing Process at the exact moment a scheduled run fires could have two
processes writing to the same DuckDB or SQLite file at once - at best a run
fails outright, at worst it corrupts the local warehouse.

The lock is a single file in the workspace, created with the OS's atomic
exclusive-create so two processes racing to acquire it can never both
succeed. A crash never leaves it stuck: the file holds the PID that created
it, and a holder whose PID is no longer running is treated as stale and taken
over automatically - no manual cleanup, no administrator, nothing the final
user ever sees or has to know exists.
"""

from __future__ import annotations

import os
import time


class LockHeld(Exception):
    """Another live process already holds this lock."""

    def __init__(self, pid: int | None):
        self.pid = pid
        super().__init__(f"run lock held by pid {pid}" if pid else "run lock held")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # exists, just owned by someone else - still running
    except OSError:
        return False
    return True


class RunLock:
    """One lock file per workspace. Use as a context manager or call
    acquire()/release() directly."""

    def __init__(self, path: str):
        self.path = path
        self._held = False

    def acquire(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        try:
            handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            holder = self._read_holder()
            if holder is not None and _pid_alive(holder):
                raise LockHeld(holder)
            self._take_over_stale_lock()
            self.acquire()
            return
        try:
            os.write(handle, f"{os.getpid()}\n{time.time()}\n".encode("utf-8"))
        finally:
            os.close(handle)
        self._held = True

    def _read_holder(self) -> int | None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                return int(handle.readline().strip())
        except (OSError, ValueError):
            return None

    def _take_over_stale_lock(self) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass   # another process may have cleaned it up first; acquire() retries either way

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            os.remove(self.path)
        except OSError:
            pass

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
