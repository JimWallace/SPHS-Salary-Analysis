"""Unit tests for scripts/promotion_cohort.py. Run: python3 -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from promotion_cohort import classify_title, name_key, normalize_given, normalize_name_part  # noqa: E402


class ClassifyTitleTests(unittest.TestCase):
    def check(self, title, rank, stream, flags=()):
        result = classify_title(title)
        self.assertEqual((result.rank, result.stream, result.flags), (rank, stream, frozenset(flags)), title)

    def test_regular_ranks(self):
        self.check("Assistant Professor", "Assistant", "research")
        self.check("Associate Professor", "Associate", "research")
        self.check("Professor", "Professor", "research")

    def test_teaching_stream(self):
        self.check("Assistant Professor, Teaching Stream", "Assistant", "teaching")
        self.check("Associate Professor, Teaching Stream", "Associate", "teaching")
        self.check("Professor, Teaching Stream", "Professor", "teaching")

    def test_research_associate_professor_is_not_associate(self):
        self.check("Research Associate Professor", "other", "research", {"nonregular"})

    def test_non_regular_ranks(self):
        self.check("Research Assistant Professor", "other", "research", {"nonregular"})
        self.check("Research Professor", "other", "research", {"nonregular"})
        self.check("Clinical Assistant Professor, Teaching Stream", "other", "teaching", {"nonregular"})
        self.check("Clinical Associate Professor, Teaching Stream", "other", "teaching", {"nonregular"})
        self.check("Adjunct Associate Professor", "other", "research", {"nonregular"})
        self.check("Adjunct Professor", "other", "research", {"nonregular"})

    def test_affiliated_colleges(self):
        self.check("Associate Professor, Renison University College", "Associate", "research", {"college"})
        self.check("Professor, Conrad Grebel University College", "Professor", "research", {"college"})
        self.check("Associate Professor, St. Jerome's University", "Associate", "research", {"college"})
        self.check("Associate Professor, St. Jerome’s University", "Associate", "research", {"college"})
        self.check("Assistant Professor, United College", "Assistant", "research", {"college"})
        self.check("Visiting Associate Professor, United College", "other", "research", {"college", "nonregular"})

    def test_admin_with_rank(self):
        self.check("Academic Dean, Associate Professor", "Associate", "research", {"admin"})
        self.check("Academic Dean, Associate Professor, United College", "Associate", "research", {"admin", "college"})
        self.check("Associate Professor, Chair, Social Development Studies, Renison University College",
                   "Associate", "research", {"admin", "college"})

    def test_admin_without_rank(self):
        self.check("Chair, Department of Kinesiology", "other", "research", {"admin"})
        self.check("Associate Dean, Research, Faculty of Health", "other", "research", {"admin"})
        self.check("Dean, Faculty of Health", "other", "research", {"admin"})
        self.check("Director, School of Public Health Sciences", "other", "research", {"admin"})
        self.check("Associate Vice-President, Academic", "other", "research", {"admin"})
        self.check("AVP, Graduate Studies", "other", "research", {"admin"})

    def test_non_academic(self):
        self.check("Continuing Lecturer", "other", "research")
        self.check("Senior Fabrication Equipment Technician", "other", "research")


class NameNormalizationTests(unittest.TestCase):
    def test_upper_case_and_accents(self):
        self.assertEqual(normalize_name_part("Élodie"), "ELODIE")
        self.assertEqual(normalize_name_part("Zürn"), "ZURN")

    def test_punctuation(self):
        self.assertEqual(normalize_name_part("D'Arc"), "DARC")
        self.assertEqual(normalize_name_part("Alpha-Beta"), "ALPHA BETA")
        self.assertEqual(normalize_name_part("  van   der Gamma "), "VAN DER GAMMA")

    def test_middle_initials_removed(self):
        self.assertEqual(normalize_given("JAMES R."), "JAMES")
        self.assertEqual(normalize_given("Mary A. B."), "MARY")
        self.assertEqual(normalize_given("ANNE MARIE"), "ANNE MARIE")

    def test_leading_initial_kept(self):
        self.assertEqual(normalize_given("J. Robert"), "J ROBERT")

    def test_initial_without_space(self):
        self.assertEqual(normalize_given("P.Robert"), normalize_given("P. Robert"))

    def test_name_key(self):
        self.assertEqual(name_key("WALLACE", "JAMES R."), ("WALLACE", "JAMES"))
        self.assertEqual(name_key("Wallace", "James"), ("WALLACE", "JAMES"))


if __name__ == "__main__":
    unittest.main()
