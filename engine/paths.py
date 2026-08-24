"""Where everything lives at run time.

The operator never sees these folders: the application owns them. Keeping the
layout in one place means the packaged app and the development checkout behave
identically.
"""

from __future__ import annotations

import dataclasses
import os


@dataclasses.dataclass
class Workspace:
    root: str

    @property
    def inbox(self) -> str:
        return os.path.join(self.root, "inbox")

    @property
    def data(self) -> str:
        return os.path.join(self.root, "data")

    @property
    def database(self) -> str:
        return os.path.join(self.data, "warehouse.db")

    @property
    def dashboard(self) -> str:
        return os.path.join(self.data, "dashboard.json")

    @property
    def dashboard_html(self) -> str:
        return os.path.join(self.data, "dashboard.html")

    @property
    def runs(self) -> str:
        return os.path.join(self.root, "runs")

    @property
    def archive(self) -> str:
        return os.path.join(self.root, "archive")

    @property
    def exports(self) -> str:
        return os.path.join(self.root, "exports")

    @property
    def logs(self) -> str:
        return os.path.join(self.root, "logs")

    @property
    def log_file(self) -> str:
        return os.path.join(self.logs, "application.log")

    def run_dir(self, run_id: str) -> str:
        return os.path.join(self.runs, run_id)

    def staging_dir(self, run_id: str) -> str:
        return os.path.join(self.run_dir(run_id), "input_copies")

    def ensure(self) -> "Workspace":
        for path in (self.inbox, self.data, self.runs, self.archive, self.exports, self.logs):
            os.makedirs(path, exist_ok=True)
        return self


def workspace_for(project_root: str, override: str | None = None) -> Workspace:
    """Data lives next to the project unless the packaged app overrides it."""

    root = override or os.environ.get("APP_DATA_DIR") or os.path.join(project_root, "_work")
    return Workspace(root=os.path.abspath(root)).ensure()
