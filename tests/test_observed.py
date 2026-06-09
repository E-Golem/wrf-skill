import unittest
from io import StringIO

import pandas as pd

from wrf_eval.observed import parse_china_daily_temperature_frame


class ObservedTemperatureTests(unittest.TestCase):
    def test_parse_daily_temperature_converts_coordinates_and_tmax_units(self):
        raw = StringIO(
            "\n".join(
                [
                    "50136 5258 12231 4330 2010 5 1 68 192 -57 0 0 0",
                    "50136 5258 12231 4330 2010 5 2 84 32766 21 0 0 0",
                    "57494 3016 11403 230 2010 5 1 225 301 180 0 0 0",
                ]
            )
        )
        frame = pd.read_csv(raw, sep=r"\s+", header=None, engine="python")

        parsed = parse_china_daily_temperature_frame(frame)

        self.assertEqual(list(parsed["station_id"]), ["50136", "57494"])
        self.assertAlmostEqual(parsed.loc[0, "lat"], 52 + 58 / 60)
        self.assertAlmostEqual(parsed.loc[0, "lon"], 122 + 31 / 60)
        self.assertEqual(parsed.loc[0, "date"].isoformat(), "2010-05-01")
        self.assertAlmostEqual(parsed.loc[0, "tmax_obs_c"], 19.2)
        self.assertAlmostEqual(parsed.loc[1, "tmax_obs_c"], 30.1)


if __name__ == "__main__":
    unittest.main()
