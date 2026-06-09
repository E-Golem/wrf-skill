import unittest
from datetime import date
from pathlib import Path

import numpy as np

from wrf_eval.wrf_diag import WrfTmaxDiagnostic, merge_wrf_tmax_diagnostics


def _diag(source: str, dates, values) -> WrfTmaxDiagnostic:
    lat = np.array([[30.0]])
    lon = np.array([[110.0]])
    return WrfTmaxDiagnostic(
        dates=dates,
        tmax_c=np.asarray(values, dtype=float).reshape(len(dates), 1, 1),
        lat=lat,
        lon=lon,
        source=Path(source),
        variable="T2MAX",
    )


class WrfMergeTests(unittest.TestCase):
    def test_merge_wrf_diagnostics_sorts_by_date_and_keeps_values_aligned(self):
        later = _diag("later", [date(2003, 7, 20)], [32.0])
        earlier = _diag("earlier", [date(2003, 5, 1), date(2003, 5, 2)], [20.0, 21.0])

        merged = merge_wrf_tmax_diagnostics([later, earlier])

        self.assertEqual(merged.dates, [date(2003, 5, 1), date(2003, 5, 2), date(2003, 7, 20)])
        self.assertEqual(merged.tmax_c[:, 0, 0].tolist(), [20.0, 21.0, 32.0])

    def test_merge_wrf_diagnostics_rejects_duplicate_dates(self):
        first = _diag("first", [date(2003, 5, 1)], [20.0])
        second = _diag("second", [date(2003, 5, 1)], [21.0])

        with self.assertRaises(ValueError):
            merge_wrf_tmax_diagnostics([first, second])


if __name__ == "__main__":
    unittest.main()
