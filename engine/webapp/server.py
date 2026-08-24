"""The local application boundary.

A loopback-only HTTP server on 127.0.0.1. It is not a website: it is how the
one-page application talks to the engine on the same machine. The launcher
picks the port, so the user never chooses one, and a per-session key stops any
other local program from driving the application.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import mimetypes
import os
import re
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine import __version__, automation, pipeline
from engine.data import archive
from engine.report import standalone
from engine.errors import UserError
from engine.logging_setup import logger

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_UPLOAD_BYTES = 256 * 1024 * 1024   # legacy JSON upload only
MAX_FILE_BYTES = 1024 * 1024 * 1024    # streaming upload: 1 GiB per file
SAFE_NAME = re.compile(r"^[\w \-.()\[\]]+\.(xlsx|xlsm|xlsb|xls|csv|txt)$", re.IGNORECASE)


class RunState:
    """Progress of the current or last run, shared with the browser."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.busy = False
        self.percent = 0
        self.step = "idle"
        self.message = ""
        self.result: dict | None = None

    def start(self) -> bool:
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            self.percent = 0
            self.step = "starting"
            self.message = "Starting"
            self.result = None
            return True

    def update(self, step: str, percent: int, message: str) -> None:
        with self.lock:
            self.step, self.percent, self.message = step, percent, message

    def finish(self, result: dict) -> None:
        with self.lock:
            self.busy = False
            self.percent = 100
            self.step = "done"
            self.result = result

    def snapshot(self) -> dict:
        with self.lock:
            return {"busy": self.busy, "percent": self.percent, "step": self.step,
                    "message": self.message, "result": self.result}


