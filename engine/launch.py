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

from engine import alerts, config as config_module  # noqa: E402
from engine import paths, pipeline  # noqa: E402
from engine.errors import UserError  # noqa: E402
from engine.logging_setup import configure, logger  # noqa: E402
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


def _package_root() -> str | None:
    """The folder holding START.bat/SCHEDULE.bat - where the failure alert
    file belongs, so it sits where a person will actually see it. Only
    meaningful for an extracted package (HERE is .../Application/app);
    a development checkout or an explicit --project has no such folder,
    so alerts.write()/clear() are simply skipped there."""

    if os.path.isfile(os.path.join(HERE, "project", "project.json")):
        return os.path.dirname(PARENT)
    return None


def _safe_print(*values: object) -> None:
    """print(), but never crash when there is no console to print to -
    pythonw.exe sets sys.stdout to None rather than a stream."""

    if sys.stdout is not None:
        print(*values, flush=True)


def _fatal_startup_error(exc: BaseException) -> None:
    """The interactive app has no console under pythonw.exe: an unhandled
    exception before the server starts would otherwise be completely
    invisible - the browser never opens and nothing tells the person who
    double-clicked START.bat why. Always logged; shown as a native message
    box when there is no console to print to, since that is the only way
    to reach the user at all in that case.
    """

    if isinstance(exc, UserError):
        message = f"{exc.what_happened}\n\n{exc.next_action}\n\nSupport code: {exc.code}"
    elif isinstance(exc, SystemExit):
        message = str(exc.code) if exc.code not in (None, 0) else "The application could not start."
    else:
        message = str(exc) or exc.__class__.__name__

    try:
        logger().error("startup failed: %s", message,
                       exc_info=None if isinstance(exc, SystemExit) else exc)
    except Exception:
        pass

    if sys.stderr is not None:
        try:
            print(f"\n{message}\n", file=sys.stderr, flush=True)
        except Exception:
            pass
        return

    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "The report could not start", 0x10)
        except Exception:
            pass


def _run_once() -> int:
    """For a scheduler: process whatever is waiting, print the outcome, exit.

    A scheduled run is normally started with pythonw.exe, so nobody sees its
    console - often there is not even one. A local alert file is what
    actually reaches the operator the next time they open this folder,
    both for a problem here (a broken configuration) and for whatever
    pipeline.run() itself reports; it is cleared automatically the moment a
    run succeeds again.
    """

    package_root = _package_root()
    try:
        project_dir = resolve_project_dir()
        workspace = paths.workspace_for(project_dir, resolve_data_dir(project_dir))
        configure(workspace.log_file)
        config = config_module.load(project_dir)
    except UserError as exc:
        if package_root:
            alerts.write(package_root, "The scheduled update", exc.what_happened,
                        exc.next_action, exc.code)
        _safe_print(f"{exc.code}: {exc.what_happened}")
        return 1
    except Exception as exc:
        if package_root:
            alerts.write(package_root, "The scheduled update", str(exc) or exc.__class__.__name__,
                        "Open START.bat and try again by hand. If it keeps happening, send the "
                        "support code to your support contact.", "E-RUN-001")
        return 1

    result = pipeline.run(config, workspace)
    _safe_print(f"{result.status}: {result.message}")
    if result.error:
        _safe_print(f"{result.error['support_code']}: {result.error['next_action']}")

    if package_root:
        if result.status in ("PASS", "WARNING"):
            alerts.clear(package_root)
        else:
            error = result.error or {}
            alerts.write(package_root, config.display_title(),
                        error.get("what_happened", result.message),
                        error.get("next_action",
                                  "Open START.bat and press Process to see full details."),
                        error.get("support_code", ""))
    return 0 if result.status in ("PASS", "WARNING") else 1


def main() -> int:
    prepare_console()

    if "--run-once" in sys.argv:
        return _run_once()

    try:
        project_dir = resolve_project_dir()
        workspace = paths.workspace_for(project_dir, resolve_data_dir(project_dir))
        configure(workspace.log_file)
        config = config_module.load(project_dir)
        port = int(_argument("port") or 0)
        server, application = server_module.make_server(config, workspace, port=port)
    except KeyboardInterrupt:
        return 1
    except BaseException as exc:
        _fatal_startup_error(exc)
        return 1

    url = server_module.url_for(server, application)

    title = config.display_title()
    # flush: on Windows this output is block-buffered when it goes through a pipe,
    # so anything reading the address would otherwise wait for the buffer, not the app.
    _safe_print(f"{title} is starting...")
    _safe_print(f"If your browser does not open, use this address: {url}")

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
