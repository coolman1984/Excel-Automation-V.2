"""The processed-file ledger and inbox lifecycle.

The regression this exists for (P0-2 from the project review): the inbox was
never cleared and no record was kept of what had already been processed, so
every run reprocessed every file ever supplied. Two consecutive runs against
a single unchanged file read double the file's own row count - reproduced
with docs/review/edge_case_repro.py before this fix existed.

A second, more serious defect was found while building this fix rather than
before it: naively giving a source zero rows on a "nothing new" run is not a
harmless no-op for SNAPSHOT or REPLACE_PERIOD - both close every record the
run did not touch, so an empty run reads as "everything just disappeared" and
closes the whole trusted table. See SnapshotSafetyTest below.
"""

from __future__ import annotations

import datetime as _dt
import os
import unittest

from engine import config as config_module, paths, pipeline
from engine.data import archive, ledger
from engine.db import database
from engine.excel.discovery import hash_file
from engine.excel.xlsx_writer import write_sheet
from tests.helpers import edit_config, project_copy, remove_all, temp_dir

SALES_HEAD = ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product",
             "Quantity", "Unit Price", "Amount", "Status"]
CUSTOMER_HEAD = ["Customer ID", "Customer Name", "Segment", "Country"]
CUSTOMERS = [["C001", "Customer 01", "Retail", "Saudi Arabia"],
             ["C002", "Customer 02", "Wholesale", "Saudi Arabia"]]


def sales_rows(day=5, invoice="INV-1", amount=200.0):
    return [[invoice, 1, _dt.date(2026, 1, day), "C001", "Pump", 2, amount / 2, amount, "Posted"]]


class LedgerUnitTest(unittest.TestCase):
    """The ledger's own read/write contract, independent of the pipeline."""

    def setUp(self):
        self.cleanup: list[str] = []
        self.connection = database.connect(
            os.path.join(temp_dir(self.cleanup), "warehouse.db"), backend="sqlite")
        database.migrate(self.connection)

    def tearDown(self):
        self.connection.close()
        remove_all(self.cleanup)

    def test_an_unrecorded_file_is_not_already_processed(self):
        self.assertFalse(ledger.already_processed(self.connection, "sales", "abc123"))

    def test_a_recorded_file_is_already_processed(self):
        ledger.record(self.connection, "sales", "sales.xlsx", "abc123", "run_1", 10)
        self.assertTrue(ledger.already_processed(self.connection, "sales", "abc123"))

    def test_the_same_content_under_a_different_source_id_is_not_shared(self):
        """The ledger is scoped per source: the same bytes matching two
        different sources' patterns must be judged independently."""

        ledger.record(self.connection, "sales", "sales.xlsx", "abc123", "run_1", 10)
        self.assertFalse(ledger.already_processed(self.connection, "customers", "abc123"))

    def test_first_run_is_recorded_and_kept_through_a_later_update(self):
        ledger.record(self.connection, "sales", "sales.xlsx", "abc123", "run_1", 10)
        ledger.record(self.connection, "sales", "sales.xlsx", "abc123", "run_5", 10)
        row = self.connection.execute(
            "SELECT first_run, last_run FROM processed_files WHERE source_id = 'sales'"
        ).fetchone()
        self.assertEqual(row["first_run"], "run_1")
        self.assertEqual(row["last_run"], "run_5")

    def test_has_ever_succeeded_is_false_until_a_file_is_recorded(self):
        self.assertFalse(ledger.has_ever_succeeded(self.connection, "sales"))
        ledger.record(self.connection, "sales", "sales.xlsx", "abc123", "run_1", 10)
        self.assertTrue(ledger.has_ever_succeeded(self.connection, "sales"))

    def test_split_separates_new_from_already_processed(self):
        class Stub:
            def __init__(self, sha):
                self.sha256 = sha

        ledger.record(self.connection, "sales", "a.xlsx", "seen", "run_1", 1)
        new, seen = ledger.split(self.connection, "sales", [Stub("seen"), Stub("fresh")], False)
        self.assertEqual([f.sha256 for f in new], ["fresh"])
        self.assertEqual([f.sha256 for f in seen], ["seen"])

    def test_reprocess_identical_bypasses_the_skip(self):
        class Stub:
            def __init__(self, sha):
                self.sha256 = sha

        ledger.record(self.connection, "sales", "a.xlsx", "seen", "run_1", 1)
        new, seen = ledger.split(self.connection, "sales", [Stub("seen")], True)
        self.assertEqual([f.sha256 for f in new], ["seen"])
        self.assertEqual(seen, [])


