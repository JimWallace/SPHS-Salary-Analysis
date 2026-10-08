"""Unit tests for SPHS rank counts. Run: python3 -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_promotion_pool import count_paid_more  # noqa: E402
from promotion_cohort import Record, classify_title  # noqa: E402


def record(title, paid):
    return Record("ALPHA", "BETA", title, paid, classify_title(title))


class CountPaidMoreTests(unittest.TestCase):
    def test_counts_only_the_exact_rank_and_stream(self):
        records = [
            record("Associate Professor", 170_000.0),
            record("Associate Professor", 150_000.0),
            record("Associate Professor, Teaching Stream", 180_000.0),
            record("Research Associate Professor", 190_000.0),
            record("Associate Professor, Renison University College", 190_000.0),
            record("Professor", 200_000.0),
        ]
        self.assertEqual(count_paid_more(records, "Associate", "research", 160_000.0), (2, 1))

    def test_equal_salary_is_not_more(self):
        self.assertEqual(count_paid_more([record("Professor", 160_000.0)], "Professor", "research", 160_000.0), (1, 0))


if __name__ == "__main__":
    unittest.main()
