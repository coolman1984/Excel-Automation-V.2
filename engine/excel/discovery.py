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


def _stable_stat(path: str, checks: int = 2, delay: float = 0.08):
    """Require unchanged size/mtime across consecutive probes.

    The short delay keeps manual runs responsive while catching the common
    watched-folder race where a large file is still being copied.  The source
    is checked again after copying, so this is defense in depth rather than a
    single timing assumption.
    """
    previous = None
    for _ in range(max(2, checks)):
        try:
            current = os.stat(path)
        except OSError as exc:
            raise user_error("E-IN-004", next_action="Make sure the file is fully copied and accessible, then process again.",
                             detail=f"{path}: {exc}") from exc
        signature = (current.st_size, current.st_mtime_ns)
        if current.st_size <= 0:
            raise user_error("E-IN-004", what_happened="An input file is empty.",
                             next_action="Replace the empty file with the completed export and process again.",
                             detail=path)
        if previous is not None and signature == previous:
            return current
        previous = signature
        time.sleep(delay)
    return os.stat(path)


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
