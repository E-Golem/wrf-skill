import unittest
from datetime import date

import pandas as pd

from wrf_eval.pipeline import merge_observed_and_sampled


class MatchingTests(unittest.TestCase):
    def test_month_day_matching_pairs_different_years(self):
        observed = pd.DataFrame(
            [
                {"station_id": "001", "date": date(2010, 5, 2), "tmax_obs_c": 20.0},
                {"station_id": "001", "date": date(2010, 5, 3), "tmax_obs_c": 22.0},
            ]
        )
        sampled = pd.DataFrame(
            [
                {"station_id": "001", "date": date(2020, 5, 2), "tmax_wrf_c": 21.0},
                {"station_id": "001", "date": date(2020, 5, 4), "tmax_wrf_c": 23.0},
            ]
        )

        matched = merge_observed_and_sampled(observed, sampled, mode="month_day")

        self.assertEqual(len(matched), 1)
        self.assertEqual(matched.loc[0, "date"], date(2020, 5, 2))
        self.assertEqual(matched.loc[0, "observed_date"], date(2010, 5, 2))


if __name__ == "__main__":
    unittest.main()
