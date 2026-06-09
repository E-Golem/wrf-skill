import unittest

import numpy as np

from wrf_eval.sampling import nearest_grid_indices, sample_grid_values


class SamplingTests(unittest.TestCase):
    def test_nearest_grid_indices_and_sampling_use_two_dimensional_lat_lon(self):
        lat = np.array([[30.0, 30.0], [31.0, 31.0]])
        lon = np.array([[110.0, 111.0], [110.0, 111.0]])
        values = np.array([[[20.0, 21.0], [22.0, 23.0]]])

        iy, ix = nearest_grid_indices(lat, lon, station_lat=30.8, station_lon=110.9)
        sampled = sample_grid_values(values, lat, lon, station_lat=30.8, station_lon=110.9)

        self.assertEqual((iy, ix), (1, 1))
        self.assertEqual(sampled.tolist(), [23.0])


if __name__ == "__main__":
    unittest.main()
