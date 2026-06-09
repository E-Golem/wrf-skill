import unittest
from datetime import date

from wrf_eval.wrf_diag import build_effective_dates


class WrfDiagnosticDateTests(unittest.TestCase):
    def test_drop_first_frame_and_rebuild_daily_dates(self):
        raw_dates = [date(2020, 5, 1), date(2020, 5, 2), date(2020, 5, 3), date(2020, 5, 4)]

        dates, indices = build_effective_dates(
            raw_dates,
            frame_count=4,
            drop_initial_frames=1,
            override_start_date=date(2020, 5, 1),
            frequency_days=1,
        )

        self.assertEqual(indices, [1, 2, 3])
        self.assertEqual(dates, [date(2020, 5, 1), date(2020, 5, 2), date(2020, 5, 3)])

    def test_default_keeps_valid_raw_dates_and_indices(self):
        raw_dates = [date(2020, 5, 1), None, date(2020, 5, 3)]

        dates, indices = build_effective_dates(raw_dates, frame_count=3)

        self.assertEqual(indices, [0, 2])
        self.assertEqual(dates, [date(2020, 5, 1), date(2020, 5, 3)])


if __name__ == "__main__":
    unittest.main()
