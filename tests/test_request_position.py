"""Unit tests for the requested-salary position. Run: python3 -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_promotion_pool import request_position  # noqa: E402


class RequestPositionTests(unittest.TestCase):
    def test_near_within_margin(self):
        self.assertEqual(request_position(192_629.0, 190_123.0), "near")
        self.assertEqual(request_position(185_123.0, 190_123.0), "near")
        self.assertEqual(request_position(195_123.0, 190_123.0), "near")

    def test_below_and_above(self):
        self.assertEqual(request_position(185_000.0, 190_123.0), "below")
        self.assertEqual(request_position(195_200.0, 190_123.0), "above")


if __name__ == "__main__":
    unittest.main()
