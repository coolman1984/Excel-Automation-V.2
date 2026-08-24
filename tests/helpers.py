"""Shared test helpers."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

os.environ.setdefault("APP_LOG_QUIET", "1")   # tests keep the console readable
os.environ.setdefault("UEA_DB_BACKEND", "sqlite")  # deterministic source tests; production can require DuckDB
os.environ.setdefault("UEA_FILE_SETTLE_SECONDS", "0.01")  # fixtures are static; production waits longer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

EXAMPLE_PROJECT = os.path.join(REPO_ROOT, "projects", "example_sales")
FIXTURES = os.path.join(EXAMPLE_PROJECT, "fixtures")

from engine import config as config_module, paths  # noqa: E402


def temp_dir(cleanup: list[str]) -> str:
    path = tempfile.mkdtemp(prefix="uea_test_")
    cleanup.append(path)
    return path


def remove_all(paths_to_remove: list[str]) -> None:
    for path in paths_to_remove:
        shutil.rmtree(path, ignore_errors=True)


def example_workspace(cleanup: list[str], with_fixtures: bool = True):
    root = temp_dir(cleanup)
    workspace = paths.workspace_for(root, os.path.join(root, "_work"))
    if with_fixtures:
        for name in sorted(os.listdir(FIXTURES)):
            shutil.copy2(os.path.join(FIXTURES, name), os.path.join(workspace.inbox, name))
    return workspace


def example_config():
    return config_module.load(EXAMPLE_PROJECT)


def project_copy(cleanup: list[str], source: str = EXAMPLE_PROJECT) -> str:
    target = os.path.join(temp_dir(cleanup), "project")
    shutil.copytree(source, target)
    return target


def edit_config(project_dir: str, mutate) -> None:
    path = os.path.join(project_dir, "project.json")
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    mutate(data)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def golden(project_dir: str = EXAMPLE_PROJECT) -> dict:
    with open(os.path.join(project_dir, "tests", "golden.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)
