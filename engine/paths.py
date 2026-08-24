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
    def published(self) -> str:
        """One folder per published run. The pointer below decides which is live."""

        return os.path.join(self.data, "published")

    @property
    def published_pointer(self) -> str:
        """Written last, in one atomic step: this is what makes a run published."""

        return os.path.join(self.published, "CURRENT")

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
    def watcher_state(self) -> str:
        """Where the watcher remembers which files it has already handed off,
        so a restart does not forget and re-copy everything in the watched
        folder. The processed-file ledger, not this file, is what actually
        stops reprocessed content from being merged twice - this only affects
        whether a file is retried, not whether it could be double-counted."""

        return os.path.join(self.data, "watcher_seen.json")

    def processed_archive(self, folder_name: str = "Processed") -> str:
        """Where a successfully processed inbox file goes, organised by month,
        so the inbox holds only what has not been processed yet while every
        source file the operator dropped in stays easy to find."""

        return os.path.join(self.root, folder_name)

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
        for path in (self.inbox, self.data, self.published, self.runs, self.archive,
                     self.exports, self.logs):
            os.makedirs(path, exist_ok=True)
        return self


def workspace_for(project_root: str, override: str | None = None) -> Workspace:
    """Data lives next to the project unless the packaged app overrides it."""

    root = override or os.environ.get("APP_DATA_DIR") or os.path.join(project_root, "_work")
    return Workspace(root=os.path.abspath(root)).ensure()
