import unittest

import pandas as pd

from wrf_eval.pipeline import frame_to_markdown_table


class ReportTests(unittest.TestCase):
    def test_frame_to_markdown_table_does_not_require_optional_dependencies(self):
        frame = pd.DataFrame([{"date": "2010-05-02", "n": 2, "rmse": 1.23456}])

        table = frame_to_markdown_table(frame)

        self.assertIn("| date | n | rmse |", table)
        self.assertIn("| 2010-05-02 | 2 | 1.2346 |", table)


if __name__ == "__main__":
    unittest.main()