class Application:
    def __init__(self, config, workspace, session_key: str):
        self.config = config
        self.workspace = workspace
        self.session_key = session_key
        self.state = RunState()
        self.automation = automation.settings(config)
        self.watcher = automation.Watcher(config, workspace, lambda files: self.process())

    # -- actions -----------------------------------------------------------
    def inbox_files(self) -> list[dict]:
        files = []
        if os.path.isdir(self.workspace.inbox):
            for name in sorted(os.listdir(self.workspace.inbox)):
                path = os.path.join(self.workspace.inbox, name)
                if os.path.isfile(path):
                    files.append({"name": name, "size_bytes": os.path.getsize(path)})
        return files

    def expected_files(self) -> list[dict]:
        return [{"source_id": source.id, "title": source.title, "patterns": source.match,
                 "required": source.required, "grain": source.grain}
                for source in self.config.sources]

    def add_file(self, name: str, content: bytes) -> dict:
        if not SAFE_NAME.match(name):
            raise UserError(code="E-IN-002",
                            what_happened=f"'{name}' is not a file type this report accepts.",
                            next_action="Add an Excel (.xlsx) or CSV file.")
        target = os.path.join(self.workspace.inbox, os.path.basename(name))
        with open(target, "wb") as handle:
            handle.write(content)
        return {"name": os.path.basename(name), "size_bytes": len(content)}

    def add_file_stream(self, name: str, stream, length: int) -> dict:
        """Write one browser upload incrementally and publish it atomically."""
        if not SAFE_NAME.match(name):
            raise UserError(code="E-IN-002",
                            what_happened=f"'{name}' is not a file type this report accepts.",
                            next_action="Add an Excel or CSV file.")
        if length <= 0 or length > MAX_FILE_BYTES:
            raise UserError(code="E-IN-002",
                            what_happened="The selected file is empty or larger than this local app accepts.",
                            next_action="Use a completed file up to 1 GB, or split the source into approved periods.",
                            detail=f"bytes={length}")
        free = __import__("shutil").disk_usage(self.workspace.inbox).free
        if free < length + 128 * 1024 * 1024:
            raise UserError(code="E-IN-002", what_happened="There is not enough free disk space to add this file safely.",
                            next_action="Free some space on this drive and add the file again.",
                            detail=f"free={free} file={length}")
        final_name = os.path.basename(name)
        target = os.path.join(self.workspace.inbox, final_name)
        temporary = target + ".uploading." + secrets.token_hex(6)
        remaining = length
        try:
            with open(temporary, "wb") as handle:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ConnectionError("upload ended before Content-Length bytes arrived")
                    handle.write(chunk)
                    remaining -= len(chunk)
                handle.flush()
                try: os.fsync(handle.fileno())
                except OSError: pass
            if os.path.getsize(temporary) != length:
                raise IOError("uploaded byte count does not match Content-Length")
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                try: os.remove(temporary)
                except OSError: pass
        return {"name": final_name, "size_bytes": length}

    def remove_file(self, name: str) -> bool:
        target = os.path.join(self.workspace.inbox, os.path.basename(name))
        if os.path.isfile(target):
            os.remove(target)
            return True
        return False

    def dashboard(self) -> dict | None:
        return pipeline.last_dashboard(self.workspace)

    def state_payload(self) -> dict:
        return {
            "engine_version": __version__,
            "project": {
                "name": self.config.project_name,
                "title": self.config.title,
                "language": self.config.language,
                "purpose": self.config.business.get("purpose", ""),
            },
            "expected_files": self.expected_files(),
            "inbox": self.inbox_files(),
            "progress": self.state.snapshot(),
            "automation": {"watching": bool(self.automation["watch_folder"]),
                           "folder": os.path.basename(self.automation["watch_folder"] or ""),
                           "every_minutes": self.automation["check_every_minutes"]},
            "dashboard": self.dashboard(),
        }

    def process(self) -> dict:
        if not self.state.start():
            return {"started": False, "reason": "A run is already in progress."}

        def worker() -> None:
            try:
                result = pipeline.run(self.config, self.workspace, progress=self.state.update)
                self.state.finish(result.to_dict())
            except Exception as exc:  # pragma: no cover - pipeline handles its own errors
                logger().exception("run failed outside the pipeline")
                self.state.finish({"status": "BLOCK", "message": str(exc)})

        threading.Thread(target=worker, name="run", daemon=True).start()
        return {"started": True}

    # -- exports -----------------------------------------------------------
    def export_metric(self, metric_id: str) -> tuple[str, str]:
        document = self.dashboard() or {}
        for table in document.get("tables", []):
            if table["id"] == metric_id:
                return _csv(table["columns"], table["rows"]), f"{metric_id}.csv"
        for chart in document.get("charts", []):
            if chart["id"] == metric_id:
                return (_csv(["label", "value"], [[p["label"], p["value"]] for p in chart["points"]]),
                        f"{metric_id}.csv")
        if metric_id == "attention":
            rows = document.get("attention", {}).get("rows", [])
            return (_csv(["file", "row", "rule", "field", "message"],
                         [[r["file_name"], r["excel_row"], r["rule"], r["field"], r["message"]]
                          for r in rows]), "rows_needing_attention.csv")
        raise KeyError(metric_id)


