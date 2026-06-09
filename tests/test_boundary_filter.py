import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from wrf_eval.pipeline import filter_points_by_boundary


class BoundaryFilterTests(unittest.TestCase):
    def test_filter_points_by_boundary_filters_unique_stations_then_preserves_rows(self):
        frame = pd.DataFrame(
            [
                {"station_id": "in", "lat": 0.5, "lon": 0.5, "date": "2020-05-02"},
                {"station_id": "in", "lat": 0.5, "lon": 0.5, "date": "2020-05-03"},
                {"station_id": "out", "lat": 2.0, "lon": 2.0, "date": "2020-05-02"},
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "boundary.geojson"
            gpd.GeoDataFrame({"id": [1]}, geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])], crs="EPSG:4326").to_file(path)

            filtered = filter_points_by_boundary(frame, path)

        self.assertEqual(filtered["station_id"].tolist(), ["in", "in"])


if __name__ == "__main__":
    unittest.main()
