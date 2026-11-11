"""Checks for the pre-registered held-out scoring; synthetic text only."""

import unittest

import heldout_score as h


class HeldoutScoreTests(unittest.TestCase):
    def test_exact_match_scores_zero(self):
        s = h.score_line("עַל־שְׁבֻעַת", "עַל־שְׁבֻעַת")
        self.assertEqual((s["base_edits"], s["missing_marks"], s["inserted_marks"]), (0, 0, 0))
        self.assertEqual(s["reference_marks"], 5)  # patach, sheva, shin dot, qubbuts, patach

    def test_mark_substitution_counts_one_missing_and_one_inserted(self):
        s = h.score_line("שְׁבֻעַת", "שְׁבֶעַת")  # qubbuts read as segol
        self.assertEqual((s["base_edits"], s["missing_marks"], s["inserted_marks"]), (0, 1, 1))

    def test_base_errors_and_marks_on_unaligned_letters(self):
        s = h.score_line("בָּא", "בָּ")
        self.assertEqual(s["base_edits"], 1)
        self.assertEqual(s["missing_marks"], 0)
        s = h.score_line("בָּא", "בָּאת")
        self.assertEqual(s["base_edits"], 1)

    def test_mark_order_and_composition_do_not_matter(self):
        self.assertEqual(h.score_line("ἔστω", "ἔστω")["missing_marks"], 0)
        self.assertEqual(h.score_line("ἔστω", "ἔστω")["missing_marks"], 0)

    def test_apostrophe_forms_fold_and_whitespace_collapses(self):
        s = h.score_line("καθʼ ὑπερβολὴν", "καθ’  ὑπερβολὴν ")
        self.assertEqual(s["base_edits"], 0)
        self.assertEqual(h.score_line("a'", "a’")["base_edits"], 0)

    def test_divine_name_marks_are_violations_only_when_reference_is_unpointed(self):
        self.assertEqual(h.score_line("דְבַר־יהוה", "דְבַר־יְהוָה")["divine_violations"], 1)
        self.assertEqual(h.score_line("דְבַר־יהוה", "דְבַר־יהוה")["divine_violations"], 0)
        self.assertEqual(h.score_line("יְהוָה", "יְהוָה")["divine_violations"], 0)

    def test_pool_thresholds_and_incomplete_lines(self):
        lines = [{"reference": "αβγ", "candidate": "αβγ"}] * 49 + [{"reference": "αβγ", "candidate": None}]
        m = h.pool(lines)
        self.assertEqual(m["completion"], 0.98)
        self.assertEqual(m["base_error"], 0.0)
        self.assertTrue(m["passes"])
        m = h.pool(lines[:48] + [{"reference": "αβγ", "candidate": None}] * 2)
        self.assertFalse(m["passes"])
        m = h.pool([{"reference": "a" * 99, "candidate": "a" * 98 + "b"}])
        self.assertAlmostEqual(m["base_error"], 1 / 99)
        self.assertFalse(m["passes"])


if __name__ == "__main__":
    unittest.main()
