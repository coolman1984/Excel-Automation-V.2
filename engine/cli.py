"""PROJECT_TOOL - the only commands an adaptation agent needs.

    PROJECT_TOOL doctor   --project projects/my_project
    PROJECT_TOOL run      --project projects/my_project --inbox <folder with Excel files>
    PROJECT_TOOL serve    --project projects/my_project
    PROJECT_TOOL new-project MyProject
    PROJECT_TOOL deliver  --project projects/my_project --output-dir release
    PROJECT_TOOL package verify --zip release/MyProject.zip
    PROJECT_TOOL test
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import unittest

from engine import __version__, config as config_module, paths, pipeline
from engine.data import cube, metrics, resolve, structure
from engine.db import database
from engine.excel import com_reader, csv_reader, discovery, layout, xlsx_reader
from engine.sync import sql_server
from engine.errors import UserError
from engine.logging_setup import configure
from engine.packaging import builder, verifier

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PROJECT = os.path.join(REPO_ROOT, "projects", "_template")


def _load(project_dir: str) -> config_module.ProjectConfig:
    return config_module.load(os.path.abspath(project_dir))


def _workspace(project_dir: str, data_dir: str | None):
    workspace = paths.workspace_for(os.path.abspath(project_dir), data_dir)
    configure(workspace.log_file)
    return workspace


# ---------------------------------------------------------------- commands
def command_doctor(args) -> int:
    problems: list[str] = []
    notes: list[str] = []
    try:
        config = _load(args.project)
    except UserError as exc:
        print(f"BLOCK  {exc.code}: {exc.what_happened}\n       next: {exc.next_action}\n"
              f"       detail: {exc.detail}")
        return 1

    print(f"project      : {config.project_name}")
    print(f"title        : {config.display_title()}")
    print(f"sources      : {', '.join(s.id for s in config.sources)}")

    backend = str((config.database or {}).get("backend", "auto")).lower()
    resolved = "duckdb" if database.backend_available("duckdb") and backend in {"auto", "duckdb"} else "sqlite"
    print(f"database     : {backend} (resolved here: {resolved})")
    if backend == "duckdb" and not database.backend_available("duckdb"):
        problems.append("DuckDB is required by project configuration but is not available in this runtime")

    com_sources = [source.id for source in config.sources
                   if str((source.extraction or {}).get("mode", "auto")).lower() == "excel_com"]
    if com_sources:
        print(f"excel COM    : required for {', '.join(com_sources)}")
        if not com_reader.available():
            problems.append("Excel COM is required but this environment is not Windows with pywin32/Excel available")
    else:
        print("excel COM    : automatic/optional")

    sync_cfg = sql_server.settings(config)
    if sync_cfg["enabled"]:
        credential_ready = bool(os.environ.get(sync_cfg["connection_string_env"], "").strip())
        print(f"SQL Server   : enabled ({'credentials present' if credential_ready else 'credentials pending'})")
        if not credential_ready:
            notes.append(f"SQL Server is enabled; set {sync_cfg['connection_string_env']} on the target machine")
    else:
        print("SQL Server   : disabled")

    pending = config_module.pending_approvals(config)
    if pending:
        problems.append(f"business meaning not approved yet: {pending}")

    for source in config.sources:
        if not source.business_key:
            notes.append(f"source '{source.id}' has no business_key; identical rows will be "
                         f"de-duplicated by their content hash")
        if not source.grain:
            notes.append(f"source '{source.id}' does not say what one row represents")
        if not source.control_totals:
            notes.append(f"source '{source.id}' has no control total; nothing proves the numbers")

    try:
        definitions = metrics.parse_file(config.metrics_sql_path)
    except UserError as exc:
        problems.append(f"{exc.code}: {exc.what_happened} ({exc.detail})")
        definitions = []
    if not definitions:
        problems.append(f"no metrics defined in {config.metrics_sql}")
    else:
        print(f"metrics      : {', '.join(d.id for d in definitions)}")

    try:
        spec = cube.parse(config)
    except UserError as exc:
        problems.append(f"{exc.code}: {exc.next_action} ({exc.detail})")
        spec = None
    if spec is None:
        notes.append("no 'analytics' block: the page will have no filters or charts of its own")
    else:
        print(f"filters      : {', '.join(d.title for d in spec['dimensions']) or 'none'}"
              f"  (by {spec['grain']})")
        print(f"measures     : {', '.join(m.id for m in spec['measures'])}")
        charts = spec["raw"].get("charts", [])
        print(f"charts       : {', '.join(c.get('id', '?') for c in charts) or 'none'}")
        if not charts:
            notes.append("'analytics' defines no charts, so the dashboard shows only KPI cards")

    known = {d.id for d in definitions}
    for key in ("kpis", "charts", "tables"):
        for entry in config.dashboard.get(key, []) or []:
            metric_id = entry if isinstance(entry, str) else entry.get("metric")
            if metric_id not in known:
                problems.append(f"dashboard.{key} refers to unknown metric '{metric_id}'")

    for note in notes:
        print(f"NOTE   {note}")
    for problem in problems:
        print(f"BLOCK  {problem}")

    if getattr(args, "probe", None):
        print()
        _run_probe(config, args.probe)

    print("RESULT: PASS" if not problems else "RESULT: FAIL")
    return 0 if not problems else 1


def _run_probe(config: config_module.ProjectConfig, probe_dir: str) -> None:
    """Show how a representative file would be read, before any row is merged.

    Read-only: nothing here copies a file, opens the warehouse, or writes
    anything. It answers exactly the questions an adaptation agent - or an
    operator wondering why a file drifted - needs before trusting a run:
    which sheet and header row were chosen, how every mapped column resolved
    and at which rung, and what the file's rows classify as.
    """

    probe_dir = os.path.abspath(probe_dir)
    for source in config.sources:
        matches = discovery.find_matching(probe_dir, source.match)
        print(f"probe source '{source.id}' ---------------------------------")
        if not matches:
            print(f"  no file in {probe_dir} matches {source.match}")
            continue
        for path in matches:
            _probe_file(source, path)


def _probe_file(source, path: str) -> None:
    name = os.path.basename(path)
    extraction = source.extraction or {}
    mode = str(extraction.get("mode", "auto")).lower()
    ext = os.path.splitext(name)[1].lower()
    if mode == "excel_com" or ext in {".xls", ".xlsb"}:
        print(f"  {name}: requires the Excel COM route (protected/legacy workbook); "
              f"not probed here - see engine/excel/com_reader.py")
        return

    try:
        if source.format == "csv":
            sample = csv_reader.sample_rows(path, delimiter=source.delimiter,
                                            limit=source.header_search_rows)
            location = layout.find_header(sample, source, source.header_row,
                                          source.header_search_rows)
            if location.values is None:
                print(f"  {name}: BLOCK  no row in the first {source.header_search_rows} "
                     f"matches any configured column")
                return
            headers, _, _ = csv_reader.inspect(path, delimiter=source.delimiter,
                                                header_row=location.row_number)
            row_source = csv_reader.iter_rows(path, delimiter=source.delimiter,
                                              header_row=location.row_number, strict_width=False)
        else:
            sample = list(xlsx_reader.Workbook(path).iter_rows(
                sheet=source.sheet, max_rows=source.header_search_rows))
            location = layout.find_header(sample, source, source.header_row,
                                          source.header_search_rows)
            if location.values is None:
                print(f"  {name}: BLOCK  no row in the first {source.header_search_rows} "
                     f"matches any configured column")
                return
            headers = xlsx_reader.inspect(path, sheet=source.sheet, header_row=location.row_number)
            row_source = xlsx_reader.iter_data_rows(path, sheet=source.sheet,
                                                     header_row=location.row_number)
    except UserError as exc:
        print(f"  {name}: BLOCK  {exc.code}: {exc.what_happened}")
        return

    print(f"  {name}")
    header_note = (f"row {location.row_number}" if not location.moved else
                  f"row {location.row_number} (configured row {source.header_row} did not "
                  f"look like the header)")
    print(f"    header      : {header_note}")

    result = resolve.resolve(source, headers)
    for column in result.resolutions:
        if not column.resolved:
            flag = "MISSING (required)" if column.required else "missing (optional)"
            print(f"    column      : '{column.source_label}' -> {flag}")
        else:
            print(f"    column      : {column.describe()}")
    if result.ambiguous:
        for item in result.ambiguous:
            print(f"    AMBIGUOUS   : '{item.column}' matches {item.candidates} at "
                 f"the {item.rung} rung")

    positions = {column.field: idx for column, idx in
                ((c, c.header_index) for c in result.resolutions) if idx is not None}
    classifier = structure.Classifier(source)
    field_names = [c.field for c in source.columns]
    seen = 0
    for row_number, values in row_source:
        if classifier.should_stop(row_number):
            break
        seen += 1
        mapped = {field: (values[positions[field]]
                          if field in positions and positions[field] < len(values) else None)
                 for field in field_names}
        classifier.classify(row_number, mapped)

    print(f"    rows        : {seen} seen -> "
         f"{classifier.counts.get(structure.DATA, 0)} data" +
         "".join(f" + {count} {structure.CLASS_TITLES.get(kind, kind).lower()}"
                for kind, count in sorted(classifier.counts.items()) if kind != structure.DATA))
    if classifier.declared_totals:
        unverified = structure.unverified_totals(classifier.declared_totals)
        state = "all verified" if not unverified else f"{len(unverified)} DISAGREE with their rows"
        print(f"    totals      : {len(classifier.declared_totals)} total line(s) found, {state}")
    if classifier.suspicions:
        print(f"    NOTE        : {len(classifier.suspicions)} row(s) mention 'total' but "
             f"were kept as data (see rows_that_may_be_totals when this file actually runs)")
    if seen:
        low, high = int(seen * 0.8), int(seen * 1.2)
        print(f"    volume      : this sample had {seen} row(s); if daily volume is normally "
             f"similar, consider expected_rows_min ~{low} / expected_rows_max ~{high} once that "
             f"gate is available, to catch a truncated export early")


def command_run(args) -> int:
    config = _load(args.project)
    workspace = _workspace(args.project, args.data)
    if args.inbox:
        for name in sorted(os.listdir(args.inbox)):
            source = os.path.join(args.inbox, name)
            if os.path.isfile(source):
                shutil.copy2(source, os.path.join(workspace.inbox, name))
    result = pipeline.run(config, workspace, progress=_print_progress if args.verbose else None,
                          require_approval=not args.allow_unapproved)
    print(f"\nrun        : {result.run_id}")
    print(f"status     : {result.status}")
    print(f"message    : {result.message}")
    print(f"rows       : read={result.rows_in} used={result.rows_clean} "
          f"attention={result.rows_rejected} out-of-scope={result.rows_filtered}")
    for check in result.reconciliation:
        print(f"  {check['status']:<8} {check['source_id']}.{check['name']}: "
              f"{check['expected']} -> {check['actual']} (diff {check['difference']})")
    if result.error:
        print(f"\n{result.error['support_code']}: {result.error['what_happened']}")
        print(f"next: {result.error['next_action']}")
        if args.verbose:
            print(result.error["detail"])
    else:
        print(f"dashboard  : {workspace.dashboard}")
    return 0 if result.status in ("PASS", "WARNING") else 1


def _print_progress(step: str, percent: int, message: str) -> None:
    print(f"  {percent:3d}%  {message}")


def command_serve(args) -> int:
    argv = ["--project", os.path.abspath(args.project)]
    if args.data:
        argv += ["--data", args.data]
    if args.port:
        argv += ["--port", str(args.port)]
    if args.no_browser:
        argv += ["--no-browser"]
    sys.argv = [sys.argv[0]] + argv
    from engine import launch
    return launch.main()


def _display_path(path: str) -> str:
    """A short path when possible, an absolute one when not.

    On Windows a project folder may live on a different drive from the
    repository, and a relative path between two drives does not exist.
    """

    try:
        relative = os.path.relpath(path, REPO_ROOT)
    except ValueError:
        return path
    return path if relative.startswith("..") else relative


def command_new_project(args) -> int:
    target = os.path.abspath(args.directory or os.path.join(REPO_ROOT, "projects", args.name))
    if os.path.exists(target):
        print(f"BLOCK  {target} already exists")
        return 1
    shutil.copytree(TEMPLATE_PROJECT, target)
    config_path = os.path.join(target, "project.json")
    with open(config_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    data["project_name"] = args.name
    data["title"] = {"en": args.name}
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"created {target}")
    print("next: describe the sources in project.json, then run PROJECT_TOOL doctor "
          f"--project {_display_path(target)}")
    return 0


def command_app_stage(args) -> int:
    app_dir = builder.stage_application(os.path.abspath(args.project), os.path.abspath(args.out),
                                        args.runtime, include_fixtures=args.include_fixtures)
    print(f"staged application: {app_dir}")
    if not args.runtime:
        print("NOTE   no private runtime was included. Pass --runtime <windows embeddable python "
              "folder> before delivering to a user.")
    return 0


def command_package_build(args) -> int:
    result = builder.build(args.project_name, os.path.abspath(args.app_dir),
                           os.path.abspath(args.output_dir), args.display_name)
    print(f"package    : {result.zip_path}")
    print(f"files      : {result.files}")
    print(f"runtime    : {'included' if result.runtime_included else 'MISSING'}")
    return 0


def command_package_verify(args) -> int:
    result = verifier.verify(os.path.abspath(args.zip), require_runtime=not args.allow_missing_runtime)
    print(result.report())
    return 0 if result.ok else 1


def command_deliver(args) -> int:
    """Stage A + Stage B + verification in one step."""

    config = _load(args.project)
    name = args.project_name or config.project_name
    output_dir = os.path.abspath(args.output_dir)
    app_dir = os.path.join(output_dir, "_app", name)
    builder.stage_application(os.path.abspath(args.project), app_dir, args.runtime,
                              include_fixtures=args.include_fixtures)
    result = builder.build(name, app_dir, output_dir, config.display_title())
    print(f"package    : {result.zip_path}")
    verification = verifier.verify(result.zip_path,
                                   require_runtime=not args.allow_missing_runtime)
    print(verification.report())
    return 0 if verification.ok else 1


# The checks that matter while adapting a project: data, meaning and numbers.
# The rest (packaging, the delivered app, the browser) only moves when the
# shared engine moves, so an adaptation should not pay for it on every edit.
QUICK_TESTS = ["tests.test_config", "tests.test_types", "tests.test_excel",
               "tests.test_metrics", "tests.test_analytics", "tests.test_pipeline",
               "tests.test_reconcile"]


def command_test(args) -> int:
    loader = unittest.TestLoader()
    if args.quick:
        suite = loader.loadTestsFromNames(QUICK_TESTS)
        print("quick: data, meaning and numbers. Run the full suite before delivering.")
    else:
        suite = loader.discover(os.path.join(REPO_ROOT, "tests"), top_level_dir=REPO_ROOT)
    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1)
    return 0 if runner.run(suite).wasSuccessful() else 1


def command_fixtures(args) -> int:
    script = os.path.join(REPO_ROOT, "tools", "make_fixtures.py")
    return subprocess.call([sys.executable, script])


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="PROJECT_TOOL",
                                     description="Ultimate Excel Automation V11 project tool")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check a project configuration before running it")
    doctor.add_argument("--project", required=True)
    doctor.add_argument("--probe",
                        help="folder with a representative file per source; report the sheet, "
                             "header row, column resolution and row classification that would "
                             "be used, without processing anything")
    doctor.set_defaults(func=command_doctor)

    run = sub.add_parser("run", help="run the pipeline once")
    run.add_argument("--project", required=True)
    run.add_argument("--inbox", help="folder of Excel files to copy in before running")
    run.add_argument("--data", help="where the database and results live")
    run.add_argument("--verbose", action="store_true")
    run.add_argument("--allow-unapproved", action="store_true",
                     help="run even though the business meaning is not approved (development only)")
    run.set_defaults(func=command_run)

    serve = sub.add_parser("serve", help="start the local application")
    serve.add_argument("--project", required=True)
    serve.add_argument("--data")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--no-browser", action="store_true")
    serve.set_defaults(func=command_serve)

    new = sub.add_parser("new-project", help="copy the project template")
    new.add_argument("name")
    new.add_argument("--directory")
    new.set_defaults(func=command_new_project)

    app = sub.add_parser("app", help="stage the private application folder")
    app_sub = app.add_subparsers(dest="app_command", required=True)
    stage = app_sub.add_parser("stage")
    stage.add_argument("--project", required=True)
    stage.add_argument("--out", required=True)
    stage.add_argument("--runtime")
    stage.add_argument("--include-fixtures", action="store_true")
    stage.set_defaults(func=command_app_stage)

    package = sub.add_parser("package", help="build or verify the final operator ZIP")
    package_sub = package.add_subparsers(dest="package_command", required=True)
    build_cmd = package_sub.add_parser("build")
    build_cmd.add_argument("--project-name", required=True)
    build_cmd.add_argument("--app-dir", required=True)
    build_cmd.add_argument("--output-dir", required=True)
    build_cmd.add_argument("--display-name")
    build_cmd.set_defaults(func=command_package_build)
    verify_cmd = package_sub.add_parser("verify")
    verify_cmd.add_argument("--zip", required=True)
    verify_cmd.add_argument("--allow-missing-runtime", action="store_true")
    verify_cmd.set_defaults(func=command_package_verify)

    deliver = sub.add_parser("deliver", help="stage, package and verify in one step")
    deliver.add_argument("--project", required=True)
    deliver.add_argument("--output-dir", default="release")
    deliver.add_argument("--project-name")
    deliver.add_argument("--runtime")
    deliver.add_argument("--include-fixtures", action="store_true")
    deliver.add_argument("--allow-missing-runtime", action="store_true")
    deliver.set_defaults(func=command_deliver)

    test = sub.add_parser("test", help="run the template test suite")
    test.add_argument("--verbose", action="store_true")
    test.add_argument("--quick", action="store_true",
                      help="only the checks an adaptation can break (a few seconds)")
    test.set_defaults(func=command_test)

    fixtures = sub.add_parser("fixtures", help="regenerate the example Excel fixtures")
    fixtures.set_defaults(func=command_fixtures)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except UserError as exc:
        print(f"{exc.code}: {exc.what_happened}")
        print(f"next: {exc.next_action}")
        if exc.detail:
            print(f"detail: {exc.detail}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
