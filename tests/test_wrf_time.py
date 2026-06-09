import unittest
from datetime import date, datetime

from wrf_eval.wrf_diag import select_record_dates


class WrfTimeTests(unittest.TestCase):
    def test_rebuilds_daily_dates_and_drops_first_frame(self):
        indices, dates = select_record_dates(
            record_count=5,
            parsed_dates=[None] * 5,
            rebuild_start="2020-05-01",
            time_step_days=1,
            drop_initial_frames=1,
        )

        self.assertEqual(indices, [1, 2, 3, 4])
        self.assertEqual(dates[0], date(2020, 5, 1))
        self.assertEqual(dates[-1], date(2020, 5, 4))

    def test_applies_time_offset_before_taking_date(self):
        indices, dates = select_record_dates(
            record_count=2,
            parsed_dates=[
                datetime(2020, 5, 1, 18, 0, 0),
                datetime(2020, 5, 2, 0, 0, 0),
            ],
            time_offset_hours=8,
        )

        self.assertEqual(indices, [0, 1])
        self.assertEqual(dates, [date(2020, 5, 2), date(2020, 5, 2)])

    def test_drops_first_incomplete_local_day_after_time_offset(self):
        indices, dates = select_record_dates(
            record_count=3,
            parsed_dates=[
                datetime(2020, 5, 1, 0, 0, 0),
                datetime(2020, 5, 2, 0, 0, 0),
                datetime(2020, 5, 3, 0, 0, 0),
            ],
            time_offset_hours=8,
            drop_incomplete_start_day=True,
        )

        self.assertEqual(indices, [1, 2])
        self.assertEqual(dates, [date(2020, 5, 2), date(2020, 5, 3)])

    def test_rebuilt_dates_can_drop_first_incomplete_local_day(self):
        indices, dates = select_record_dates(
            record_count=3,
            parsed_dates=[None] * 3,
            rebuild_start="2020-05-01",
            time_step_days=1,
            time_offset_hours=8,
            drop_incomplete_start_day=True,
        )

        self.assertEqual(indices, [1, 2])
        self.assertEqual(dates, [date(2020, 5, 2), date(2020, 5, 3)])

    def test_applies_twenty_hour_local_day_boundary_after_time_offset(self):
        indices, dates = select_record_dates(
            record_count=3,
            parsed_dates=[
                datetime(2020, 5, 1, 11, 0, 0),  # Beijing 19:00, same station day.
                datetime(2020, 5, 1, 12, 0, 0),  # Beijing 20:00, boundary belongs to same station day.
                datetime(2020, 5, 1, 13, 0, 0),  # Beijing 21:00, next station day.
            ],
            time_offset_hours=8,
            local_day_boundary_hour=20,
        )

        self.assertEqual(indices, [0, 1, 2])
        self.assertEqual(dates, [date(2020, 5, 1), date(2020, 5, 1), date(2020, 5, 2)])

    def test_complete_start_day_matches_twenty_hour_boundary(self):
        indices, dates = select_record_dates(
            record_count=2,
            parsed_dates=[
                datetime(2020, 5, 1, 12, 0, 0),
                datetime(2020, 5, 2, 12, 0, 0),
            ],
            time_offset_hours=8,
            local_day_boundary_hour=20,
            drop_incomplete_start_day=True,
        )

        self.assertEqual(indices, [0, 1])
        self.assertEqual(dates, [date(2020, 5, 1), date(2020, 5, 2)])


if __name__ == "__main__":
    unittest.main()
