"""Tests for confirmatory_cohorts/confirm.py. Synthetic fixtures only.

Run: python3 -m unittest discover -s confirmatory_cohorts/tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from confirm import (  # noqa: E402
    assign_cohorts,
    cohort_members,
    lump_sum_flags,
    ordinal,
    quartiles,
    rank_and_percentile,
    retained,
    scale_factor,
    scale_increases_complete,
    summary_row,
)
from promotion_cohort import Record, classify_title  # noqa: E402


def rec(surname, title, paid=150_000.0, given="ALPHA"):
    return Record(surname, given, title, paid, classify_title(title))


class TitleChangeTests(unittest.TestCase):
    def test_regular_change_is_detected(self):
        members, _ = cohort_members([rec("ONE", "Associate Professor")], [rec("ONE", "Professor")], 2023)
        self.assertEqual([(m.cohort, m.curr.surname) for m in members], [(2023, "ONE")])

    def test_excluded_ranks_and_streams(self):
        prev = [rec("TWO", "Research Associate Professor"),
                rec("THREE", "Associate Professor, Renison University College"),
                rec("FOUR", "Associate Professor, Teaching Stream"),
                rec("FIVE", "Clinical Associate Professor")]
        curr = [rec("TWO", "Research Professor"),
                rec("THREE", "Professor, Renison University College"),
                rec("FOUR", "Professor, Teaching Stream"),
                rec("FIVE", "Professor")]
        members, _ = cohort_members(prev, curr, 2023)
        self.assertEqual(members, [])

    def test_admin_title_goes_to_review_not_cohort(self):
        members, review = cohort_members([rec("SIX", "Associate Professor")],
                                         [rec("SIX", "Associate Dean, Research")], 2023)
        self.assertEqual(members, [])
        self.assertEqual(len(review), 1)
        self.assertIn("admin", review[0]["reason"])

    def test_no_change_is_not_a_member(self):
        members, _ = cohort_members([rec("SEVEN", "Associate Professor")], [rec("SEVEN", "Associate Professor")], 2023)
        self.assertEqual(members, [])


class CohortAssignmentTests(unittest.TestCase):
    def test_three_consecutive_lists(self):
        lists = {
            2021: [rec("EARLY", "Associate Professor"), rec("LATE", "Associate Professor")],
            2022: [rec("EARLY", "Professor"), rec("LATE", "Associate Professor")],
            2023: [rec("EARLY", "Professor"), rec("LATE", "Professor")],
        }
        members, _ = assign_cohorts(lists, (2022, 2023))
        self.assertEqual(sorted((m.curr.surname, m.cohort) for m in members), [("EARLY", 2022), ("LATE", 2023)])


class AttritionTests(unittest.TestCase):
    def setUp(self):
        members, _ = cohort_members([rec("STAY", "Associate Professor"), rec("GONE", "Associate Professor"),
                                     rec("MOVED", "Associate Professor")],
                                    [rec("STAY", "Professor"), rec("GONE", "Professor"), rec("MOVED", "Professor")],
                                    2022)
        self.members = {m.curr.surname: m for m in members}
        self.final = [rec("STAY", "Professor", 170_000.0), rec("MOVED", "Professor, Conrad Grebel University College")]

    def test_still_professor(self):
        self.assertEqual(retained(self.members["STAY"], self.final).paid, 170_000.0)

    def test_not_on_final_list(self):
        self.assertIsNone(retained(self.members["GONE"], self.final))

    def test_no_longer_main_campus_professor(self):
        self.assertIsNone(retained(self.members["MOVED"], self.final))


class QuartileTests(unittest.TestCase):
    def test_matches_r_type_7(self):
        # R: quantile(1:10, c(.25, .5, .75), type = 7) -> 3.25 5.50 7.75
        self.assertEqual(quartiles([float(v) for v in range(1, 11)]), (3.25, 5.5, 7.75))
        # R: quantile(c(10, 20, 40, 80, 160), c(.25, .5, .75), type = 7) -> 20 40 80
        self.assertEqual(quartiles([10.0, 20.0, 40.0, 80.0, 160.0]), (20.0, 40.0, 80.0))


class DisclosureTests(unittest.TestCase):
    def test_whole_position_quartiles_are_withheld(self):
        row = summary_row([float(v) for v in range(1, 6)], 2.0)   # n = 5: every quartile is one person
        self.assertEqual((row["lower_quartile"], row["median"], row["upper_quartile"]), ("withheld",) * 3)
        self.assertEqual(row["my_diff_from_median"], "withheld")
        self.assertEqual(row["my_rank"], 4)                       # rank is still reported

    def test_interpolated_quartiles_are_kept(self):
        row = summary_row([float(v) for v in range(1, 11)], 2.0)   # n = 10: 3.25, 5.5, 7.75
        self.assertEqual(row["median"], 5.5)
        self.assertEqual(row["my_diff_from_lower_quartile"], 2.0 - 3.25)

    def test_ordinal(self):
        self.assertEqual([ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 82, 85, 111)],
                         ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "82nd", "85th", "111th"])


class RankTests(unittest.TestCase):
    def test_rank_and_percentile(self):
        self.assertEqual(rank_and_percentile([10.0, 20.0, 30.0, 40.0, 50.0], 20.0), (4, 25.0))

    def test_ties(self):
        rank, pct = rank_and_percentile([10.0, 20.0, 20.0, 30.0], 20.0)
        self.assertEqual(rank, 2)                 # one higher; the tie does not count as higher
        self.assertAlmostEqual(pct, 100.0 / 3)    # one of three others is strictly lower

    def test_lowest_and_highest(self):
        self.assertEqual(rank_and_percentile([1.0, 2.0, 3.0], 1.0), (3, 0.0))
        self.assertEqual(rank_and_percentile([1.0, 2.0, 3.0], 3.0), (1, 100.0))


class ScaleTests(unittest.TestCase):
    INCREASES = {"2023": 0.02, "2024": 0.03, "2025": 0.01}

    def test_compounding(self):
        self.assertAlmostEqual(scale_factor(2022, self.INCREASES), 1.02 * 1.03 * 1.01)
        self.assertAlmostEqual(scale_factor(2024, self.INCREASES), 1.01)
        self.assertEqual(scale_factor(2025, self.INCREASES), 1.0)

    def test_refuses_empty_values(self):
        empty = {"2023": None, "2024": None, "2025": None}
        with self.assertRaises(ValueError):
            scale_factor(2022, empty)
        self.assertFalse(scale_increases_complete(empty, 2022))
        self.assertTrue(scale_increases_complete(self.INCREASES, 2022))

    def test_missing_key_is_refused(self):
        with self.assertRaises(ValueError):
            scale_factor(2022, {"2024": 0.03, "2025": 0.01})


class LumpSumTests(unittest.TestCase):
    def test_boundary(self):
        history = {2021: 100_000.0, 2022: 115_000.0, 2023: 132_250.01}
        flags = lump_sum_flags(history, promotion_year=2025, threshold=0.15)
        self.assertEqual([year for year, _ in flags], [2023])   # exactly 15% in 2022 is not flagged

    def test_promotion_years_are_explained(self):
        history = {2021: 100_000.0, 2022: 130_000.0, 2023: 160_000.0, 2024: 165_000.0}
        self.assertEqual(lump_sum_flags(history, promotion_year=2022, threshold=0.15), [])

    def test_gap_years_are_skipped(self):
        self.assertEqual(lump_sum_flags({2021: 100_000.0, 2023: 150_000.0}, 2025, 0.15), [])


if __name__ == "__main__":
    unittest.main()
