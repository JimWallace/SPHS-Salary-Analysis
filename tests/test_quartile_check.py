"""Unit tests for the quartile disclosure check. Run: python3 -m unittest discover -s tests"""

import statistics
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_promotion_pool import quartile_check  # noqa: E402


class QuartileCheckTests(unittest.TestCase):
    def test_matches_inclusive_quantiles(self):
        values = [float(v) for v in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 125, 140, 160)]
        expected = statistics.quantiles(values, n=4, method="inclusive")
        check = quartile_check(values)
        self.assertAlmostEqual(check["Q1"][1], expected[0])
        self.assertAlmostEqual(check["median"][1], expected[1])
        self.assertAlmostEqual(check["Q3"][1], expected[2])

    def test_odd_n_median_is_one_person(self):
        check = quartile_check([float(v) for v in range(1, 12)])  # n = 11
        self.assertEqual(check["median"][0], 6)
        self.assertFalse(check["median"][2])
        self.assertTrue(check["Q1"][2])
        self.assertTrue(check["Q3"][2])

    def test_equal_neighbours_are_not_shown(self):
        check = quartile_check([1.0, 2.0, 2.0, 4.0, 5.0, 6.0])  # Q1 at position 2.25, between 2 and 2
        self.assertFalse(check["Q1"][2])


if __name__ == "__main__":
    unittest.main()
