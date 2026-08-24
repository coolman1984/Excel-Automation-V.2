"""Application entry point.

``START.bat`` runs this file with the private runtime. It chooses a free
loopback port, starts the local application and opens the browser. The user
never sees a port, a command or a choice.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
PARENT = os.path.dirname(HERE)
if os.path.isdir(os.path.join(PARENT, "engine")) and PARENT not in sys.path:
    sys.path.insert(0, PARENT)   # running from the repository checkout

from engine import config as config_module  # noqa: E402
from engine import paths, pipeline  # noqa: E402
from engine.logging_setup import configure  # noqa: E402
from engine.webapp import server as server_module  # noqa: E402


def prepare_console() -> None:
    """Make printing safe on Windows.

    A Windows console is not UTF-8 by default, so a project title in Arabic - or
    even a single typographic character - could otherwise stop the application
    before it started. Under ``pythonw.exe`` there is no console at all and the
    streams are ``None``; printing then does nothing, which is what we want.
    """

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - depends on the console
            pass


def _argument(name: str) -> str | None:
    prefix = f"--{name}="
    for value in sys.argv[1:]:
        if value.startswith(prefix):
            return value[len(prefix):]
    if f"--{name}" in sys.argv[1:]:
        index = sys.argv.index(f"--{name}")
        if index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return None


def resolve_project_dir() -> str:
    explicit = _argument("project") or os.environ.get("APP_PROJECT_DIR")
    if explicit:
        return os.path.abspath(explicit)
    packaged = os.path.join(HERE, "project")
    if os.path.isfile(os.path.join(packaged, "project.json")):
        return packaged
    raise SystemExit("No project found. Start the application from its own folder, or pass "
                     "--project <folder>.")


def resolve_data_dir(project_dir: str) -> str:
    explicit = _argument("data") or os.environ.get("APP_DATA_DIR")
    if explicit:
        return os.path.abspath(explicit)
    packaged_data = os.path.join(PARENT, "Data")
    if os.path.isdir(os.path.join(HERE, "project")):
        return packaged_data
    return os.path.join(project_dir, "_work")


def main() -> int:
    prepare_console()
    project_dir = resolve_project_dir()
    workspace = paths.workspace_for(project_dir, resolve_data_dir(project_dir))
    configure(workspace.log_file)
    config = config_module.load(project_dir)

    if "--run-once" in sys.argv:
        # For a scheduler: process whatever is waiting, print the outcome, exit.
        result = pipeline.run(config, workspace)
        print(f"{result.status}: {result.message}", flush=True)
        if result.error:
            print(f"{result.error['support_code']}: {result.error['next_action']}", flush=True)
        return 0 if result.status in ("PASS", "WARNING") else 1

    port = int(_argument("port") or 0)
    server, application = server_module.make_server(config, workspace, port=port)
    url = server_module.url_for(server, application)

    title = config.display_title()
    # flush: on Windows this output is block-buffered when it goes through a pipe,
    # so anything reading the address would otherwise wait for the buffer, not the app.
    print(f"{title} is starting...", flush=True)
    print(f"If your browser does not open, use this address: {url}", flush=True)

    server_module.start_automation(application)

    if "--no-browser" not in sys.argv:
        threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)),
                         daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
