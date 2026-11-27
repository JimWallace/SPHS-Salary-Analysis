import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import anomaly_build_inputs as bi  # noqa: E402
import anomaly_health_roster as hr  # noqa: E402


class RankMapping(unittest.TestCase):
    def test_teaching_stream_is_lecturer_category(self):
        self.assertEqual(bi.rank_from_title("Associate Professor, Teaching Stream"), "Lecturer")
        self.assertEqual(bi.norm_rank("Assistant Professor, Teaching Stream"), "Lecturer")

    def test_regular_ranks(self):
        self.assertEqual(bi.rank_from_title("Professor"), "Professor")
        self.assertEqual(bi.rank_from_title("Associate Professor"), "Associate")
        self.assertEqual(bi.norm_rank("Assistant Professor"), "Assistant")
        self.assertEqual(bi.rank_from_title("Lecturer"), "Lecturer")

    def test_admin_only_title_has_no_rank(self):
        self.assertEqual(bi.rank_from_title("Dean, Faculty of Health"), "")
        self.assertEqual(bi.rank_from_title("Research Associate Professor"), "")


class AcademicGroups(unittest.TestCase):
    def test_working_group_special_units(self):
        self.assertEqual(bi.academic_group("Cheriton School of Computer Science (Mathematics)", False)[0], "CSCS")
        self.assertEqual(bi.academic_group("School of Accounting and Finance (Arts)", False)[0], "SAF")
        self.assertEqual(bi.academic_group("Economics (Arts)", False)[0], "Econ")
        self.assertEqual(bi.academic_group("School of Pharmacy (Science)", False)[0], "Pharmacy")
        self.assertEqual(bi.academic_group("Optometry and Vision Science (Science)", False)[0], "SOVS")

    def test_faculty_fallback(self):
        self.assertEqual(bi.academic_group("Chemistry (Science)", False)[0], "Sci")
        self.assertEqual(bi.academic_group("Statistics and Actuarial Science (Mathematics)", False)[0], "Math")
        self.assertEqual(bi.academic_group("Civil and Environmental Engineering (Engineering)", False)[0], "Eng")
        self.assertEqual(bi.academic_group("anything", True)[0], "Health")


class LeaveThreshold(unittest.TestCase):
    def test_scale_only_growth(self):
        # 4 months at the 2024 scale and 8 at the 2025 scale, relative to calendar 2024.
        self.assertAlmostEqual(bi.EXPECTED_SCALE_GROWTH_2025, 1.0396, places=4)


class RosterPositions(unittest.TestCase):
    def test_kept(self):
        for pos in ("Professor", "Associate Professor, Teaching Stream", "Lecturer",
                    "Professor; Chair, Department of Kinesiology and Health Sciences",
                    "Associate Professor, Cross-Appointed to Public Health Sciences"):
            self.assertEqual(hr.classify_position(pos), "", pos)

    def test_dropped(self):
        for pos in ("Adjunct Assistant Professor", "Distinguished Professor Emeritus", "Postdoctoral Fellow",
                    "Professor, School of Pharmacy", "Associate Professor, McMaster University",
                    "Professor of Practice", "Research Associate"):
            self.assertNotEqual(hr.classify_position(pos), "", pos)


if __name__ == "__main__":
    unittest.main()