def _csv(columns, rows) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = f"UltimateExcelAutomation/{__version__}"
    app: Application  # set by make_server

    # -- plumbing ----------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:  # keep the console clean
        logger().debug("http %s", fmt % args)

    def _host_is_local(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost", "[::1]", "::1")

    def _authorised(self, query: dict) -> bool:
        key = (query.get("k", [None])[0] or self.headers.get("X-Session-Key"))
        return secrets.compare_digest(str(key or ""), self.app.session_key)

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                         "script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD_BYTES:
            raise ValueError("payload too large")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # -- routing -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if not self._host_is_local():
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        path = parsed.path

        if path == "/api/health":
            self._json({"ok": True, "version": __version__})
            return
        if path.startswith("/api/") and not self._authorised(query):
            self._json({"error": "This page was opened without its session key. "
                                 "Close the browser tab and start the application again."}, 403)
            return

        if path == "/api/state":
            self._json(self.app.state_payload())
        elif path == "/api/progress":
            self._json(self.app.state.snapshot())
        elif path == "/api/dashboard":
            self._json(self.app.dashboard())
        elif path == "/api/export/dashboard.html":
            document = self.app.dashboard()
            if not document:
                self._json({"error": "There is no result to save yet."}, 404)
                return
            body = standalone.build(document, self.app.config.display_title())
            name = standalone.file_name(self.app.config.project_name, document)
            self._send(200, body.encode("utf-8"), "text/html; charset=utf-8",
                       {"Content-Disposition": f'attachment; filename="{name}"'})
        elif path.startswith("/api/export/"):
            metric_id = path[len("/api/export/"):].removesuffix(".csv")
            try:
                body, filename = self.app.export_metric(metric_id)
            except KeyError:
                self._json({"error": "That export is not available."}, 404)
                return
            self._send(200, body.encode("utf-8-sig"), "text/csv; charset=utf-8",
                       {"Content-Disposition": f'attachment; filename="{filename}"'})
        elif path.startswith("/api/"):
            self._json({"error": "unknown endpoint"}, 404)
        else:
            self._static(path if path != "/" else "/index.html")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if not self._host_is_local():
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        if not self._authorised(query):
            self._json({"error": "Session key missing."}, 403)
            return
        path = parsed.path
        if path == "/api/files/raw":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                name = urllib.parse.unquote(self.headers.get("X-File-Name") or "")
                added = self.app.add_file_stream(name, self.rfile, length)
                self._json({"added": [added], "errors": [], "inbox": self.app.inbox_files()})
            except UserError as exc:
                self._json({"added": [], "errors": [exc.to_dict()], "inbox": self.app.inbox_files()}, 400)
            except Exception as exc:
                self._json({"added": [], "errors": [{"what_happened": "The file upload did not finish.",
                    "next_action": "Add the file again. No partial file was kept.", "detail": str(exc),
                    "support_code": "E-IN-002"}], "inbox": self.app.inbox_files()}, 200)
            return
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return

        if path == "/api/files":
            added, errors = [], []
            for item in payload.get("files", []):
                try:
                    content = base64.b64decode(item.get("content_base64", ""), validate=True)
                    added.append(self.app.add_file(item.get("name", ""), content))
                except UserError as exc:
                    errors.append(exc.to_dict())
                except Exception as exc:
                    errors.append({"what_happened": f"'{item.get('name')}' could not be added.",
                                   "next_action": "Try a different file.", "detail": str(exc),
                                   "support_code": "E-IN-002"})
            self._json({"added": added, "errors": errors, "inbox": self.app.inbox_files()})
        elif path == "/api/files/remove":
            removed = self.app.remove_file(payload.get("name", ""))
            self._json({"removed": removed, "inbox": self.app.inbox_files()})
        elif path == "/api/process":
            self._json(self.app.process())
        elif path == "/api/shutdown":
            self._json({"stopping": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self._json({"error": "unknown endpoint"}, 404)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    # -- static ------------------------------------------------------------
    def _static(self, path: str) -> None:
        relative = path.lstrip("/").replace("\\", "/")
        target = os.path.normpath(os.path.join(STATIC_DIR, relative))
        if not target.startswith(STATIC_DIR) or not os.path.isfile(target):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript",):
            content_type += "; charset=utf-8"
        with open(target, "rb") as handle:
            self._send(200, handle.read(), content_type)


def start_automation(application) -> None:
    """Process what is already waiting, then keep watching while the app is open."""

    if application.automation["process_on_start"] and application.inbox_files():
        application.process()
    if application.watcher.enabled:
        application.watcher.check_once()
        application.watcher.start()


def make_server(config, workspace, host: str = "127.0.0.1", port: int = 0):
    """Create the loopback server. ``port=0`` lets the machine choose a free one."""

    session_key = secrets.token_urlsafe(24)
    # A crash during a previous run can leave the convenience copies in data/ out of
    # step with the published result. Put them back before anything reads them.
    archive.mirror(workspace)
    application = Application(config, workspace, session_key)
    handler = type("BoundHandler", (Handler,), {"app": application})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server, application


def url_for(server, application) -> str:
    host, port = server.server_address[0], server.server_address[1]
    return f"http://{host}:{port}/?k={application.session_key}"
