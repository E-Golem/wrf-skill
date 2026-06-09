from __future__ import annotations

import numpy as np


def nearest_grid_indices(lat2d, lon2d, station_lat: float, station_lon: float) -> tuple[int, int]:
    """Return nearest grid indices on a two-dimensional curvilinear WRF grid."""
    lat = np.asarray(lat2d, dtype=float)
    lon = np.asarray(lon2d, dtype=float)
    if lat.shape != lon.shape or lat.ndim != 2:
        raise ValueError("lat2d and lon2d must be two-dimensional arrays with the same shape.")
    distance2 = (lat - station_lat) ** 2 + (lon - station_lon) ** 2
    flat_index = int(np.nanargmin(distance2))
    iy, ix = np.unravel_index(flat_index, lat.shape)
    return int(iy), int(ix)


def sample_grid_values(values, lat2d, lon2d, station_lat: float, station_lon: float) -> np.ndarray:
    """Sample a time, y, x array at the nearest grid cell to a station."""
    array = np.asarray(values, dtype=float)
    if array.ndim != 3:
        raise ValueError("values must have dimensions time, y, x.")
    iy, ix = nearest_grid_indices(lat2d, lon2d, station_lat, station_lon)
    return array[:, iy, ix]
