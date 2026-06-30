import unittest

import pandas as pd

from wrf_eval.compare_schemes import add_scheme_parts, rank_schemes


class CompareSchemesTests(unittest.TestCase):
    def test_rank_schemes_selects_highest_score_with_metric_tiebreakers(self):
        frame = pd.DataFrame(
            [
                {"scheme_name": "a", "score": 80.0, "rmse": 3.0, "mae": 2.5, "pcc": 0.8},
                {"scheme_name": "b", "score": 81.0, "rmse": 3.5, "mae": 2.7, "pcc": 0.7},
                {"scheme_name": "c", "score": 80.0, "rmse": 2.8, "mae": 2.2, "pcc": 0.9},
            ]
        )

        ranked = rank_schemes(frame)

        self.assertEqual(ranked.iloc[0]["scheme_name"], "b")
        self.assertEqual(ranked.iloc[1]["scheme_name"], "c")

    def test_add_scheme_parts_parses_longwave_and_shortwave_names(self):
        frame = pd.DataFrame([{"scheme_name": "lw4-sw2", "score": 1.0}])

        parsed = add_scheme_parts(frame)

        self.assertEqual(parsed.iloc[0]["lw_scheme"], "lw4")
        self.assertEqual(parsed.iloc[0]["sw_scheme"], "sw2")


if __name__ == "__main__":
    unittest.main()
