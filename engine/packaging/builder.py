"""Build the final operator package.

Stage A prepares the private application folder. Stage B wraps it in the only
shape the final user ever sees:

    ProjectName/
        START.bat
        QUICK_START.html
        Application/
"""

from __future__ import annotations

import dataclasses
import os
import re
import shutil
import zipfile

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_ENTRIES = ("START.bat", "SCHEDULE.bat", "QUICK_START.html", "Application")
EXCLUDE_DIRS = {"__pycache__", ".git", ".github", "node_modules", ".pytest_cache", "_work",
                "fixtures", "tests"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".log", ".db", ".db-wal", ".db-shm")


@dataclasses.dataclass
class BuildResult:
    zip_path: str
    app_dir: str
    display_name: str
    files: int
    bytes: int
    runtime_included: bool


def _copy_tree(source: str, target: str) -> int:
    copied = 0
    for directory, subdirectories, files in os.walk(source):
        subdirectories[:] = [d for d in subdirectories if d not in EXCLUDE_DIRS]
        relative = os.path.relpath(directory, source)
        destination = target if relative == "." else os.path.join(target, relative)
        os.makedirs(destination, exist_ok=True)
        for name in files:
            if name.endswith(EXCLUDE_SUFFIXES):
                continue
            shutil.copy2(os.path.join(directory, name), os.path.join(destination, name))
            copied += 1
    return copied


def stage_application(project_dir: str, app_dir: str, runtime_dir: str | None = None,
                      include_fixtures: bool = False) -> str:
    """Stage A - assemble the private one-folder application.

    ``app_dir/``
        ``app/``      engine source, project configuration and web assets
        ``runtime/``  the private Python runtime (Windows embeddable build)
        ``Data/``     created on first start; holds the database and results
    """

    if os.path.isdir(app_dir):
        shutil.rmtree(app_dir)
    code_dir = os.path.join(app_dir, "app")
    os.makedirs(code_dir, exist_ok=True)

    _copy_tree(ENGINE_DIR, os.path.join(code_dir, "engine"))

    project_target = os.path.join(code_dir, "project")
    os.makedirs(project_target, exist_ok=True)
    for directory, subdirectories, files in os.walk(project_dir):
        subdirectories[:] = [d for d in subdirectories
                             if d not in EXCLUDE_DIRS or (include_fixtures and d == "fixtures")]
        relative = os.path.relpath(directory, project_dir)
        destination = project_target if relative == "." else os.path.join(project_target, relative)
        os.makedirs(destination, exist_ok=True)
        for name in files:
            if name.endswith(EXCLUDE_SUFFIXES):
                continue
            shutil.copy2(os.path.join(directory, name), os.path.join(destination, name))

    shutil.copy2(os.path.join(ENGINE_DIR, "launch.py"), os.path.join(code_dir, "launch.py"))

    if runtime_dir:
        runtime_target = os.path.join(app_dir, "runtime")
        _copy_tree(runtime_dir, runtime_target)
    os.makedirs(os.path.join(app_dir, "Data"), exist_ok=True)
    return app_dir


def _render_template(name: str, display_name: str) -> str:
    with open(os.path.join(TEMPLATE_DIR, name), "r", encoding="utf-8") as handle:
        return handle.read().replace("__DISPLAY_NAME__", display_name)


def safe_project_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.\- ]", "", name).strip()
    if not cleaned:
        raise ValueError("project name must contain letters or digits")
    return cleaned


def build(project_name: str, app_dir: str, output_dir: str, display_name: str | None = None
          ) -> BuildResult:
    """Stage B - write ``output_dir/ProjectName.zip``."""

    project_name = safe_project_name(project_name)
    display_name = display_name or project_name
    if not os.path.isdir(app_dir):
        raise FileNotFoundError(app_dir)
    os.makedirs(output_dir, exist_ok=True)
    zip_path = os.path.join(output_dir, f"{project_name}.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)

    files = 0
    total_bytes = 0
    runtime_included = os.path.isdir(os.path.join(app_dir, "runtime"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(f"{project_name}/START.bat",
                         _render_template("START.bat", display_name).replace("\n", "\r\n"))
        archive.writestr(f"{project_name}/SCHEDULE.bat",
                         _render_template("SCHEDULE.bat", display_name).replace("\n", "\r\n"))
        archive.writestr(f"{project_name}/QUICK_START.html",
                         _render_template("QUICK_START.html", display_name))
        files += 3
        for directory, subdirectories, names in os.walk(app_dir):
            subdirectories[:] = [d for d in subdirectories if d not in EXCLUDE_DIRS]
            for name in sorted(names):
                if name.endswith(EXCLUDE_SUFFIXES):
                    continue
                full = os.path.join(directory, name)
                relative = os.path.relpath(full, app_dir).replace(os.sep, "/")
                archive.write(full, f"{project_name}/Application/{relative}")
                files += 1
                total_bytes += os.path.getsize(full)
    return BuildResult(zip_path=zip_path, app_dir=app_dir, display_name=display_name,
                       files=files, bytes=total_bytes, runtime_included=runtime_included)
