"""Prepare the private Windows x64 runtime used by final operator packages.

This is a BUILD-TIME tool for the adaptation agent or approved build machine.
The final business user never runs it. It downloads only pinned artifacts from
``runtime_inputs/windows_runtime_manifest.json``, verifies SHA-256, and expands
them into ``runtime_inputs/python-windows``. It never installs anything into the
machine-wide Python environment.

For a closed build network, place the four pinned files in
``runtime_inputs/downloads`` first and run with ``--offline``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "runtime_inputs" / "windows_runtime_manifest.json"
DEFAULT_CACHE = ROOT / "runtime_inputs" / "downloads"
DEFAULT_OUTPUT = ROOT / "runtime_inputs" / "python-windows"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "UltimateExcelAutomation/13"})
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def acquire(item: dict, cache: Path, offline: bool) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / item["filename"]
    expected = item["sha256"].lower()
    if target.exists() and sha256(target) == expected:
        return target
    if target.exists():
        target.unlink()
    if offline:
        raise RuntimeError(f"offline artifact missing or invalid: {target.name}")
    temp = target.with_suffix(target.suffix + ".part")
    if temp.exists():
        temp.unlink()
    _download(item["url"], temp)
    actual = sha256(temp)
    if actual != expected:
        temp.unlink(missing_ok=True)
        raise RuntimeError(
            f"SHA-256 mismatch for {item['filename']}: expected {expected}, got {actual}")
    temp.replace(target)
    return target


def extract(archive: Path, output: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            parts = [part for part in name.split("/") if part]
            if not parts or any(part == ".." for part in parts):
                raise RuntimeError(f"unsafe archive entry: {info.filename}")
            destination = output.joinpath(*parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)


def prepare(output: Path, cache: Path, offline: bool = False) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifacts = [(item, acquire(item, cache, offline)) for item in manifest["artifacts"]]

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="uea_runtime_", dir=str(output.parent)))
    try:
        for item, archive in artifacts:
            extract(archive, staging)

        # The embeddable runtime keeps imports intentionally isolated. It already
        # includes '.' in python311._pth; fail closed if a future Python layout does not.
        pth_files = list(staging.glob("python*._pth"))
        if not pth_files:
            raise RuntimeError("embeddable Python _pth file is missing")
        pth = pth_files[0]
        lines = [line.strip() for line in pth.read_text(encoding="utf-8").splitlines()]
        if "." not in lines:
            lines.insert(1, ".")
            pth.write_text("\n".join(lines) + "\n", encoding="utf-8")

        evidence = {
            "runtime_id": manifest["runtime_id"],
            "architecture": manifest["architecture"],
            "python": manifest["python"],
            "artifacts": [
                {"id": item["id"], "version": item.get("version", manifest["python"]),
                 "filename": item["filename"], "sha256": item["sha256"]}
                for item, _ in artifacts
            ],
            "target_requirements": manifest["target_requirements"],
        }
        (staging / "UEA_RUNTIME_MANIFEST.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        if output.exists():
            shutil.rmtree(output)
        staging.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--offline", action="store_true",
                        help="do not access the internet; require all pinned archives in --cache")
    args = parser.parse_args()
    evidence = prepare(Path(args.output).resolve(), Path(args.cache).resolve(), args.offline)
    print(f"prepared: {Path(args.output).resolve()}")
    print("included: " + ", ".join(item["id"] for item in evidence["artifacts"]))
    print("next: run PROJECT_TOOL.py deliver ... --runtime runtime_inputs/python-windows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