class PipelineLedgerTest(unittest.TestCase):
    """The ledger wired through a real run: the reproduction from the review."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def workspace_with(self, sales_sheet_rows, mutate=None):
        project = project_copy(self.cleanup)
        import shutil
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        if mutate is not None:
            edit_config(project, mutate)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_2026.xlsx"), SALES_HEAD,
                   sales_sheet_rows, "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                   CUSTOMERS, "Customers")
        return project, workspace

    def keep_files(self, data):
        data["inbox"] = {"after_run": "keep"}

    def test_the_original_defect_two_runs_no_longer_double_count(self):
        """docs/review/edge_case_repro.py's reproduction: two consecutive runs
        against one unchanged file used to report double the file's own rows."""

        project, workspace = self.workspace_with(sales_rows(), self.keep_files)
        config = config_module.load(project)

        first = pipeline.run(config, workspace)
        second = pipeline.run(config, workspace)

        self.assertEqual(first.status, "PASS", first.message)
        self.assertEqual(second.status, "PASS", second.message)
        self.assertEqual(first.rows_in, 3)     # 1 sales row + 2 customers
        self.assertEqual(second.rows_in, 0)    # nothing new the second time
        sales = next(s for s in second.sources if s["source_id"] == "sales")
        self.assertTrue(sales["skipped"])

    def test_a_renamed_but_identical_file_is_still_recognised(self):
        project, workspace = self.workspace_with(sales_rows(), self.keep_files)
        config = config_module.load(project)
        first = pipeline.run(config, workspace)
        self.assertEqual(first.status, "PASS", first.message)

        os.rename(os.path.join(workspace.inbox, "sales_2026.xlsx"),
                 os.path.join(workspace.inbox, "sales_2026_copy.xlsx"))
        second = pipeline.run(config, workspace)

        sales = next(s for s in second.sources if s["source_id"] == "sales")
        self.assertTrue(sales["skipped"], "identical content under a new name must still skip")

    def test_content_that_genuinely_changed_is_not_skipped(self):
        project, workspace = self.workspace_with(sales_rows(amount=200.0), self.keep_files)
        config = config_module.load(project)
        first = pipeline.run(config, workspace)
        self.assertEqual(first.status, "PASS", first.message)

        write_sheet(os.path.join(workspace.inbox, "sales_2026.xlsx"), SALES_HEAD,
                   sales_rows(invoice="INV-2", amount=300.0), "Sales")
        second = pipeline.run(config, workspace)

        sales = next(s for s in second.sources if s["source_id"] == "sales")
        self.assertFalse(sales["skipped"])
        self.assertEqual(sales["new_records"], 1)

    def test_reprocess_identical_opts_a_source_out_of_skipping(self):
        def with_reprocess(data):
            data["inbox"] = {"after_run": "keep", "reprocess_identical": True}

        project, workspace = self.workspace_with(sales_rows(), with_reprocess)
        config = config_module.load(project)
        pipeline.run(config, workspace)
        second = pipeline.run(config, workspace)
        sales = next(s for s in second.sources if s["source_id"] == "sales")
        self.assertFalse(sales["skipped"])


