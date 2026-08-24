"""The column resolution ladder, at the unit level.

The regression this exists for: any header drift at all - a rename, a moved
column, a translated label - hard-blocked the run with 'add this column or
update the source mapping', which in practice meant calling the adaptation
agent back for a change with no business meaning. The ladder absorbs the
common, low-risk cases (case, punctuation, spacing, digit forms, a unit
suffix, reordered words) and always says how, so nothing is silently guessed.

What it must not do is just as important: a genuinely different name
("Amount" vs "Total Amount") must not auto-match, and two candidates tying at
the same rung must refuse rather than pick one.
"""

from __future__ import annotations

import unittest

from engine import config as config_module
from engine.data import resolve


def source(columns, **overrides):
    payload = {"id": "s", "title": "s", "match": ["*.xlsx"], "columns": columns}
    payload.update(overrides)
    return config_module._parse_source(0, payload)


def col(name, field, required=True, **extra):
    payload = {"source": name, "field": field, "type": "text", "required": required}
    payload.update(extra)
    return payload


class ExactAndAliasTest(unittest.TestCase):
    def test_an_exact_header_resolves_without_being_a_guess(self):
        src = source([col("Amount", "amount")])
        result = resolve.resolve(src, ["Amount"])
        self.assertEqual(result.positions, {"amount": 0})
        self.assertFalse(result.guessed)
        self.assertEqual(result.resolutions[0].rung, resolve.RUNG_EXACT)

    def test_exact_match_is_case_insensitive(self):
        src = source([col("Amount", "amount")])
        result = resolve.resolve(src, ["AMOUNT"])
        self.assertEqual(result.positions, {"amount": 0})

    def test_a_declared_alias_resolves_and_is_not_a_guess(self):
        src = source([col("Amount", "amount", aliases=["Total Amount", "Net Amount"])])
        result = resolve.resolve(src, ["Total Amount"])
        self.assertEqual(result.positions, {"amount": 0})
        self.assertFalse(result.guessed)
        self.assertEqual(result.resolutions[0].rung, resolve.RUNG_ALIAS)

    def test_an_undeclared_semantic_rename_does_not_auto_match(self):
        """'Amount' vs 'Total Amount' could mean something different (tax
        inclusive vs exclusive); guessing here is exactly what the ladder must
        refuse to do without an explicit alias."""

        src = source([col("Amount", "amount")])
        result = resolve.resolve(src, ["Total Amount"])
        self.assertEqual(result.positions, {})
        self.assertEqual(result.missing_required, ["Amount"])


class NormalizedRungTest(unittest.TestCase):
    def test_case_and_punctuation_drift_resolves(self):
        src = source([col("Invoice No.", "invoice_no")])
        result = resolve.resolve(src, ["invoice no"])
        self.assertEqual(result.resolutions[0].rung, resolve.RUNG_NORMALIZED)
        self.assertTrue(result.guessed)

    def test_a_trailing_unit_suffix_resolves(self):
        src = source([col("Amount", "amount")])
        result = resolve.resolve(src, ["Amount (SAR)"])
        self.assertEqual(result.positions, {"amount": 0})
        self.assertEqual(result.resolutions[0].rung, resolve.RUNG_NORMALIZED)

    def test_arabic_digit_forms_fold_together(self):
        src = source([col("Q١", "q1")])
        result = resolve.resolve(src, ["Q1"])
        self.assertEqual(result.positions, {"q1": 0})

    def test_arabic_label_drift_resolves(self):
        src = source([col("الإجمالي", "total")])
        result = resolve.resolve(src, ["الاجمالي"])
        self.assertEqual(result.positions, {"total": 0})


class FuzzyRungTest(unittest.TestCase):
    def test_reordered_words_resolve(self):
        src = source([col("Invoice No", "invoice_no")])
        result = resolve.resolve(src, ["No Invoice"])
        self.assertEqual(result.resolutions[0].rung, resolve.RUNG_FUZZY)
        self.assertGreaterEqual(result.resolutions[0].score, resolve.FUZZY_THRESHOLD)

    def test_a_dropped_character_resolves(self):
        src = source([col("Customer ID", "customer_id")])
        result = resolve.resolve(src, ["Custmer ID"])
        self.assertEqual(result.resolutions[0].rung, resolve.RUNG_FUZZY)

    def test_a_different_word_does_not_reach_the_threshold(self):
        src = source([col("No", "no")])
        result = resolve.resolve(src, ["Number"])
        self.assertEqual(result.positions, {})

    def test_fuzzy_prefers_alias_names_too(self):
        src = source([col("Amount", "amount", aliases=["Reference Value"])])
        result = resolve.resolve(src, ["Reference Valeu"])
        self.assertEqual(result.positions, {"amount": 0})
        self.assertEqual(result.resolutions[0].rung, resolve.RUNG_FUZZY)


