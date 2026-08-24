"""Locate the header row, at the unit level.

The regression this exists for: one title banner above the header - "Monthly
Sales Export - Confidential" - hard-blocked the run with 'add the column(s)
[...] or update the source mapping', which meant calling the adaptation
agent back for a change with no business meaning. This is the original P0-3
reproduction from the project review.
"""

from __future__ import annotations

import unittest

from engine import config as config_module
from engine.excel import layout


def source(columns, header_row=1, **overrides):
    payload = {"id": "s", "title": "s", "match": ["*.xlsx"], "header_row": header_row,
              "columns": columns}
    payload.update(overrides)
    return config_module._parse_source(0, payload)


def col(name, field, required=True, **extra):
    payload = {"source": name, "field": field, "type": "text", "required": required}
    payload.update(extra)
    return payload


SALES_COLUMNS = [
    col("Invoice No", "invoice_no"), col("Customer ID", "customer_id"),
    col("Amount", "amount", type="number"),
]


class BannerAboveHeaderTest(unittest.TestCase):
    def test_a_title_banner_above_the_header_is_found_on_row_two(self):
        src = source(SALES_COLUMNS, header_row=1)
        sample = [
            (1, ["Monthly Sales Export - Confidential"]),
            (2, ["Invoice No", "Customer ID", "Amount"]),
            (3, ["INV-1", "C001", "200"]),
        ]
        location = layout.find_header(sample, src, hint=1)
        self.assertEqual(location.row_number, 2)
        self.assertTrue(location.moved)
        self.assertEqual(location.values, ["Invoice No", "Customer ID", "Amount"])

    def test_two_banner_rows_above_the_header_are_both_skipped(self):
        src = source(SALES_COLUMNS, header_row=1)
        sample = [
            (1, ["Confidential"]),
            (2, ["Generated 2026-01-31"]),
            (3, ["Invoice No", "Customer ID", "Amount"]),
            (4, ["INV-1", "C001", "200"]),
        ]
        location = layout.find_header(sample, src, hint=1)
        self.assertEqual(location.row_number, 3)
        self.assertTrue(location.moved)


class HintWinsWhenCompetitiveTest(unittest.TestCase):
    def test_an_unmoved_header_is_used_without_being_flagged(self):
        src = source(SALES_COLUMNS, header_row=1)
        sample = [
            (1, ["Invoice No", "Customer ID", "Amount"]),
            (2, ["INV-1", "C001", "200"]),
        ]
        location = layout.find_header(sample, src, hint=1)
        self.assertEqual(location.row_number, 1)
        self.assertFalse(location.moved)

    def test_the_hint_is_preferred_over_an_equally_good_alternative(self):
        """Only override the operator's own setting when it is actually
        worse, never as routine second-guessing."""

        src = source(SALES_COLUMNS, header_row=1)
        sample = [
            (1, ["Invoice No", "Customer ID", "Amount"]),
            (2, ["Invoice No", "Customer ID", "Amount"]),   # a coincidental repeat
            (3, ["INV-1", "C001", "200"]),
        ]
        location = layout.find_header(sample, src, hint=1)
        self.assertEqual(location.row_number, 1)
        self.assertFalse(location.moved)


class NoGuessWithoutEvidenceTest(unittest.TestCase):
    def test_nothing_matching_any_configured_column_makes_no_guess(self):
        """A file that has genuinely lost its header should fail with a clear
        missing-column error against the hinted row, not a confusing error
        against a wrongly guessed one."""

        src = source(SALES_COLUMNS, header_row=1)
        sample = [(1, ["Unrelated Report"]), (2, ["x", "y", "z"]), (3, ["1", "2", "3"])]
        location = layout.find_header(sample, src, hint=1)
        self.assertEqual(location.row_number, 1)
        self.assertIsNone(location.values)
        self.assertFalse(location.moved)

    def test_an_empty_sample_makes_no_guess(self):
        src = source(SALES_COLUMNS, header_row=1)
        location = layout.find_header([], src, hint=1)
        self.assertEqual(location.row_number, 1)
        self.assertFalse(location.moved)


class SearchWindowTest(unittest.TestCase):
    def test_a_header_beyond_the_search_window_is_not_found(self):
        src = source(SALES_COLUMNS, header_row=1)
        sample = [(i, [f"note {i}"]) for i in range(1, 30)]
        sample.append((30, ["Invoice No", "Customer ID", "Amount"]))
        location = layout.find_header(sample, src, hint=1, search_rows=25)
        self.assertIsNone(location.values)

    def test_a_wider_search_window_finds_it(self):
        src = source(SALES_COLUMNS, header_row=1, header_search_rows=40)
        sample = [(i, [f"note {i}"]) for i in range(1, 30)]
        sample.append((30, ["Invoice No", "Customer ID", "Amount"]))
        location = layout.find_header(sample, src, hint=1, search_rows=40)
        self.assertEqual(location.row_number, 30)


class SectionAndBlankRowTest(unittest.TestCase):
    def test_a_single_populated_cell_row_scores_below_a_real_header(self):
        src = source(SALES_COLUMNS, header_row=1)
        sample = [
            (1, ["North region"]),
            (2, ["Invoice No", "Customer ID", "Amount"]),
            (3, ["INV-1", "C001", "200"]),
        ]
        location = layout.find_header(sample, src, hint=1)
        self.assertEqual(location.row_number, 2)


if __name__ == "__main__":
    unittest.main()
