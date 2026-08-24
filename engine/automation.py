"""Recurring runs without anyone pressing a button.

A finished report is usually the same files arriving again every day, week or
month. Two ways to do that, both without a service, an administrator or a
scheduler the user has to understand:

* a **watched folder** - the application notices a new or changed file and
  processes it by itself, while it is open;
* **run once** - ``launch.py --run-once`` processes and exits, so Windows Task
  Scheduler (or any other scheduler) can call it as a standard user.

A file is only handed off to a run once: its fingerprint is remembered so it is
not copied and queued again on the next check. That memory used to be recorded
before the hand-off was known to have succeeded, and lived only in this
process's own memory - so a file the application happened to be busy when it
arrived was silently never tried again, and a restart forgot every fingerprint
at once. Both are fixed below: a file is only remembered once ``on_new_files``
reports it actually started, and what is remembered is written to disk.

The processed-file ledger (:mod:`engine.data.ledger`) is the correctness
backstop underneath all of this - it is what actually stops a file's content
being merged twice, keyed on the file's bytes rather than this process's
memory. What this module gets right or wrong changes efficiency and whether a
file is *tried*, not whether reprocessed content could corrupt trusted data.
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import threading
import time

from engine.data import archive
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


def _load_seen(workspace) -> dict[str, str]:
    try:
        with open(workspace.watcher_state, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_seen(workspace, seen: dict[str, str]) -> None:
    try:
        archive.atomic_write(workspace.watcher_state, json.dumps(seen, ensure_ascii=False))
    except OSError:
        logger().warning("could not persist watcher state; a restart may recopy pending files")


def _interesting(name: str, patterns: list[str]) -> bool:
    if name.startswith("~$") or name.startswith("."):
        return False
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in patterns)


def collect_new(folder: str, patterns: list[str], seen: dict[str, str]) -> list[tuple[str, str, str]]:
    """Candidates whose content is new or changed since the last look.

    Returns ``(path, name, fingerprint)`` and does not modify ``seen`` - the
    caller commits a fingerprint only once it knows the file was actually
    handed off, so a file is never forgotten just because it was looked at.
    """

    if not folder or not os.path.isdir(folder):
        return []
    fresh: list[tuple[str, str, str]] = []
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
        fresh.append((path, name, fingerprint))
    return fresh


class Watcher:
    """Checks the watched folder on a timer and asks the application to run."""

    def __init__(self, config, workspace, on_new_files):
        self.config = config
        self.workspace = workspace
        self.on_new_files = on_new_files
        self.settings = settings(config)
        self.patterns = matching_patterns(config)
        self.seen: dict[str, str] = _load_seen(workspace)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings["watch_folder"])

    def check_once(self) -> int:
        """Copy any new file into the inbox and start a run. Returns the count.

        A fingerprint is committed to ``seen`` - and only then persisted - once
        ``on_new_files`` reports the hand-off actually started. A run that was
        already busy, or a callback that raised outright, leaves the file
        exactly as it was: still due, tried again on the next check rather
        than silently skipped forever.
        """

        fresh = collect_new(self.settings["watch_folder"], self.patterns, self.seen)
        if not fresh:
            return 0
        for path, _name, _fingerprint in fresh:
            shutil.copy2(path, os.path.join(self.workspace.inbox, os.path.basename(path)))
        logger().info("watched folder: %d new file(s) -> processing", len(fresh))
        outcome = self.on_new_files([path for path, _name, _fingerprint in fresh])
        if isinstance(outcome, dict) and outcome.get("started") is False:
            logger().info("watched folder: hand-off deferred (%s); will retry next check",
                          outcome.get("reason", "busy"))
            return 0
        for _path, name, fingerprint in fresh:
            self.seen[name] = fingerprint
        _save_seen(self.workspace, self.seen)
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
