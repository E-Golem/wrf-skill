import unittest
from datetime import datetime, date, timedelta

import numpy as np

from wrf_eval.wrf_hourly import (
    _calculate_rh_pct,
    _parse_ymd_fraction_time,
    aggregate_hourly_field,
    aggregate_hourly_temperature,
    aggregate_hourly_tmax,
)


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
            drop_incomplete_start_day=False,
            drop_incomplete_end_day=False,
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

    def test_aggregate_hourly_field_records_excluded_incomplete_days(self):
        times = [datetime(2020, 5, 1) + timedelta(hours=hour) for hour in range(49)]
        values = np.arange(49, dtype=float).reshape(49, 1, 1)

        dates, daily, excluded = aggregate_hourly_field(
            times,
            values,
            aggregation="max",
            time_offset_hours=8,
            local_day_boundary_hour=20,
            drop_incomplete_start_day=True,
            drop_incomplete_end_day=True,
        )

        self.assertEqual(dates, [date(2020, 5, 2)])
        self.assertEqual(daily[:, 0, 0].tolist(), [36.0])
        self.assertEqual(excluded["reason"].tolist(), ["incomplete_day", "incomplete_day"])
        self.assertEqual(excluded["actual_records"].tolist(), [13, 12])
        self.assertEqual(excluded["expected_records"].tolist(), [24, 24])

    def test_aggregates_hourly_t2_to_station_day_mean(self):
        times = [
            datetime(2020, 5, 1, 11, 0, 0),  # Beijing 19:00, station day May 1.
            datetime(2020, 5, 1, 12, 0, 0),  # Beijing 20:00, station day May 1.
            datetime(2020, 5, 1, 13, 0, 0),  # Beijing 21:00, station day May 2.
            datetime(2020, 5, 2, 12, 0, 0),  # Beijing 20:00, station day May 2.
        ]
        values = np.asarray([280.0, 282.0, 285.0, 287.0]).reshape(4, 1, 1)

        dates, tmean = aggregate_hourly_temperature(
            times,
            values,
            time_offset_hours=8,
            local_day_boundary_hour=20,
            aggregation="mean",
            drop_incomplete_start_day=False,
            drop_incomplete_end_day=False,
        )

        self.assertEqual(dates, [date(2020, 5, 1), date(2020, 5, 2)])
        self.assertEqual(tmean[:, 0, 0].tolist(), [281.0, 286.0])

    def test_parse_ymd_fraction_xtime_values(self):
        parsed = _parse_ymd_fraction_time([20030501.0, 20030501.041666668, 20030501.5, 20031001.0])

        self.assertEqual(parsed[0], datetime(2003, 5, 1, 0, 0))
        self.assertEqual(parsed[1], datetime(2003, 5, 1, 1, 0))
        self.assertEqual(parsed[2], datetime(2003, 5, 1, 12, 0))
        self.assertEqual(parsed[3], datetime(2003, 10, 1, 0, 0))

    def test_calculates_relative_humidity_from_temperature_moisture_and_pressure(self):
        t2_c = np.asarray([[20.0]])
        q2 = np.asarray([[0.0073]])
        psfc = np.asarray([[100000.0]])

        rh = _calculate_rh_pct(t2_c, q2, psfc)

        self.assertAlmostEqual(float(rh[0, 0]), 50.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
