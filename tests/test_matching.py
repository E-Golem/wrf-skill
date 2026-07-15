import unittest
from datetime import date

import pandas as pd

from wrf_eval.pipeline import merge_observed_and_sampled


class MatchingTests(unittest.TestCase):
    def test_exact_matching_pairs_same_station_and_same_date(self):
        observed = pd.DataFrame(
            [
                {"station_id": "001", "date": date(2020, 6, 2), "tmax_obs_c": 20.0},
                {"station_id": "001", "date": date(2020, 6, 3), "tmax_obs_c": 22.0},
            ]
        )
        sampled = pd.DataFrame(
            [
                {"station_id": "001", "date": date(2020, 6, 2), "tmax_wrf_c": 21.0},
                {"station_id": "001", "date": date(2020, 6, 4), "tmax_wrf_c": 23.0},
            ]
        )

        matched = merge_observed_and_sampled(observed, sampled)

        self.assertEqual(len(matched), 1)
        self.assertEqual(matched.loc[0, "date"], date(2020, 6, 2))
        self.assertEqual(matched.loc[0, "observed_date"], date(2020, 6, 2))

    def test_rejects_month_day_matching_removed_from_v11(self):
        with self.assertRaises(ValueError):
            merge_observed_and_sampled(pd.DataFrame(), pd.DataFrame(), mode="month_day")


if __name__ == "__main__":
    unittest.main()
