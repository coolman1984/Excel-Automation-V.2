"""Recurring runs without anyone pressing a button.

A finished report is usually the same files arriving again every day, week or
month. Two ways to do that, both without a service, an administrator or a
scheduler the user has to understand:

* a **watched folder** - the application notices a new or changed file and
  processes it by itself, while it is open;
* **run once** - ``launch.py --run-once`` processes and exits, so Windows Task
  Scheduler (or any other scheduler) can call it as a standard user.

A file is only processed when its content actually changed: the fingerprint of
every file already processed is remembered, so the same file arriving twice
costs nothing and never duplicates a record.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import threading
import time

from engine.excel.discovery import hash_file
from engine.logging_setup import logger

DEFAULT_INTERVAL_MINUTES = 10


def settings(config) -> dict:
    raw = config.raw.get("automation") or {}
    return {
        "watch_folder": raw.get("watch_folder", ""),
        "process_on_start": bool(raw.get("process_on_start", False)),
        "check_every_minutes": float(raw.get("check_every_minutes", DEFAULT_INTERVAL_MINUTES)),
        "enabled": bool(raw.get("watch_folder") or raw.get("process_on_start")),
    }


def matching_patterns(config) -> list[str]:
    patterns: list[str] = []
    for source in config.sources:
        patterns.extend(source.match)
    return patterns


def _interesting(name: str, patterns: list[str]) -> bool:
    if name.startswith("~$") or name.startswith("."):
        return False
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in patterns)


def collect_new(folder: str, patterns: list[str], seen: dict[str, str]) -> list[str]:
    """Return the files whose content is new or changed since the last look."""

    if not folder or not os.path.isdir(folder):
        return []
    fresh: list[str] = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or not _interesting(name, patterns):
            continue
        try:
            fingerprint = hash_file(path)
        except OSError:
            continue                      # still being written; try again next time
        if seen.get(name) == fingerprint:
            continue
        seen[name] = fingerprint
        fresh.append(path)
    return fresh


class Watcher:
    """Checks the watched folder on a timer and asks the application to run."""

    def __init__(self, config, workspace, on_new_files):
        self.config = config
        self.workspace = workspace
        self.on_new_files = on_new_files
        self.settings = settings(config)
        self.patterns = matching_patterns(config)
        self.seen: dict[str, str] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings["watch_folder"])

    def check_once(self) -> int:
        """Copy any new file into the inbox and start a run. Returns the count."""

        fresh = collect_new(self.settings["watch_folder"], self.patterns, self.seen)
        if not fresh:
            return 0
        for path in fresh:
            shutil.copy2(path, os.path.join(self.workspace.inbox, os.path.basename(path)))
        logger().info("watched folder: %d new file(s) -> processing", len(fresh))
        self.on_new_files(fresh)
        return len(fresh)

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        interval = max(0.5, self.settings["check_every_minutes"]) * 60

        def loop() -> None:
            while not self._stop.wait(5):
                try:
                    self.check_once()
                except Exception:               # never let the watcher kill the app
                    logger().exception("watched folder check failed")
                if self._stop.wait(interval):
                    return

        self._thread = threading.Thread(target=loop, name="watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
