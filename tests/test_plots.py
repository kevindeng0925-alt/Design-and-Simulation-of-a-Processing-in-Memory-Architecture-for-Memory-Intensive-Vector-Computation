import math
import unittest

from benchmarks.plot_results import speedup_series


class PlotTests(unittest.TestCase):
    def test_speedup_masks_mock_failed_unavailable_and_zero_denominator(self):
        rows = []
        for bank, (status, mock, cycles) in enumerate([
            ("ok", "false", "10"), ("ok", "true", "10"), ("failed", "false", ""),
            ("unavailable", "", ""), ("ok", "false", "0"),
        ], start=1):
            row = {"op": "DOT", "banks": str(bank), "correct": "true"}
            rows.append(dict(row, requested_mode="cpu", status="ok", is_mock="false", cycles="30"))
            rows.append(dict(row, requested_mode="pim", status=status, is_mock=mock, cycles=cycles))
        points = speedup_series(rows, "DOT", "pim")
        self.assertEqual(points[1], 3)
        self.assertTrue(all(math.isnan(points[bank]) for bank in (2, 3, 4, 5)))


if __name__ == "__main__":
    unittest.main()
