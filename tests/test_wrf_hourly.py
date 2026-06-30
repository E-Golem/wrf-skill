import unittest
from datetime import datetime, date, timedelta

import numpy as np

from wrf_eval.wrf_hourly import _parse_ymd_fraction_time, aggregate_hourly_tmax


class WrfHourlyAggregationTests(unittest.TestCase):
    def test_aggregates_hourly_t2_to_station_day_tmax_with_twenty_hour_boundary(self):
        times = [
            datetime(2020, 5, 1, 11, 0, 0),  # Beijing 19:00, station day May 1.
            datetime(2020, 5, 1, 12, 0, 0),  # Beijing 20:00, station day May 1.
            datetime(2020, 5, 1, 13, 0, 0),  # Beijing 21:00, station day May 2.
            datetime(2020, 5, 2, 12, 0, 0),  # Beijing 20:00, station day May 2.
        ]
        values = np.asarray([280.0, 282.0, 285.0, 284.0]).reshape(4, 1, 1)

        dates, tmax = aggregate_hourly_tmax(
            times,
            values,
            time_offset_hours=8,
            local_day_boundary_hour=20,
        )

        self.assertEqual(dates, [date(2020, 5, 1), date(2020, 5, 2)])
        self.assertEqual(tmax[:, 0, 0].tolist(), [282.0, 285.0])

    def test_can_drop_incomplete_start_and_end_station_days(self):
        times = [datetime(2020, 5, 1) + timedelta(hours=hour) for hour in range(49)]
        values = np.arange(49, dtype=float).reshape(49, 1, 1)

        dates, tmax = aggregate_hourly_tmax(
            times,
            values,
            time_offset_hours=8,
            local_day_boundary_hour=20,
            drop_incomplete_start_day=True,
            drop_incomplete_end_day=True,
        )

        self.assertEqual(dates, [date(2020, 5, 2)])
        self.assertEqual(tmax[:, 0, 0].tolist(), [36.0])

    def test_parse_ymd_fraction_xtime_values(self):
        parsed = _parse_ymd_fraction_time([20030501.0, 20030501.041666668, 20030501.5, 20031001.0])

        self.assertEqual(parsed[0], datetime(2003, 5, 1, 0, 0))
        self.assertEqual(parsed[1], datetime(2003, 5, 1, 1, 0))
        self.assertEqual(parsed[2], datetime(2003, 5, 1, 12, 0))
        self.assertEqual(parsed[3], datetime(2003, 10, 1, 0, 0))


if __name__ == "__main__":
    unittest.main()
