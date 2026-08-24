"""Recovery archive.

Every published result is copied aside before the next run touches anything,
so a bad run can never leave the business without its last approved numbers.
"""

from __future__ import annotations

import os
import shutil
import time


def snapshot(archive_dir: str, run_id: str, files: list[str], keep: int = 10) -> str:
    target = os.path.join(archive_dir, run_id)
    os.makedirs(target, exist_ok=True)
    for path in files:
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(target, os.path.basename(path)))
    prune(archive_dir, keep)
    return target


def prune(archive_dir: str, keep: int) -> list[str]:
    if keep <= 0 or not os.path.isdir(archive_dir):
        return []
    entries = [os.path.join(archive_dir, name) for name in os.listdir(archive_dir)]
    entries = [path for path in entries if os.path.isdir(path)]
    entries.sort(key=os.path.getmtime, reverse=True)
    removed = []
    for path in entries[keep:]:
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path)
    return removed


def restore(archive_dir: str, run_id: str, destination: str) -> list[str]:
    """Copy an archived snapshot back into place."""

    source = os.path.join(archive_dir, run_id)
    if not os.path.isdir(source):
        raise FileNotFoundError(source)
    os.makedirs(destination, exist_ok=True)
    restored = []
    for name in sorted(os.listdir(source)):
        shutil.copy2(os.path.join(source, name), os.path.join(destination, name))
        restored.append(name)
    return restored


def latest(archive_dir: str) -> str | None:
    if not os.path.isdir(archive_dir):
        return None
    entries = [os.path.join(archive_dir, n) for n in os.listdir(archive_dir)]
    entries = [p for p in entries if os.path.isdir(p)]
    if not entries:
        return None
    return os.path.basename(max(entries, key=os.path.getmtime))


def atomic_write(path: str, content: str) -> None:
    """Write a file so readers never see a half-written result."""

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary = os.path.join(directory, f".{os.path.basename(path)}.{int(time.time()*1000)}.tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
