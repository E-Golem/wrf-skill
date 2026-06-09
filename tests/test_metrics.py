import math
import unittest

import numpy as np

from wrf_eval.metrics import compute_metrics, score_from_metrics


class MetricTests(unittest.TestCase):
    def test_compute_metrics_ignores_nan_and_returns_core_scores(self):
        observed = np.array([10.0, 12.0, np.nan, 16.0])
        modeled = np.array([11.0, 11.0, 15.0, 18.0])

        metrics = compute_metrics(observed, modeled)

        self.assertEqual(metrics["n"], 3)
        self.assertAlmostEqual(metrics["bias"], 2 / 3)
        self.assertAlmostEqual(metrics["mae"], 4 / 3)
        self.assertAlmostEqual(metrics["rmse"], math.sqrt(2))
        self.assertAlmostEqual(metrics["pcc"], float(np.corrcoef([10, 12, 16], [11, 11, 18])[0, 1]))
        self.assertAlmostEqual(metrics["rsd"], np.std([11, 11, 18], ddof=1) / np.std([10, 12, 16], ddof=1))
        self.assertIn("nse", metrics)

    def test_score_penalizes_large_error_and_rewards_correlation(self):
        good = score_from_metrics({"pcc": 0.9, "rmse": 1.0, "mae": 0.8, "rsd": 1.05}, observed_std=5.0)
        poor = score_from_metrics({"pcc": 0.2, "rmse": 8.0, "mae": 6.0, "rsd": 2.5}, observed_std=5.0)

        self.assertGreater(good, poor)
        self.assertGreaterEqual(good, 0)
        self.assertLessEqual(good, 100)


if __name__ == "__main__":
    unittest.main()
