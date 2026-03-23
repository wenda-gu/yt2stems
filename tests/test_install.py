from __future__ import annotations

import unittest

from yt2stems.benchmark import BenchResult
from yt2stems.install import select_default_model, select_fastest_device


class InstallDecisionTests(unittest.TestCase):
    def test_select_fastest_device_prefers_fastest_ok_result(self) -> None:
        results = [
            BenchResult("OK", "cpu", "htdemucs", 12),
            BenchResult("OK", "mps", "htdemucs", 7),
        ]
        self.assertEqual(select_fastest_device(results), "mps")

    def test_select_default_model_respects_quality_margin(self) -> None:
        results = [
            BenchResult("OK", "cpu", "htdemucs", 10),
            BenchResult("OK", "cpu", "htdemucs_ft", 12),
        ]
        self.assertEqual(
            select_default_model(results, device="cpu", quality_margin_percent=25),
            "htdemucs_ft",
        )
        self.assertEqual(
            select_default_model(results, device="cpu", quality_margin_percent=10),
            "htdemucs",
        )


if __name__ == "__main__":
    unittest.main()
