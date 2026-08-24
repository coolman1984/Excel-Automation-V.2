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


def _fsync_dir(path: str) -> None:
    """Make the directory entries themselves durable. A no-op on Windows."""

    try:
        handle = os.open(path, getattr(os, "O_DIRECTORY", os.O_RDONLY))
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def publish(workspace, run_id: str, documents: dict[str, str], keep: int = 10) -> str:
    """Publish a run's result files as one unit.

    Each file is individually atomic, but a *set* of atomic writes is not: a crash
    between them used to leave the JSON from this run beside the HTML from the last
    one. So the files are written into their own run folder first and a single
    pointer is then replaced in one step. That replace is the moment the run becomes
    published; before it, nothing has changed, and there is no window in which a
    reader can see two files from different runs.

    ``data/dashboard.json`` and ``data/dashboard.html`` are kept up to date
    afterwards for anything that reads those paths directly. They are copies - the
    pointer is the authority.
    """

    target = os.path.join(workspace.published, run_id)
    os.makedirs(target, exist_ok=True)
    for name, content in documents.items():
        atomic_write(os.path.join(target, name), content)
    _fsync_dir(target)

    atomic_write(workspace.published_pointer, run_id)   # the commit point
    mirror(workspace)
    prune_published(workspace, keep)
    return target


def current_run(workspace) -> str | None:
    """The run the pointer names, or ``None`` when nothing is published yet."""

    try:
        with open(workspace.published_pointer, "r", encoding="utf-8") as handle:
            run_id = handle.read().strip()
    except OSError:
        return None
    if not run_id or not os.path.isdir(os.path.join(workspace.published, run_id)):
        return None
    return run_id


def published_file(workspace, name: str) -> str:
    """Resolve a published file, preferring the pointer over the legacy copy."""

    run_id = current_run(workspace)
    if run_id:
        candidate = os.path.join(workspace.published, run_id, name)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(workspace.data, name)


def mirror(workspace) -> list[str]:
    """Refresh the legacy ``data/`` copies from whatever the pointer names.

    Also the repair path: a crash during a previous mirror can leave those copies
    from different runs, and calling this puts them back in step.
    """

    run_id = current_run(workspace)
    if not run_id:
        return []
    source_dir = os.path.join(workspace.published, run_id)
    written = []
    for name in sorted(os.listdir(source_dir)):
        source = os.path.join(source_dir, name)
        if not os.path.isfile(source):
            continue
        with open(source, "r", encoding="utf-8") as handle:
            content = handle.read()
        destination = os.path.join(workspace.data, name)
        try:
            with open(destination, "r", encoding="utf-8") as handle:
                if handle.read() == content:
                    continue
        except OSError:
            pass
        atomic_write(destination, content)
        written.append(destination)
    return written


def prune_published(workspace, keep: int) -> list[str]:
    """Drop old published runs, never the live one."""

    if keep <= 0 or not os.path.isdir(workspace.published):
        return []
    live = current_run(workspace)
    entries = []
    for name in os.listdir(workspace.published):
        path = os.path.join(workspace.published, name)
        if os.path.isdir(path) and name != live:
            entries.append(path)
    entries.sort(key=os.path.getmtime, reverse=True)
    removed = []
    for path in entries[max(0, keep - 1):]:
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path)
    return removed