class InboxLifecycleTest(unittest.TestCase):
    """What happens to the file itself after a successful run."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def run_with_policy(self, after_run):
        def set_policy(data):
            data["inbox"] = {"after_run": after_run}

        import shutil
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        edit_config(project, set_policy)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_2026.xlsx"), SALES_HEAD,
                   sales_rows(), "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                   CUSTOMERS, "Customers")
        config = config_module.load(project)
        result = pipeline.run(config, workspace)
        self.assertEqual(result.status, "PASS", result.message)
        return workspace

    def test_archive_moves_the_file_out_of_the_inbox(self):
        workspace = self.run_with_policy("archive")
        self.assertFalse(os.path.exists(os.path.join(workspace.inbox, "sales_2026.xlsx")))
        month = _dt.datetime.now().strftime("%Y-%m")
        archived = os.path.join(workspace.processed_archive("Processed"), month, "sales_2026.xlsx")
        self.assertTrue(os.path.isfile(archived))

    def test_keep_leaves_the_file_in_place(self):
        workspace = self.run_with_policy("keep")
        self.assertTrue(os.path.isfile(os.path.join(workspace.inbox, "sales_2026.xlsx")))

    def test_delete_removes_the_file(self):
        workspace = self.run_with_policy("delete")
        self.assertFalse(os.path.exists(os.path.join(workspace.inbox, "sales_2026.xlsx")))
        month = _dt.datetime.now().strftime("%Y-%m")
        self.assertFalse(os.path.isfile(
            os.path.join(workspace.processed_archive("Processed"), month, "sales_2026.xlsx")))

    def test_a_failed_run_leaves_every_file_exactly_where_it_was(self):
        import shutil
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        # Missing the required Amount column -> BLOCK.
        write_sheet(os.path.join(workspace.inbox, "sales_2026.xlsx"),
                   [h for h in SALES_HEAD if h != "Amount"],
                   [[r for r, h in zip(row, SALES_HEAD) if h != "Amount"]
                    for row in sales_rows()], "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                   CUSTOMERS, "Customers")
        config = config_module.load(project)
        result = pipeline.run(config, workspace)

        self.assertEqual(result.status, "BLOCK")
        self.assertTrue(os.path.isfile(os.path.join(workspace.inbox, "sales_2026.xlsx")))
        self.assertTrue(os.path.isfile(os.path.join(workspace.inbox, "customers.xlsx")))


class ArchiveHelperTest(unittest.TestCase):
    """archive.archive_inbox_file / prune_processed_archive at the unit level."""

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def workspace(self):
        root = temp_dir(self.cleanup)
        return paths.workspace_for(root, os.path.join(root, "_work"))

    def test_a_name_collision_is_resolved_not_overwritten(self):
        workspace = self.workspace()
        moment = _dt.datetime(2026, 3, 15, 9, 30, 0)
        first = os.path.join(temp_dir(self.cleanup), "sales.xlsx")
        second = os.path.join(temp_dir(self.cleanup), "sales.xlsx")
        with open(first, "w") as h:
            h.write("first")
        with open(second, "w") as h:
            h.write("second")

        target1 = archive.archive_inbox_file(workspace, "Processed", first, "sales.xlsx", moment)
        target2 = archive.archive_inbox_file(workspace, "Processed", second, "sales.xlsx",
                                             _dt.datetime(2026, 3, 15, 14, 0, 0))
        self.assertNotEqual(target1, target2)
        self.assertTrue(os.path.isfile(target1))
        self.assertTrue(os.path.isfile(target2))
        with open(target1) as h:
            self.assertEqual(h.read(), "first")
        with open(target2) as h:
            self.assertEqual(h.read(), "second")

    def test_files_are_organised_by_month(self):
        workspace = self.workspace()
        source = os.path.join(temp_dir(self.cleanup), "sales.xlsx")
        with open(source, "w") as h:
            h.write("x")
        target = archive.archive_inbox_file(workspace, "Processed", source, "sales.xlsx",
                                            _dt.datetime(2026, 7, 4))
        self.assertIn(os.path.join("Processed", "2026-07"), target)

    def test_prune_removes_only_files_older_than_the_cutoff(self):
        workspace = self.workspace()
        month_dir = os.path.join(workspace.processed_archive("Processed"), "2020-01")
        os.makedirs(month_dir, exist_ok=True)
        old = os.path.join(month_dir, "old.xlsx")
        new = os.path.join(month_dir, "new.xlsx")
        with open(old, "w") as h:
            h.write("x")
        with open(new, "w") as h:
            h.write("x")
        old_time = _dt.datetime.now().timestamp() - 200 * 86400
        os.utime(old, (old_time, old_time))

        removed = archive.prune_processed_archive(workspace, "Processed", keep_days=90)
        self.assertEqual(removed, [old])
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))

    def test_zero_keep_days_means_keep_forever(self):
        workspace = self.workspace()
        month_dir = os.path.join(workspace.processed_archive("Processed"), "2020-01")
        os.makedirs(month_dir, exist_ok=True)
        old = os.path.join(month_dir, "ancient.xlsx")
        with open(old, "w") as h:
            h.write("x")
        old_time = _dt.datetime.now().timestamp() - 5000 * 86400
        os.utime(old, (old_time, old_time))

        removed = archive.prune_processed_archive(workspace, "Processed", keep_days=0)
        self.assertEqual(removed, [])
        self.assertTrue(os.path.exists(old))


class SnapshotSafetyTest(unittest.TestCase):
    """The bug found while building this feature, not before it.

    Naively running a SNAPSHOT source with zero staged rows on a "nothing new"
    day is not a harmless no-op: history.apply's SNAPSHOT branch closes every
    record the current run_id did not touch, so an empty run reads as "every
    record just disappeared" and closes the entire trusted table. The fix is
    that a source with nothing new is skipped entirely - staging, clean and
    history are simply never called for it - which these tests verify from
    the outside, through a real run, not by re-deriving the reasoning.
    """

    def setUp(self):
        self.cleanup: list[str] = []

    def tearDown(self):
        remove_all(self.cleanup)

    def snapshot_project(self):
        import shutil
        project = project_copy(self.cleanup)
        shutil.rmtree(os.path.join(project, "fixtures"), ignore_errors=True)

        def make_snapshot(data):
            data["inbox"] = {"after_run": "keep"}
            for source in data["sources"]:
                if source["id"] == "sales":
                    source["update_mode"] = "SNAPSHOT"

        edit_config(project, make_snapshot)
        return project

    def test_a_quiet_day_does_not_close_every_snapshot_record(self):
        project = self.snapshot_project()
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_2026.xlsx"), SALES_HEAD,
                   [sales_rows(invoice="INV-1")[0], sales_rows(invoice="INV-2")[0]], "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                   CUSTOMERS, "Customers")
        config = config_module.load(project)

        first = pipeline.run(config, workspace)
        self.assertEqual(first.status, "PASS", first.message)

        connection = database.connect(workspace.database)
        try:
            active_after_first = connection.execute(
                "SELECT COUNT(*) FROM hist__sales WHERE _status = 'active'").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(active_after_first, 2)

        # No new sales file this run: the same content is still sitting in the
        # inbox (after_run: keep) and is correctly recognised as already
        # processed. Before this fix, calling history.apply with zero staged
        # rows for a SNAPSHOT source here would close both active records.
        second = pipeline.run(config, workspace)
        self.assertEqual(second.status, "PASS", second.message)

        connection = database.connect(workspace.database)
        try:
            active_after_second = connection.execute(
                "SELECT COUNT(*) FROM hist__sales WHERE _status = 'active'").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(active_after_second, 2,
                         "a quiet day must not close every SNAPSHOT record")

    def test_a_genuine_new_snapshot_still_closes_missing_records_correctly(self):
        """The SNAPSHOT contract itself - closing a record genuinely absent
        from a fresh, complete snapshot - must still work; only an *empty*
        run must not trigger it."""

        project = self.snapshot_project()
        root = temp_dir(self.cleanup)
        workspace = paths.workspace_for(root, os.path.join(root, "_work"))
        write_sheet(os.path.join(workspace.inbox, "sales_2026.xlsx"), SALES_HEAD,
                   [sales_rows(invoice="INV-1")[0], sales_rows(invoice="INV-2")[0]], "Sales")
        write_sheet(os.path.join(workspace.inbox, "customers.xlsx"), CUSTOMER_HEAD,
                   CUSTOMERS, "Customers")
        config = config_module.load(project)
        pipeline.run(config, workspace)

        # A genuinely new, complete snapshot that now omits INV-2.
        write_sheet(os.path.join(workspace.inbox, "sales_2026.xlsx"), SALES_HEAD,
                   [sales_rows(invoice="INV-1")[0]], "Sales")
        result = pipeline.run(config, workspace)
        self.assertEqual(result.status, "PASS", result.message)

        connection = database.connect(workspace.database)
        try:
            statuses = {row["_bk"]: row["_status"]
                       for row in connection.execute("SELECT _bk, _status FROM hist__sales")}
        finally:
            connection.close()
        self.assertEqual(statuses["inv-1|1"], "active")
        self.assertEqual(statuses["inv-2|1"], "closed")


if __name__ == "__main__":
    unittest.main()
