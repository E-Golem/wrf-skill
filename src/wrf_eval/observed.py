from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


CHINA_DAILY_TEM_COLUMNS = [
    "station_id",
    "lat_raw",
    "lon_raw",
    "elevation_raw",
    "year",
    "month",
    "day",
    "tmean_raw",
    "tmax_raw",
    "tmin_raw",
    "tmean_qc",
    "tmax_qc",
    "tmin_qc",
]


def degree_minute_to_decimal(value: int | float) -> float:
    """Convert China station latitude/longitude DDMM or DDDMM values to decimal degrees."""
    if pd.isna(value):
        return np.nan
    raw = int(value)
    degrees = raw // 100
    minutes = raw % 100
    return degrees + minutes / 60.0


def parse_china_daily_temperature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Parse SURF_CLI_CHN_MUL_DAY TEM records into station/date daily maximum temperature."""
    if frame.shape[1] != len(CHINA_DAILY_TEM_COLUMNS):
        raise ValueError(
            f"Expected {len(CHINA_DAILY_TEM_COLUMNS)} columns in China daily TEM data, "
            f"got {frame.shape[1]}."
        )

    data = frame.copy()
    data.columns = CHINA_DAILY_TEM_COLUMNS
    data["station_id"] = data["station_id"].astype(str)
    data["lat"] = data["lat_raw"].map(degree_minute_to_decimal)
    data["lon"] = data["lon_raw"].map(degree_minute_to_decimal)
    data["elevation_m"] = data["elevation_raw"].replace(32766, np.nan) / 10.0
    data["date"] = pd.to_datetime(data[["year", "month", "day"]], errors="coerce").dt.date
    data["tmax_obs_c"] = data["tmax_raw"].where(data["tmax_raw"] < 30000) / 10.0
    data["tmean_obs_c"] = data["tmean_raw"].where(data["tmean_raw"] < 30000) / 10.0
    data["tmin_obs_c"] = data["tmin_raw"].where(data["tmin_raw"] < 30000) / 10.0

    columns = [
        "station_id",
        "date",
        "lat",
        "lon",
        "elevation_m",
        "tmax_obs_c",
        "tmean_obs_c",
        "tmin_obs_c",
        "tmax_qc",
    ]
    parsed = data.loc[:, columns]
    parsed = parsed.dropna(subset=["station_id", "date", "lat", "lon", "tmax_obs_c"])
    return parsed.reset_index(drop=True)


def read_china_daily_temperature(paths: list[Path] | Path) -> pd.DataFrame:
    """Read one or more China daily TEM text files."""
    if isinstance(paths, Path):
        paths = [paths]

    frames = []
    for path in paths:
        raw = pd.read_csv(path, sep=r"\s+", header=None, engine="python")
        parsed = parse_china_daily_temperature_frame(raw)
        parsed["source_file"] = path.name
        frames.append(parsed)

    if not frames:
        return pd.DataFrame(
            columns=[
                "station_id",
                "date",
                "lat",
                "lon",
                "elevation_m",
                "tmax_obs_c",
                "tmean_obs_c",
                "tmin_obs_c",
                "tmax_qc",
                "source_file",
            ]
        )
    return pd.concat(frames, ignore_index=True)
