"""Discover, fingerprint and safely copy approved input files.

Sources are immutable.  Intake rejects half-copied/empty files, waits briefly
for filesystem metadata to stabilise, copies to a run-owned workspace, and
verifies the copied bytes match the source hash before extraction starts.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import hashlib
import os
import shutil
import time

from engine.errors import user_error


@dataclasses.dataclass
class DiscoveredFile:
    source_id: str
    original_path: str
    workspace_path: str
    file_name: str
    size_bytes: int
    modified_at: float
    sha256: str


def hash_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_matching(inbox: str, patterns: list[str]) -> list[str]:
    if not os.path.isdir(inbox):
        return []
    found: list[str] = []
    for name in sorted(os.listdir(inbox)):
        if name.startswith("~$") or name.startswith("."):
            continue
        full = os.path.join(inbox, name)
        if not os.path.isfile(full):
            continue
        if any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in patterns):
            found.append(full)
    return found


def _default_settle_seconds() -> float:
    # Production wants a real window (a slow network copy can pause between write
    # batches for well over a second); the test suite processes hundreds of
    # already-complete static fixtures and would otherwise pay this on every one.
    # Same override pattern as UEA_DB_BACKEND.
    try:
        return float(os.environ.get("UEA_FILE_SETTLE_SECONDS", "1.0"))
    except ValueError:
        return 1.0


def _stable_stat(path: str, min_settle_seconds: float | None = None, poll_interval: float = 0.1,
                 max_wait_seconds: float = 30.0):
    """Require unchanged size/mtime for a real elapsed window, not just two probes.

    A slow network copy can easily pause between write batches for longer than a
    couple of probes 80ms apart, which used to be enough to look "stable" while
    genuinely mid-transfer. This instead requires the signature to hold for
    ``min_settle_seconds`` of continuous polling; any change resets the clock. A
    file still growing after ``max_wait_seconds`` is reported clearly rather than
    accepted on a technicality or hung on forever.

    This still cannot detect a transfer that aborted and left a permanently
    truncated file with no further writes - no stability window can, since a
    stopped-changing truncated file and a stopped-changing complete file look
    identical from the outside. That case surfaces instead when the file fails to
    open as a valid workbook, downstream.
    """
    min_settle_seconds = _default_settle_seconds() if min_settle_seconds is None else min_settle_seconds
    poll_interval = min(poll_interval, max(0.001, min_settle_seconds / 4)) if min_settle_seconds else poll_interval
    start = time.monotonic()
    previous = None
    settled_since: float | None = None
    while True:
        try:
            current = os.stat(path)
        except OSError as exc:
            raise user_error("E-IN-004", next_action="Make sure the file is fully copied and accessible, then process again.",
                             detail=f"{path}: {exc}") from exc
        if current.st_size <= 0:
            raise user_error("E-IN-004", what_happened="An input file is empty.",
                             next_action="Replace the empty file with the completed export and process again.",
                             detail=path)
        signature = (current.st_size, current.st_mtime_ns)
        now = time.monotonic()
        if signature != previous:
            previous = signature
            settled_since = now
        elif now - settled_since >= min_settle_seconds:
            return current
        if now - start >= max_wait_seconds:
            raise user_error(
                "E-IN-004",
                what_happened="An input file is still being written and did not finish in time.",
                next_action="Wait for the file copy or export to finish, then process again.",
                detail=f"{path}: still changing after {max_wait_seconds:.0f}s")
        time.sleep(poll_interval)


def collect(source_id: str, inbox: str, patterns: list[str], workspace: str,
            required: bool = True) -> list[DiscoveredFile]:
    matches = find_matching(inbox, patterns)
    if not matches and required:
        raise user_error("E-IN-001", next_action=f"Add the file for '{source_id}' on the page, then press Process again.",
                         detail=f"inbox={inbox} patterns={patterns}")
    source_workspace = os.path.join(workspace, source_id)
    os.makedirs(source_workspace, exist_ok=True)
    collected: list[DiscoveredFile] = []
    for path in matches:
        before = _stable_stat(path)
        source_hash = hash_file(path)
        target = os.path.join(source_workspace, os.path.basename(path))
        shutil.copy2(path, target)
        after = os.stat(path)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            try: os.remove(target)
            except OSError: pass
            raise user_error("E-IN-004", next_action="Wait for the file copy/export to finish, then press Process again.",
                             detail=f"{path} changed while being copied.")
        copied_hash = hash_file(target)
        if copied_hash != source_hash:
            try: os.remove(target)
            except OSError: pass
            raise user_error("E-IN-004", what_happened="The safe input copy did not match the source file.",
                             next_action="Process again. If it repeats, copy the source file to a local folder first.",
                             detail=f"{path}: source={source_hash} copy={copied_hash}")
        collected.append(DiscoveredFile(source_id=source_id, original_path=path,
            workspace_path=target, file_name=os.path.basename(path), size_bytes=after.st_size,
            modified_at=after.st_mtime, sha256=source_hash))
    return collected
