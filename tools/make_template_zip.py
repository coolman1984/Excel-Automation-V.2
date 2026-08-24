"""Build the template ZIP that a chat session receives.

This is the *other* package: the one for the adaptation agent, not for the
business user. It carries the engine, the tests, the example project, the agent
instructions and the documentation - and nothing that a run produced.

    python tools/make_template_zip.py [--output release]
"""

from __future__ import annotations

import argparse
import os
import sys
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

NAME = "Project-Template"
EXCLUDE_DIRS = {".git", ".github", "__pycache__", "_work", "release", "build", "dist",
                ".pytest_cache", ".venv", "venv", ".idea", ".vscode"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".log", ".db", ".db-wal", ".db-shm", ".zip")
# Files an agent must find immediately, in the order it should read them.
REQUIRED = ["PROJECT_SKILL.md", ".ai/CONTEXT_PACK.md", ".ai/PROJECT_MAP.md",
            ".ai/BUSINESS_QUESTIONS.md", "PROJECT_TOOL.py",
            "runtime_inputs/windows_runtime_manifest.json", "tools/prepare_windows_runtime.py",
            "projects/example_sales/project.json", "projects/_template/project.json"]


def build(output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    zip_path = os.path.join(output_dir, f"{NAME}.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)

    written: set[str] = set()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for directory, subdirectories, files in os.walk(REPO_ROOT):
            subdirectories[:] = sorted(d for d in subdirectories if d not in EXCLUDE_DIRS)
            for name in sorted(files):
                if name.endswith(EXCLUDE_SUFFIXES):
                    continue
                full = os.path.join(directory, name)
                relative = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
                archive.write(full, f"{NAME}/{relative}")
                written.add(relative)

    missing = [name for name in REQUIRED if name not in written]
    if missing:
        raise SystemExit(f"template ZIP is incomplete, missing: {missing}")
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=os.path.join(REPO_ROOT, "release"))
    args = parser.parse_args()
    zip_path = build(args.output)
    size = os.path.getsize(zip_path) / 1024
    print(f"wrote {zip_path} ({size:.0f} KB)")
    print("Give this file to a chat session together with the Excel files and a plain "
          "explanation of the work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
