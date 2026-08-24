"""Quality rules operate on rows directly, so their edge behaviour is tested there.

The regression here: a ``unique`` check fetched every row of a duplicate group and
rejected all of them, so two rows sharing a value removed both - including the
legitimate first occurrence.
"""

from __future__ import annotations

import os
import unittest

from engine import config as config_module
from engine.data import clean
from engine.data.staging import LINEAGE_COLUMNS, stage_table
from engine.db import database
from tests.helpers import remove_all, temp_dir


def source_with(check: dict) -> config_module.Source:
    return config_module._parse_source(0, {
        "id": "people",
        "title": "People",
        "match": ["*.xlsx"],
        "business_key": ["ref"],
        "columns": [
            {"source": "Ref", "field": "ref", "type": "text", "required": True},
            {"source": "Email", "field": "email", "type": "text"},
            {"source": "Amount", "field": "amount", "type": "number"},
        ],
        "checks": [check],
    })


class UniqueCheckTest(unittest.TestCase):
    def setUp(self):
        self.cleanup: list[str] = []
        self.connection = database.connect(
            os.path.join(temp_dir(self.cleanup), "warehouse.db"), backend="sqlite")
        database.migrate(self.connection)

    def tearDown(self):
        self.connection.close()
        remove_all(self.cleanup)

    def stage(self, source, rows):
        """Write rows straight into the staging table this source would produce."""

        table = stage_table(source.id)
        database.create_table(self.connection, table,
                              LINEAGE_COLUMNS + [(c.field, "TEXT") for c in source.columns])
        columns = [c[0] for c in LINEAGE_COLUMNS] + [c.field for c in source.columns]
        database.insert_many(self.connection, table, columns, [
            ["run", "people.xlsx", "hash", row_no, *values] for row_no, values in rows])

    def quarantine(self):
        return self.connection.execute(
            "SELECT excel_row, rule, message FROM quarantine ORDER BY excel_row").fetchall()

    def surviving(self, source):
        return [row["_row_no"] for row in self.connection.execute(
            f"SELECT _row_no FROM {database.quote(clean.clean_table(source.id))}"
            " ORDER BY _row_no")]

    def test_duplicate_group_keeps_its_first_row(self):
        source = source_with({"type": "unique", "fields": ["email"], "on_fail": "quarantine"})
        self.stage(source, [
            (2, ["R1", "a@example.com", "100"]),
            (3, ["R2", "a@example.com", "200"]),
            (4, ["R3", "b@example.com", "300"]),
        ])
        result = clean.clean(self.connection, "run", source)

        self.assertEqual(self.surviving(source), [2, 4])
        self.assertEqual(result.rows_clean, 2)
        self.assertEqual(result.rows_rejected, 1)
        rejected = self.quarantine()
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["excel_row"], 3)
        self.assertIn("row 2", rejected[0]["message"])
        self.assertIn("which was kept", rejected[0]["message"])

    def test_three_way_duplicate_keeps_only_the_first(self):
        source = source_with({"type": "unique", "fields": ["email"], "on_fail": "quarantine"})
        self.stage(source, [
            (5, ["R1", "same@example.com", "100"]),
            (6, ["R2", "same@example.com", "200"]),
            (7, ["R3", "same@example.com", "300"]),
        ])
        clean.clean(self.connection, "run", source)

        self.assertEqual(self.surviving(source), [5])
        self.assertEqual([row["excel_row"] for row in self.quarantine()], [6, 7])

    def test_unique_values_are_untouched(self):
        source = source_with({"type": "unique", "fields": ["email"], "on_fail": "quarantine"})
        self.stage(source, [
            (2, ["R1", "a@example.com", "100"]),
            (3, ["R2", "b@example.com", "200"]),
        ])
        result = clean.clean(self.connection, "run", source)

        self.assertEqual(self.surviving(source), [2, 3])
        self.assertEqual(result.rows_rejected, 0)
        self.assertEqual(self.quarantine(), [])

    def test_warn_severity_keeps_every_row_visible(self):
        source = source_with({"type": "unique", "fields": ["email"], "on_fail": "warn"})
        self.stage(source, [
            (2, ["R1", "a@example.com", "100"]),
            (3, ["R2", "a@example.com", "200"]),
        ])
        result = clean.clean(self.connection, "run", source)

        # A warning reports the repeat without removing it.
        self.assertEqual(self.surviving(source), [2, 3])
        self.assertEqual(result.rows_rejected, 0)
        self.assertEqual(result.warnings, 1)


if __name__ == "__main__":
    unittest.main()
