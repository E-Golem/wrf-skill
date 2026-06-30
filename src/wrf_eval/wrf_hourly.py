from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from netCDF4 import Dataset, chartostring

from wrf_eval.wrf_diag import WrfTmaxDiagnostic, _station_day, discover_wrf_diagnostic_files


@dataclass(frozen=True)
class _HourlyRecord:
    timestamp: pd.Timestamp
    file_path: Path
    frame_index: int


def aggregate_hourly_tmax(
    timestamps: list[datetime | pd.Timestamp],
    values: np.ndarray,
    time_offset_hours: int = 0,
    local_day_boundary_hour: int | None = None,
    drop_incomplete_start_day: bool = False,
    drop_incomplete_end_day: bool = False,
) -> tuple[list, np.ndarray]:
    """Aggregate hourly near-surface temperature fields to station-day Tmax."""
    if values.ndim != 3:
        raise ValueError(f"values must have dimensions time, y, x; got {values.shape}.")
    if len(timestamps) != values.shape[0]:
        raise ValueError("timestamps length must match the first values dimension.")

    records = []
    for idx, timestamp in enumerate(timestamps):
        parsed = pd.to_datetime(timestamp, errors="coerce")
        if pd.isna(parsed):
            continue
        records.append((parsed, idx))
    records.sort(key=lambda item: item[0])
    records = _dedupe_timestamp_records(records)
    keep_dates = _complete_station_days(
        [timestamp for timestamp, _ in records],
        time_offset_hours=time_offset_hours,
        local_day_boundary_hour=local_day_boundary_hour,
        drop_incomplete_start_day=drop_incomplete_start_day,
        drop_incomplete_end_day=drop_incomplete_end_day,
    )

    daily: dict = {}
    for timestamp, idx in records:
        station_date = _station_day(timestamp + pd.Timedelta(hours=time_offset_hours), local_day_boundary_hour)
        if station_date not in keep_dates:
            continue
        field = values[idx]
        if station_date not in daily:
            daily[station_date] = field.astype(float, copy=True)
        else:
            daily[station_date] = np.fmax(daily[station_date], field)

    dates = sorted(daily)
    if not dates:
        raise ValueError("No complete station-day Tmax records were available after hourly aggregation.")
    return dates, np.stack([daily[day] for day in dates], axis=0)


def read_wrf_hourly_t2_as_daily_tmax(
    path: Path,
    variable: str = "T2",
    file_pattern: str | None = None,
    coord_source: Path | None = None,
    time_offset_hours: int = 0,
    local_day_boundary_hour: int | None = None,
    drop_incomplete_start_day: bool = False,
    drop_incomplete_end_day: bool = False,
) -> WrfTmaxDiagnostic:
    """Read hourly WRF T2 outputs and aggregate them to daily maximum temperature."""
    files = discover_wrf_diagnostic_files(path, file_pattern=file_pattern)
    records: dict[pd.Timestamp, _HourlyRecord] = {}
    lat = None
    lon = None

    for file in files:
        with Dataset(file) as ds:
            if variable not in ds.variables:
                available = ", ".join(ds.variables.keys())
                raise KeyError(f"Variable {variable!r} was not found in {file}. Available variables: {available}")
            file_times = _read_time_axis(ds)
            if len(file_times) != ds.variables[variable].shape[0]:
                raise ValueError(f"Time axis length does not match {variable} frames in {file}.")
            file_lat, file_lon = _read_coordinates(ds, coord_source)
            if lat is None:
                lat = file_lat
                lon = file_lon
            elif not np.allclose(lat, file_lat, equal_nan=True) or not np.allclose(lon, file_lon, equal_nan=True):
                raise ValueError("All hourly WRF files must have matching XLAT/XLONG coordinates.")
            for frame_index, timestamp in enumerate(file_times):
                records[timestamp] = _HourlyRecord(timestamp, file, frame_index)

    sorted_records = [records[key] for key in sorted(records)]
    keep_dates = _complete_station_days(
        [record.timestamp for record in sorted_records],
        time_offset_hours=time_offset_hours,
        local_day_boundary_hour=local_day_boundary_hour,
        drop_incomplete_start_day=drop_incomplete_start_day,
        drop_incomplete_end_day=drop_incomplete_end_day,
    )

    daily: dict = {}
    by_file: dict[Path, list[_HourlyRecord]] = defaultdict(list)
    for record in sorted_records:
        station_date = _station_day(record.timestamp + pd.Timedelta(hours=time_offset_hours), local_day_boundary_hour)
        if station_date in keep_dates:
            by_file[record.file_path].append(record)

    for file, file_records in by_file.items():
        with Dataset(file) as ds:
            var = ds.variables[variable]
            units = getattr(var, "units", "")
            for record in file_records:
                station_date = _station_day(record.timestamp + pd.Timedelta(hours=time_offset_hours), local_day_boundary_hour)
                field = np.ma.filled(var[record.frame_index], np.nan).astype(float)
                if units.upper().startswith("K"):
                    field = field - 273.15
                if station_date not in daily:
                    daily[station_date] = field
                else:
                    daily[station_date] = np.fmax(daily[station_date], field)

    dates = sorted(daily)
    if not dates:
        raise ValueError("No hourly T2 records were available after station-day aggregation.")
    return WrfTmaxDiagnostic(
        dates=dates,
        tmax_c=np.stack([daily[day] for day in dates], axis=0),
        lat=lat,
        lon=lon,
        source=path,
        variable=f"{variable}_HOURLY_TMAX",
    )


