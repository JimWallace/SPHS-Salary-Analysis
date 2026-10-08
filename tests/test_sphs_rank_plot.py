"""Unit tests for SPHS rank plot grouping. Run: python3 -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_sphs_rank_plot import rank_group  # noqa: E402
from promotion_cohort import classify_title  # noqa: E402


class RankGroupTests(unittest.TestCase):
    def test_research_ranks(self):
        self.assertEqual(rank_group(classify_title("Professor")), "Professor")
        self.assertEqual(rank_group(classify_title("Associate Professor")), "Associate")
        self.assertEqual(rank_group(classify_title("Assistant Professor")), "Assistant")

    def test_teaching_stream_is_one_group(self):
        self.assertEqual(rank_group(classify_title("Associate Professor, Teaching Stream")), "Teaching")
        self.assertEqual(rank_group(classify_title("Assistant Professor, Teaching Stream")), "Teaching")

    def test_excluded_titles(self):
        self.assertIsNone(rank_group(classify_title("Research Associate Professor")))
        self.assertIsNone(rank_group(classify_title("Associate Professor, Renison University College")))
        self.assertIsNone(rank_group(classify_title("Dean, Faculty of Health")))


if __name__ == "__main__":
    unittest.main()
