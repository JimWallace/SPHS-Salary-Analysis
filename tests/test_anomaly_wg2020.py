import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import anomaly_wg2020_self as wg  # noqa: E402


class WorkingGroupEquation(unittest.TestCase):
    def setUp(self):
        self.c = wg.load_coefs()

    def test_worked_example(self):
        self.assertAlmostEqual(wg.worked_example(self.c), 138182.10, places=1)

    def test_health_is_reference(self):
        # Synthetic record, not anyone's data: Health adds no group or interaction term.
        ts = wg.terms(self.c, r_avg=1.0, opa=0, hire_year=2010, degree_year=2008, degree="Doctoral",
                      rank="Associate", rank_at_hire="Assistant", group="Health")
        self.assertFalse(any("Academic group" in t for t, _, _ in ts))

    def test_r_thresholds_are_consistent(self):
        # At the R where fitted equals actual, the gap is zero; the flag threshold is higher.
        ts = wg.terms(self.c, r_avg=0.0, opa=1, hire_year=2012, degree_year=2009, degree="Doctoral",
                      rank="Professor", rank_at_hire="Associate", group="Math")
        base = wg.fitted(ts)
        actual = 150000.0
        r_eq = (actual - base) / self.c["R-score avg"]
        r_flag = (max(actual + 5000, actual / 0.9) - base) / self.c["R-score avg"]
        self.assertGreater(r_flag, r_eq)


if __name__ == "__main__":
    unittest.main()
