"""Unit tests for the requested-adjustment macros. Run: python3 -m unittest discover -s tests"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_promotion_pool import request_macros  # noqa: E402


class RequestMacrosTests(unittest.TestCase):
    def test_values_are_computed_from_base(self):
        with redirect_stdout(io.StringIO()):
            macros = request_macros(162_628.83, 30_000.0, 189_332.69, 207_957.22)
        self.assertEqual(macros["RequestAdj"], "\\$30{,}000")
        self.assertEqual(macros["RequestTarget"], "\\$192{,}629")
        self.assertEqual(macros["RequestPct"], "18")

    def test_position_is_printed(self):
        out = io.StringIO()
        with redirect_stdout(out):
            request_macros(100_000.0, 10_000.0, 105_000.0, 120_000.0)
        self.assertIn("between lower quartile and median: True", out.getvalue())


if __name__ == "__main__":
    unittest.main()