def _read_time_axis(ds: Dataset) -> list[pd.Timestamp]:
    if "Times" in ds.variables:
        strings = chartostring(ds.variables["Times"][:])
        return [pd.to_datetime(str(value).strip(), format="%Y-%m-%d_%H:%M:%S", errors="raise") for value in strings]
    if "XTIME" not in ds.variables:
        raise KeyError("Hourly WRF file must contain Times or XTIME.")
    xtime = ds.variables["XTIME"]
    units = getattr(xtime, "units", "")
    units_key = units.strip().lower()
    if units_key == "day as %y%m%d.%f":
        return _parse_ymd_fraction_time(np.asarray(xtime[:], dtype=float))
    if " since " not in units:
        raise ValueError(f"Unsupported XTIME units: {units!r}")
    unit_name, origin = units.split(" since ", 1)
    unit_name = unit_name.strip().lower()
    origin_time = pd.to_datetime(origin.strip(), errors="raise")
    if unit_name.startswith("minute"):
        unit = "minutes"
    elif unit_name.startswith("hour"):
        unit = "hours"
    elif unit_name.startswith("second"):
        unit = "seconds"
    else:
        raise ValueError(f"Unsupported XTIME unit: {unit_name!r}")
    return [origin_time + pd.Timedelta(float(value), unit=unit) for value in np.asarray(xtime[:], dtype=float)]


def _parse_ymd_fraction_time(values) -> list[pd.Timestamp]:
    timestamps = []
    for raw_value in np.asarray(values, dtype=float):
        ymd = int(np.floor(raw_value))
        fraction = float(raw_value - ymd)
        base = datetime.strptime(str(ymd), "%Y%m%d")
        seconds = int(round(fraction * 24 * 3600))
        timestamps.append(pd.Timestamp(base + timedelta(seconds=seconds)))
    return timestamps


def _read_coordinates(ds: Dataset, coord_source: Path | None) -> tuple[np.ndarray, np.ndarray]:
    if "XLAT" in ds.variables and "XLONG" in ds.variables:
        return _normalize_coord(ds.variables["XLAT"][:]), _normalize_coord(ds.variables["XLONG"][:])
    if coord_source is None:
        raise KeyError("Hourly WRF file must contain XLAT/XLONG or a coordinate source must be provided.")
    with Dataset(coord_source) as coord_ds:
        return _normalize_coord(coord_ds.variables["XLAT"][:]), _normalize_coord(coord_ds.variables["XLONG"][:])


def _normalize_coord(values) -> np.ndarray:
    arr = np.ma.filled(values, np.nan).astype(float)
    if arr.ndim == 3:
        return arr[0]
    if arr.ndim == 2:
        return arr
    raise ValueError(f"Coordinate variable must be 2D or 3D; got {arr.shape}.")


def _dedupe_timestamp_records(records: list[tuple[pd.Timestamp, int]]) -> list[tuple[pd.Timestamp, int]]:
    deduped = {}
    for timestamp, idx in records:
        deduped[timestamp] = idx
    return [(timestamp, deduped[timestamp]) for timestamp in sorted(deduped)]


def _complete_station_days(
    timestamps: list[pd.Timestamp],
    time_offset_hours: int,
    local_day_boundary_hour: int | None,
    drop_incomplete_start_day: bool,
    drop_incomplete_end_day: bool,
) -> set:
    if not timestamps:
        return set()
    expected = _expected_records_per_day(timestamps)
    station_days = [
        _station_day(timestamp + pd.Timedelta(hours=time_offset_hours), local_day_boundary_hour)
        for timestamp in timestamps
    ]
    counts = Counter(station_days)
    keep = set(counts)
    if expected is not None:
        if drop_incomplete_start_day and counts[station_days[0]] < expected:
            keep.discard(station_days[0])
        if drop_incomplete_end_day and counts[station_days[-1]] < expected:
            keep.discard(station_days[-1])
    return keep


def _expected_records_per_day(timestamps: list[pd.Timestamp]) -> int | None:
    unique = sorted(set(timestamps))
    if len(unique) < 2:
        return None
    deltas = [
        (right - left).total_seconds()
        for left, right in zip(unique[:-1], unique[1:])
        if (right - left).total_seconds() > 0
    ]
    if not deltas:
        return None
    median_delta = float(np.median(deltas))
    if median_delta <= 0:
        return None
    return int(round(24 * 3600 / median_delta))
