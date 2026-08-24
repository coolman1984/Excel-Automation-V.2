"""The deterministic end-to-end run.

Every business run follows one visible state machine. Trusted local data,
calculations, JSON and the standalone dashboard are built and verified before
publication. A failure never replaces the last-good result. Optional enterprise
synchronization happens only after the local result is trustworthy, so a remote
outage can never force Excel to be extracted again.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os
import platform
import traceback
from typing import Callable

from engine import __version__, config as config_module
from engine.data import archive, clean, cube, history, insights, metrics, reconcile, staging
from engine.db import database
from engine.errors import UserError, user_error
from engine.excel import discovery
from engine.logging_setup import logger
from engine.report import dashboard as dashboard_module, standalone
from engine.sync import sql_server

ProgressCallback = Callable[[str, int, str], None]

# Product-level states. These are deliberately business-readable and stable.
STEPS = [
    ("DETECTED", 5, "Source files detected"),
    ("OPENING", 12, "Opening approved source files"),
    ("EXTRACTING", 27, "Extracting data in large chunks"),
    ("VALIDATING", 43, "Validating structure and data quality"),
    ("LOADING", 52, "Loading trusted typed data"),
    ("MERGING", 64, "Resolving history and recurring updates"),
    ("CALCULATING", 78, "Calculating trusted KPIs and insights"),
    ("GENERATING_JSON", 87, "Building compact dashboard datasets"),
    ("GENERATING_DASHBOARD", 93, "Generating the offline dashboard"),
    ("VERIFYING", 98, "Verifying totals, dashboard and publication"),
    ("COMPLETE", 100, "Finished"),
]


@dataclasses.dataclass
class RunResult:
    run_id: str
    status: str                     # PASS | WARNING | BLOCK
    message: str
    started_at: str
    finished_at: str
    state: str = "DETECTED"
    rows_in: int = 0
    rows_clean: int = 0
    rows_rejected: int = 0
    rows_filtered: int = 0
    rows_excluded: int = 0
    files: list[dict] = dataclasses.field(default_factory=list)
    reconciliation: list[dict] = dataclasses.field(default_factory=list)
    sources: list[dict] = dataclasses.field(default_factory=list)
    enterprise_sync: dict = dataclasses.field(default_factory=dict)
    database_backend: str = ""
    error: dict | None = None
    dashboard_published: bool = False

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def new_run_id(now: _dt.datetime | None = None) -> str:
    now = now or _dt.datetime.now()
    return now.strftime("run_%Y%m%d_%H%M%S_%f")[:-3]


def _state_file(workspace, run_id: str) -> str:
    return os.path.join(workspace.run_dir(run_id), "state.json")


def _write_state(workspace, run_id: str, state: str, percent: int, message: str,
                 status: str = "RUNNING") -> None:
    payload = {
        "run_id": run_id,
        "state": state,
        "percent": percent,
        "status": status,
        "message": message,
        "updated_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    archive.atomic_write(_state_file(workspace, run_id), json.dumps(payload, ensure_ascii=False,
                                                                      indent=2))


def run(config: config_module.ProjectConfig, workspace, progress: ProgressCallback | None = None,
        run_id: str | None = None, require_approval: bool = True) -> RunResult:
    """Execute one complete recurring run and return its result."""

    log = logger()
    run_id = run_id or new_run_id()
    started_at = _dt.datetime.now().isoformat(timespec="seconds")
    events: list[tuple[str, int, str]] = []
    result = RunResult(run_id=run_id, status="RUNNING", message="", started_at=started_at,
                       finished_at="")

    def emit(state: str, percent: int, message: str) -> None:
        result.state = state
        events.append((state, percent, message))
        _write_state(workspace, run_id, state, percent, message, result.status)
        log.info("[%s] %3d%% %-22s %s", run_id, percent, state, message)
        if progress is not None:
            progress(state, percent, message)

    backend = str((config.database or {}).get("backend", "auto"))
    try:
        connection = database.connect(workspace.database, backend=backend)
        result.database_backend = connection.backend
    except Exception as exc:
        wrapped = user_error(
            "E-RUN-001",
            what_happened="The local analytical database could not start.",
            next_action="Use the complete packaged application. If this repeats, send the support code to support.",
            detail=str(exc))
        result.status = "BLOCK"
        result.state = "FAILED"
        result.error = wrapped.to_dict()
        result.message = wrapped.what_happened
        result.finished_at = _dt.datetime.now().isoformat(timespec="seconds")
        _write_state(workspace, run_id, "FAILED", 100, result.message, "BLOCK")
        return result

    document: dict | None = None
    html = ""
    try:
        database.migrate(connection)
        if require_approval and not config.is_approved:
            pending = config_module.pending_approvals(config)
            raise user_error(
                "E-CFG-005",
                what_happened="The business meaning of this report has not been approved yet.",
                next_action="Ask the person who owns these numbers to confirm the meaning, then process again.",
                detail=f"pending: {pending}")

        # Register the run before the main business transaction. The detailed state is also
        # persisted to the run folder, so a crash still leaves useful support evidence.
        connection.execute(
            "INSERT OR REPLACE INTO runs(run_id, started_at, status, message) VALUES (?,?,?,?)",
            (run_id, started_at, "RUNNING", ""))

        connection.execute("BEGIN IMMEDIATE")
        try:
            checks: list[reconcile.Check] = []
            source_summaries: list[dict] = []

            emit(*_step("DETECTED"))
            discovered: dict[str, list] = {}
            for source in config.sources:
                files = discovery.collect(source.id, workspace.inbox, source.match,
                                          workspace.staging_dir(run_id), required=source.required)
                discovered[source.id] = files
                for item in files:
                    connection.execute(
                        "INSERT OR REPLACE INTO run_files(run_id, source_id, file_name, size_bytes,"
                        " modified_at, sha256) VALUES (?,?,?,?,?,?)",
                        (run_id, source.id, item.file_name, item.size_bytes,
                         _dt.datetime.fromtimestamp(item.modified_at).isoformat(timespec="seconds"),
                         item.sha256))
                    result.files.append({"source_id": source.id, "file_name": item.file_name,
                                         "sha256": item.sha256, "size_bytes": item.size_bytes,
                                         "modified_at": _dt.datetime.fromtimestamp(item.modified_at).isoformat(timespec="seconds"),
                                         "extraction": (source.extraction or {}).get("mode", "auto")})

            # Fail before extraction when the private workspace is too full to safely
            # stage, transact and publish. A half-written warehouse is considerably less
            # useful than a clear request to free space.
            input_bytes = sum(item.size_bytes for items in discovered.values() for item in items)
            try:
                free_bytes = __import__("shutil").disk_usage(workspace.root).free
                floor = max(int(config.gate("min_free_disk_mb", 512)) * 1024 * 1024,
                            int(input_bytes * float(config.gate("working_space_multiplier", 2.5))))
                if free_bytes < floor:
                    raise user_error(
                        "E-RUN-001",
                        what_happened="There is not enough free disk space to process these files safely.",
                        next_action="Free some space on this drive, then process again. Your existing result is unchanged.",
                        detail=f"free={free_bytes} required={floor} input={input_bytes}")
            except OSError:
                pass

            emit(*_step("OPENING"))
            # Opening and extraction are performed by the staging adapter. OPENING is a visible
            # state because protected Excel may spend time authorizing the workbook before rows flow.
            emit(*_step("EXTRACTING"))
            staged_results: dict[str, staging.StageResult] = {}
            for source in config.sources:
                staged = staging.stage(connection, run_id, source, discovered[source.id])
                staged_results[source.id] = staged
                result.rows_in += staged.rows_read
                result.rows_excluded += staged.rows_excluded

            emit(*_step("VALIDATING"))
            cleaned: dict[str, clean.CleanResult] = {}
            for source in config.sources:
                outcome = clean.clean(connection, run_id, source)
                cleaned[source.id] = outcome
                result.rows_clean += outcome.rows_clean
                result.rows_rejected += outcome.rows_rejected
                result.rows_filtered += outcome.rows_filtered

            emit(*_step("LOADING"))
            # At this point raw values have become typed, quality-controlled clean tables.
            # The explicit state separates ingestion from history decisions for the operator.

            emit(*_step("MERGING"))
            history_results: dict[str, history.HistoryResult] = {}

            def quarantine_writer(source_id, file_name, row_no, rule, field, message, payload):
                connection.execute(
                    "INSERT INTO quarantine(run_id, source_id, file_name, excel_row, rule, field,"
                    " message, severity, row_json) VALUES (?,?,?,?,?,?,?,?,?)",
                    (run_id, source_id, file_name, row_no, rule, field, message, "reject",
                     json.dumps(payload, ensure_ascii=False, default=str)))

            for source in config.sources:
                history_results[source.id] = history.apply(connection, run_id, source,
                                                           quarantine_writer)

            for source in config.sources:
                checks.extend(reconcile.structure_checks(run_id, source,
                                                         staged_results.get(source.id)))
                checks.extend(reconcile.run(connection, run_id, source, history_results[source.id]))
            checks.extend(reconcile.relationships(connection, config, run_id))
            reconcile.save(connection, run_id, checks)
            result.reconciliation = reconcile.as_dicts(checks)

            for source in config.sources:
                outcome = cleaned[source.id]
                merged = history_results[source.id]
                source_summaries.append({
                    "source_id": source.id,
                    "title": source.title,
                    "grain": source.grain,
                    "update_mode": merged.update_mode,
                    "files": [f.file_name for f in discovered[source.id]],
                    "rows_in": outcome.rows_in,
                    "rows_clean": outcome.rows_clean,
                    "rows_rejected": outcome.rows_rejected + merged.corrections_blocked,
                    "rows_filtered": outcome.rows_filtered,
                    "rows_excluded": staged_results[source.id].rows_excluded,
                    "excluded_by_class": staged_results[source.id].excluded_by_class,
                    "new_records": merged.inserted,
                    "corrected_records": merged.corrected,
                    "unchanged_records": merged.unchanged,
                    "closed_records": merged.closed,
                })
            result.sources = source_summaries

            status = reconcile.summary(checks)
            if status == "BLOCK" and config.gate("block_on_reconciliation_failure", True):
                raise user_error(
                    "E-REC-001",
                    what_happened="The totals from your files did not match the calculated totals.",
                    next_action="Nothing was published. Check the highlighted files, then process again.",
                    trusted_data_safe=True,
                    detail=json.dumps(reconcile.as_dicts([c for c in checks if c.status == "BLOCK"]),
                                      ensure_ascii=False))

            max_rejected_pct = float(config.gate("max_rejected_percent", 100))
            if result.rows_in and (result.rows_rejected / result.rows_in) * 100 > max_rejected_pct:
                raise user_error(
                    "E-VAL-001",
                    what_happened="Too many rows did not pass the agreed rules, so the result was not published.",
                    next_action="Review the listed rows in the source file and process again.",
                    detail=f"rejected={result.rows_rejected} of {result.rows_in}, limit={max_rejected_pct}%")

            emit(*_step("CALCULATING"))
            definitions = metrics.parse_file(config.metrics_sql_path)
            payloads = metrics.compute(connection, definitions)
            metrics.save(connection, run_id, payloads)

            analytics = None
            spec = cube.parse(config)
            if spec is not None:
                analytics = cube.build(connection, config, spec)
                cube_checks = [
                    reconcile.Check(source_id="analytics", name=name, expected=expected,
                                    actual=actual, difference="0" if check_status == "PASS" else "",
                                    status=check_status)
                    for name, expected, actual, check_status in cube.verify(connection, config, spec,
                                                                            analytics)]
                checks.extend(cube_checks)
                reconcile.save(connection, run_id, cube_checks)
                result.reconciliation = reconcile.as_dicts(checks)
                if reconcile.summary(cube_checks) == "BLOCK":
                    raise user_error(
                        "E-REC-001",
                        what_happened="The filtered figures did not agree with the trusted totals, so nothing was published.",
                        next_action="Process again. If it repeats, send the support code on.",
                        detail=json.dumps([c.__dict__ for c in cube_checks if c.status == "BLOCK"]))

            highlights = insights.evaluate(config, payloads, {
                "rows_rejected": result.rows_rejected,
                "reconciliation": result.reconciliation,
            }, analytics=analytics)
            insights.save(connection, run_id, highlights)

            emit(*_step("GENERATING_JSON"))
            result.status = status
            result.message = _message_for(status, result)
            result.finished_at = _dt.datetime.now().isoformat(timespec="seconds")
            document = dashboard_module.build(config, result, payloads, highlights, checks,
                                              connection, run_id, status, analytics)
            dashboard_module.verify(document, payloads)

            emit(*_step("GENERATING_DASHBOARD"))
            html = standalone.build(document, config.display_title())
            standalone.verify(html, document)

            emit(*_step("VERIFYING"))
            connection.execute(
                "UPDATE runs SET finished_at = ?, status = ?, rows_in = ?, rows_clean = ?,"
                " rows_rejected = ?, message = ?, manifest_json = ? WHERE run_id = ?",
                (result.finished_at, status, result.rows_in, result.rows_clean, result.rows_rejected,
                 result.message, json.dumps(_manifest(config, result), ensure_ascii=False,
                                            default=str), run_id))
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

        # Local publication is independent from SQL Server. Both strings are already built and
        # verified in memory, so neither can expose a half-generated dashboard.
        assert document is not None
        archive.atomic_write(workspace.dashboard, json.dumps(document, ensure_ascii=False,
                                                             indent=2, default=str))
        archive.atomic_write(workspace.dashboard_html, html)
        result.dashboard_published = True

        # Optional enterprise mirror. A remote outage changes only this status, not the trusted run.
        sync_result = sql_server.sync(config, connection, run_id)
        result.enterprise_sync = sync_result.to_dict()
        document["enterprise_sync"] = result.enterprise_sync
        # Verification has finished successfully; the persisted report represents a completed run.
        result.state = "COMPLETE"
        document["run"]["state"] = "COMPLETE"
        # Rebuild the portable HTML so its status matches the JSON users see in the app.
        html = standalone.build(document, config.display_title())
        standalone.verify(html, document)
        archive.atomic_write(workspace.dashboard, json.dumps(document, ensure_ascii=False,
                                                             indent=2, default=str))
        archive.atomic_write(workspace.dashboard_html, html)

        archive.snapshot(workspace.archive, run_id,
                         [workspace.dashboard, workspace.dashboard_html, workspace.database],
                         keep=int(config.gate("archive_keep_runs", 10)))
        emit(*_step("COMPLETE"))
        _write_events(connection, run_id, events)
        return result

    except UserError as exc:
        result.status = "BLOCK"
        result.state = "FAILED"
        result.error = exc.to_dict()
        result.message = exc.what_happened
        result.finished_at = _dt.datetime.now().isoformat(timespec="seconds")
        log.error("[%s] %s | %s", run_id, exc, exc.detail)
        _record_failure(connection, result)
        events.append(("FAILED", 100, exc.what_happened))
        _write_state(workspace, run_id, "FAILED", 100, exc.what_happened, "BLOCK")
        _write_events(connection, run_id, events)
        return result
    except Exception:
        detail = traceback.format_exc()
        log.error("[%s] unexpected failure\n%s", run_id, detail)
        wrapped = user_error(
            "E-RUN-001",
            what_happened="The run stopped before it finished. Your previous results were kept.",
            next_action="Try again. If it happens twice, send the support code to your support contact.",
            detail=detail)
        result.status = "BLOCK"
        result.state = "FAILED"
        result.error = wrapped.to_dict()
        result.message = wrapped.what_happened
        result.finished_at = _dt.datetime.now().isoformat(timespec="seconds")
        _record_failure(connection, result)
        events.append(("FAILED", 100, wrapped.what_happened))
        _write_state(workspace, run_id, "FAILED", 100, wrapped.what_happened, "BLOCK")
        _write_events(connection, run_id, events)
        return result
    finally:
        connection.close()


def _step(name: str) -> tuple[str, int, str]:
    for state, percent, message in STEPS:
        if state == name:
            return state, percent, message
    return name, 0, name


def _message_for(status: str, result: RunResult) -> str:
    if status == "PASS":
        return f"{result.rows_clean:,} rows processed and every trusted check passed."
    if status == "WARNING":
        return f"{result.rows_clean:,} rows processed. Some items need attention, but trusted publication is valid."
    return "The result was not published."


def _manifest(config, result: RunResult) -> dict:
    return {
        "engine_version": __version__,
        "project": config.project_name,
        "run_id": result.run_id,
        "started_at": result.started_at,
        "status": result.status,
        "state": result.state,
        "database_backend": result.database_backend,
        "files": result.files,
        "rows": {"in": result.rows_in, "clean": result.rows_clean,
                 "rejected": result.rows_rejected, "filtered": result.rows_filtered,
                 "excluded": result.rows_excluded},
        "reconciliation": result.reconciliation,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def _record_failure(connection, result: RunResult) -> None:
    try:
        connection.execute(
            "INSERT OR REPLACE INTO runs(run_id, started_at, finished_at, status, rows_in,"
            " rows_clean, rows_rejected, message, manifest_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (result.run_id, result.started_at, result.finished_at, "BLOCK", result.rows_in,
             result.rows_clean, result.rows_rejected, result.message,
             json.dumps({"error": result.error, "state": result.state}, ensure_ascii=False)))
    except Exception:
        logger().error("could not record the failed run %s", result.run_id)


def _write_events(connection, run_id: str, events) -> None:
    try:
        connection.executemany(
            "INSERT OR REPLACE INTO run_events(run_id, seq, at, step, percent, message)"
            " VALUES (?,?,?,?,?,?)",
            [(run_id, index, _dt.datetime.now().isoformat(timespec="seconds"),
              step, percent, message) for index, (step, percent, message) in enumerate(events)])
    except Exception:
        pass


def last_dashboard(workspace) -> dict | None:
    if not os.path.isfile(workspace.dashboard):
        return None
    try:
        with open(workspace.dashboard, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