class PositionalRungTest(unittest.TestCase):
    def test_positional_is_off_by_default(self):
        src = source([col("A", "a"), col("B", "b")])
        result = resolve.resolve(src, ["A", "Renamed Column"])
        self.assertEqual(result.positions, {"a": 0})
        self.assertEqual(result.missing_required, ["B"])

    def test_positional_resolves_when_the_source_declares_stable_order(self):
        src = source([col("A", "a"), col("B", "b")], column_order="stable")
        result = resolve.resolve(src, ["A", "Renamed Column"])
        self.assertEqual(result.positions, {"a": 0, "b": 1})
        self.assertEqual(result.resolutions[1].rung, resolve.RUNG_POSITIONAL)
        self.assertTrue(result.guessed)

    def test_positional_never_applies_to_a_business_key(self):
        src = source([col("A", "a"), col("B", "b")],
                     business_key=["b"], column_order="stable")
        result = resolve.resolve(src, ["A", "Renamed Column"])
        self.assertNotIn("b", result.positions)
        self.assertEqual(result.missing_required, ["B"])

    def test_positional_never_applies_to_a_control_total_field(self):
        src = source(
            [col("A", "a", type="text"),
             col("B", "b", type="number")],
            control_totals=[{"field": "b", "precision": 2}], column_order="stable")
        result = resolve.resolve(src, ["A", "Renamed Column"])
        self.assertNotIn("b", result.positions)


class AmbiguityTest(unittest.TestCase):
    def test_two_headers_exactly_matching_one_column_is_ambiguous(self):
        src = source([col("Amount", "amount")])
        result = resolve.resolve(src, ["Amount", "Amount"])
        self.assertEqual(result.positions, {})
        self.assertEqual(len(result.ambiguous), 1)
        self.assertEqual(result.ambiguous[0].rung, resolve.RUNG_EXACT)

    def test_an_exact_match_for_one_column_is_never_stolen_by_a_fuzzy_guess_for_another(self):
        """A stricter rung always wins for every column at once, so a rung-1
        match for column B can't be claimed by a rung-4 guess for column A
        processed first."""

        src = source([col("No", "reference"), col("Reference No", "ref_no")])
        result = resolve.resolve(src, ["Reference No", "No"])
        self.assertEqual(result.positions["reference"], 1)
        self.assertEqual(result.positions["ref_no"], 0)
        self.assertEqual(result.resolutions[0].rung, resolve.RUNG_EXACT)


    def test_a_genuine_fuzzy_tie_is_ambiguous_not_arbitrarily_picked(self):
        src = source([col("Reference Value", "amount")])
        result = resolve.resolve(src, ["Reference Valeu", "Reference Valeu"])
        self.assertEqual(result.positions, {})
        self.assertEqual(len(result.ambiguous), 1)
        self.assertEqual(result.ambiguous[0].rung, resolve.RUNG_FUZZY)

    def test_an_ambiguous_column_is_not_reattempted_at_a_weaker_rung(self):
        """Two headers tying at 'exact' must not then be resolved by the
        normalized or fuzzy rung just because they also match there."""

        src = source([col("Amount", "amount")])
        result = resolve.resolve(src, ["Amount", "AMOUNT"])
        self.assertEqual(result.positions, {})
        self.assertEqual(len(result.ambiguous), 1)
        self.assertEqual(result.ambiguous[0].rung, resolve.RUNG_EXACT)


class MissingColumnTest(unittest.TestCase):
    def test_required_and_optional_columns_are_reported_separately(self):
        src = source([col("A", "a", required=True), col("B", "b", required=False)])
        result = resolve.resolve(src, [])
        self.assertEqual(result.missing_required, ["A"])
        self.assertEqual(result.missing_optional, ["B"])

    def test_describe_names_the_rung_for_a_guessed_column(self):
        src = source([col("Invoice No", "invoice_no")])
        result = resolve.resolve(src, ["No Invoice"])
        text = result.resolutions[0].describe()
        self.assertIn("Invoice No", text)
        self.assertIn("No Invoice", text)


class MockObjectCompatibilityTest(unittest.TestCase):
    """staging._map_headers is called directly, with bare mock objects, by an
    existing test - resolve() must not assume every config attribute exists."""

    def test_resolve_accepts_a_bare_object_with_only_the_essentials(self):
        class Col:
            def __init__(self, source, field, required=True):
                self.source, self.field, self.required = source, field, required

        class Src:
            id = "x"
            columns = [Col("Amount", "amount")]

        result = resolve.resolve(Src(), ["Amount"])
        self.assertEqual(result.positions, {"amount": 0})


if __name__ == "__main__":
    unittest.main()
