"""The backend the package ships must be the backend that was proven.

DuckDB is the documented production backend, but the whole suite used to run on
the SQLite fallback, so nothing had ever executed the production path. The first
attempt failed on the very first migration: ``at`` is a reserved word in DuckDB.
Two more portability breaks followed - ``a IS b`` as null-safe equality, and
``ROWID`` on the right side of a LEFT JOIN.

These tests exist so the same numbers have to come out of both backends, and so
each portability break stays fixed.
"""

from __future__ import annotations

import os
import unittest

from engine import config as config_module, pipeline
from engine.db import database
from tests.helpers import example_workspace, project_copy, remove_all, temp_dir

HAS_DUCKDB = database.backend_available("duckdb")
BACKENDS = ["sqlite"] + (["duckdb"] if HAS_DUCKDB else [])
needs_duckdb = unittest.skipUnless(HAS_DUCKDB, "DuckDB is not installed in this environment")


class BackendSelectionTest(unittest.TestCase):
    def setUp(self):
        self.cleanup: list[str] = []
        self.previous = os.environ.get("UEA_DB_BACKEND")

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("UEA_DB_BACKEND", None)
        else:
            os.environ["UEA_DB_BACKEND"] = self.previous
        remove_all(self.cleanup)

    def path(self, name="warehouse.db"):
        return os.path.join(temp_dir(self.cleanup), name)

    def test_explicit_project_backend_beats_the_environment(self):
        os.environ["UEA_DB_BACKEND"] = "duckdb"
        connection = database.connect(self.path(), backend="sqlite")
        self.addCleanup(connection.close)
        self.assertEqual(connection.backend, "sqlite")

    def test_auto_defers_to_the_environment(self):
        """"auto" means the project has no opinion, so the suite can pin a backend."""

        os.environ["UEA_DB_BACKEND"] = "sqlite"
        connection = database.connect(self.path(), backend="auto")
        self.addCleanup(connection.close)
        self.assertEqual(connection.backend, "sqlite")

    def test_an_unknown_backend_is_refused(self):
        with self.assertRaises(ValueError):
            database.connect(self.path(), backend="postgres")

    @needs_duckdb
    def test_duckdb_is_required_when_the_project_demands_it(self):
        os.environ["UEA_DB_BACKEND"] = "sqlite"
        connection = database.connect(self.path(), backend="duckdb")
        self.addCleanup(connection.close)
        self.assertEqual(connection.backend, "duckdb")

    @needs_duckdb
    def test_the_spill_directory_is_actually_applied(self):
        """It used to be set with a bound parameter, which DuckDB rejects. The
        exception was swallowed, so the setting that stops a wide workbook running
        out of memory silently never took effect."""

        path = self.path()
        connection = database.connect(path, backend="duckdb")
        self.addCleanup(connection.close)
        configured = connection.execute("SELECT current_setting('temp_directory')").fetchone()[0]
        self.assertEqual(os.path.abspath(configured), os.path.abspath(path) + ".spill")

    @needs_duckdb
    def test_the_spill_directory_is_not_mistaken_for_an_atomic_write_temp_file(self):
        path = os.path.join(temp_dir(self.cleanup), "warehouse.db")
        connection = database.connect(path, backend="duckdb")
        self.addCleanup(connection.close)
        leftovers = [name for name in os.listdir(os.path.dirname(path)) if name.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class PortabilityTest(unittest.TestCase):
    """Each of these guards one construct that only SQLite accepts."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def connect(self, backend):
        connection = database.connect(
            os.path.join(temp_dir(self.cleanup), "warehouse.db"), backend=backend)
        self.addCleanup(connection.close)
        return connection

    def test_null_safe_equality_uses_the_dialect_each_backend_accepts(self):
        sqlite = self.connect("sqlite")
        self.assertEqual(database.null_safe_eq(sqlite, "a", "b"), "a IS b")
        if HAS_DUCKDB:
            duck = self.connect("duckdb")
            self.assertEqual(database.null_safe_eq(duck, "a", "b"),
                             "a IS NOT DISTINCT FROM b")

    def test_null_safe_equality_runs_and_treats_null_as_comparable(self):
        for backend in BACKENDS:
            with self.subTest(backend=backend):
                connection = self.connect(backend)
                database.create_table(connection, "t", [("a", "TEXT"), ("b", "TEXT")])
                database.insert_many(connection, "t", ["a", "b"],
                                     [["x", "x"], [None, None], ["x", None]])
                clause = database.null_safe_eq(connection, "a", "b")
                matched = database.scalar(connection, f"SELECT COUNT(*) FROM t WHERE {clause}")
                self.assertEqual(int(matched), 2)   # ("x","x") and (NULL,NULL)

    def test_every_migration_applies(self):
        """The reserved word 'at' in run_events broke this on the first attempt."""

        for backend in BACKENDS:
            with self.subTest(backend=backend):
                connection = self.connect(backend)
                applied = database.migrate(connection)
                self.assertIn("0001_core.sql", applied)
                self.assertIn("0004_structure.sql", applied)
                for table in ("runs", "run_files", "quarantine", "reconciliation", "metrics",
                              "insights", "run_events", "filtered_rows", "sync_events",
                              "excluded_rows", "source_totals"):
                    self.assertTrue(database.table_exists(connection, table), table)
                # Applying twice must be a no-op, not an error.
                self.assertEqual(database.migrate(connection), [])

    def test_the_reserved_column_can_be_written_and_read(self):
        for backend in BACKENDS:
            with self.subTest(backend=backend):
                connection = self.connect(backend)
                database.migrate(connection)
                connection.execute(
                    'INSERT INTO run_events(run_id, seq, "at", step, percent, message)'
                    " VALUES (?,?,?,?,?,?)", ("r1", 0, "2026-01-01T00:00:00", "DETECTED", 5, "x"))
                row = connection.execute(
                    'SELECT "at", step FROM run_events WHERE run_id = ?', ("r1",)).fetchone()
                self.assertEqual(row["step"], "DETECTED")


@unittest.skipUnless(HAS_DUCKDB, "cross-backend comparison needs both backends")
class SameNumbersOnBothBackendsTest(unittest.TestCase):
    """The gate that makes the rest of this file worth having."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def run_on(self, backend):
        project = project_copy(self.cleanup)
        workspace = example_workspace(self.cleanup)
        config = config_module.load(project)
        config.database = {"backend": backend}
        result = pipeline.run(config, workspace)
        self.assertIn(result.status, ("PASS", "WARNING"), result.message)
        self.assertEqual(result.database_backend, backend)
        return result, pipeline.last_dashboard(workspace)

    def test_the_trusted_numbers_are_identical(self):
        sqlite_result, sqlite_doc = self.run_on("sqlite")
        duck_result, duck_doc = self.run_on("duckdb")

        self.assertEqual(sqlite_result.rows_clean, duck_result.rows_clean)
        self.assertEqual(sqlite_result.rows_rejected, duck_result.rows_rejected)
        self.assertEqual(sqlite_result.rows_filtered, duck_result.rows_filtered)
        self.assertEqual(sqlite_result.status, duck_result.status)

        def kpis(document):
            return {item["id"]: str(item["value"])
                    for item in document.get("analytics", {}).get("kpis", [])
                    if isinstance(item, dict)}

        def controls(result):
            return {check["name"]: (check["expected"], check["actual"], check["status"])
                    for check in result.reconciliation}

        self.assertEqual(kpis(sqlite_doc), kpis(duck_doc))
        self.assertEqual(controls(sqlite_result), controls(duck_result))

    def test_the_same_metrics_come_out_of_both(self):
        _sqlite_result, sqlite_doc = self.run_on("sqlite")
        _duck_result, duck_doc = self.run_on("duckdb")

        def metrics(document):
            return sorted((item.get("id"), str(item.get("value")))
                          for item in (document.get("metrics") or [])
                          if isinstance(item, dict))

        self.assertEqual(metrics(sqlite_doc), metrics(duck_doc))


if __name__ == "__main__":
    unittest.main()
