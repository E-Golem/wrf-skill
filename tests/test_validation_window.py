import unittest
from datetime import date

from wrf_eval.pipeline import date_in_validation_window


class ValidationWindowTests(unittest.TestCase):
    def test_month_day_window_excludes_spinup_month(self):
        self.assertFalse(date_in_validation_window(date(2003, 5, 31), "06-01", "10-01"))
        self.assertTrue(date_in_validation_window(date(2003, 6, 1), "06-01", "10-01"))
        self.assertTrue(date_in_validation_window(date(2003, 10, 1), "06-01", "10-01"))
        self.assertFalse(date_in_validation_window(date(2003, 10, 2), "06-01", "10-01"))


if __name__ == "__main__":
    unittest.main()
