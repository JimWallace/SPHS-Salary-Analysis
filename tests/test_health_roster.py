"""Unit tests for Faculty of Health roster parsing and matching. Run: python3 -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_health_roster import parse_names  # noqa: E402
from build_promotion_pool import roster_match  # noqa: E402
from promotion_cohort import Record, classify_title, normalize_name_part  # noqa: E402


def record(surname, given):
    return Record(surname, given, "Professor", 100_000.0, classify_title("Professor"))


def roster(*names):
    return [normalize_name_part(name).split() for name in names]


class ParseNamesTests(unittest.TestCase):
    def test_both_profile_link_forms(self):
        page = (
            '<a href="/unit/profiles/alpha-beta" aria-label="Alpha Beta"><img></a>'
            '<a href="/unit/people-profiles/gamma-delta" aria-label="Gamma D. Delta"><img></a>'
            '<a href="/unit/news/item" aria-label="Not A Person"></a>'
        )
        self.assertEqual(parse_names(page), ["Alpha Beta", "Gamma D. Delta"])

    def test_duplicates_and_entities(self):
        page = (
            '<a href="/u/profiles/x" aria-label="Zeta  O&#039;Eta"></a>'
            '<a href="/u/profiles/x" aria-label="Zeta O&#039;Eta"></a>'
        )
        self.assertEqual(parse_names(page), ["Zeta O'Eta"])


class RosterMatchTests(unittest.TestCase):
    def test_surname_and_first_given_name(self):
        self.assertEqual(roster_match(record("BETA", "ALPHA Q."), roster("Alpha Q. Beta")), "yes")

    def test_compound_surname(self):
        self.assertEqual(roster_match(record("BETA-GAMMA", "ALPHA"), roster("Alpha Beta-Gamma")), "yes")

    def test_surname_only_is_not_a_match(self):
        self.assertEqual(roster_match(record("BETA", "OMEGA"), roster("Alpha Beta")), "surname")

    def test_no_match(self):
        self.assertEqual(roster_match(record("DELTA", "ALPHA"), roster("Alpha Beta")), "")


if __name__ == "__main__":
    unittest.main()
