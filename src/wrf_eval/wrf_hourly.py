from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from netCDF4 import Dataset, chartostring

from wrf_eval.wrf_diag import WrfTmaxDiagnostic, _station_day, discover_wrf_diagnostic_files

DEFAULT_TIME_OFFSET_HOURS = 8
DEFAULT_LOCAL_DAY_BOUNDARY_HOUR = 20


@dataclass(frozen=True)
class DailyWrfField:
    dates: list[date]
    values: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    source: Path
    variable: str
    aggregation: str
    excluded_days: pd.DataFrame


@dataclass(frozen=True)
class _HourlyRecord:
    timestamp: pd.Timestamp
    file_path: Path
    frame_index: int


def aggregate_hourly_tmax(
    timestamps: list[datetime | pd.Timestamp],
    values: np.ndarray,
    time_offset_hours: int = DEFAULT_TIME_OFFSET_HOURS,
    local_day_boundary_hour: int | None = DEFAULT_LOCAL_DAY_BOUNDARY_HOUR,
    drop_incomplete_start_day: bool = True,
    drop_incomplete_end_day: bool = True,
) -> tuple[list[date], np.ndarray]:
    """Aggregate hourly near-surface temperature fields to station-day Tmax."""
    dates, daily, _ = aggregate_hourly_field(
        timestamps,
        values,
        aggregation="max",
        time_offset_hours=time_offset_hours,
        local_day_boundary_hour=local_day_boundary_hour,
        drop_incomplete_start_day=drop_incomplete_start_day,
        drop_incomplete_end_day=drop_incomplete_end_day,
    )
    return dates, daily


def aggregate_hourly_temperature(
    timestamps: list[datetime | pd.Timestamp],
    values: np.ndarray,
    time_offset_hours: int = DEFAULT_TIME_OFFSET_HOURS,
    local_day_boundary_hour: int | None = DEFAULT_LOCAL_DAY_BOUNDARY_HOUR,
    drop_incomplete_start_day: bool = True,
    drop_incomplete_end_day: bool = True,
    aggregation: str = "max",
) -> tuple[list[date], np.ndarray]:
    """Aggregate hourly fields to station-day values."""
    dates, daily, _ = aggregate_hourly_field(
        timestamps,
        values,
        aggregation=aggregation,
        time_offset_hours=time_offset_hours,
        local_day_boundary_hour=local_day_boundary_hour,
        drop_incomplete_start_day=drop_incomplete_start_day,
        drop_incomplete_end_day=drop_incomplete_end_day,
    )
    return dates, daily


def aggregate_hourly_field(
    timestamps: list[datetime | pd.Timestamp],
    values: np.ndarray,
    aggregation: str,
    validation_start: str | None = None,
    validation_end: str | None = None,
    time_offset_hours: int = DEFAULT_TIME_OFFSET_HOURS,
    local_day_boundary_hour: int | None = DEFAULT_LOCAL_DAY_BOUNDARY_HOUR,
    drop_incomplete_start_day: bool = True,
    drop_incomplete_end_day: bool = True,
) -> tuple[list[date], np.ndarray, pd.DataFrame]:
    """Aggregate hourly fields and return kept dates plus excluded-day metadata."""
    aggregation = _normalize_aggregation(aggregation)
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
    day_policy = _build_day_policy(
        [timestamp for timestamp, _ in records],
        validation_start=validation_start,
        validation_end=validation_end,
        time_offset_hours=time_offset_hours,
        local_day_boundary_hour=local_day_boundary_hour,
        drop_incomplete_start_day=drop_incomplete_start_day,
        drop_incomplete_end_day=drop_incomplete_end_day,
    )

    daily: dict[date, np.ndarray] = {}
    daily_counts: dict[date, np.ndarray] = {}
    for timestamp, idx in records:
        station_date = _station_day(timestamp + pd.Timedelta(hours=time_offset_hours), local_day_boundary_hour)
        if station_date not in day_policy.keep_dates:
            continue
        _update_daily_field(daily, daily_counts, station_date, values[idx].astype(float, copy=False), aggregation)

    dates = sorted(daily)
    if not dates:
        raise ValueError("No complete station-day records were available after hourly aggregation.")
    stacked = np.stack([_finalize_daily_field(daily[day], daily_counts.get(day), aggregation) for day in dates], axis=0)
    return dates, stacked, day_policy.excluded_days


def read_wrfout_as_daily_field(
    path: Path,
    target_variable: str,
    file_pattern: str | None = None,
    coord_source: Path | None = None,
    validation_start: str | None = None,
    validation_end: str | None = None,
) -> DailyWrfField:
    """Read wrfout files and aggregate supported target variables to daily station-day fields."""
    variable = _normalize_target_variable(target_variable)
    source_variable, aggregation = _target_source_and_aggregation(variable)
    files = discover_wrf_diagnostic_files(path, file_pattern=file_pattern)
    records: dict[pd.Timestamp, _HourlyRecord] = {}
    lat = None
    lon = None

    for file in files:
        with Dataset(file) as ds:
            _ensure_target_available(ds, variable, file)
            file_times = _read_time_axis(ds)
            frame_count = _target_frame_count(ds, variable)
            if len(file_times) != frame_count:
                raise ValueError(f"Time axis length does not match {source_variable} frames in {file}.")
            file_lat, file_lon = _read_coordinates(ds, coord_source)
            if lat is None:
                lat = file_lat
                lon = file_lon
            elif not np.allclose(lat, file_lat, equal_nan=True) or not np.allclose(lon, file_lon, equal_nan=True):
                raise ValueError("All wrfout files must have matching XLAT/XLONG coordinates.")
            for frame_index, timestamp in enumerate(file_times):
                records[timestamp] = _HourlyRecord(timestamp, file, frame_index)

    sorted_records = [records[key] for key in sorted(records)]
    day_policy = _build_day_policy(
        [record.timestamp for record in sorted_records],
        validation_start=validation_start,
        validation_end=validation_end,
        time_offset_hours=DEFAULT_TIME_OFFSET_HOURS,
        local_day_boundary_hour=DEFAULT_LOCAL_DAY_BOUNDARY_HOUR,
        drop_incomplete_start_day=True,
        drop_incomplete_end_day=True,
    )

    by_file: dict[Path, list[_HourlyRecord]] = defaultdict(list)
    for record in sorted_records:
        station_date = _station_day(record.timestamp + pd.Timedelta(hours=DEFAULT_TIME_OFFSET_HOURS), DEFAULT_LOCAL_DAY_BOUNDARY_HOUR)
        if station_date in day_policy.keep_dates:
            by_file[record.file_path].append(record)

    daily: dict[date, np.ndarray] = {}
    daily_counts: dict[date, np.ndarray] = {}
    for file, file_records in by_file.items():
        with Dataset(file) as ds:
            for record in file_records:
                station_date = _station_day(record.timestamp + pd.Timedelta(hours=DEFAULT_TIME_OFFSET_HOURS), DEFAULT_LOCAL_DAY_BOUNDARY_HOUR)
                field = _read_target_field(ds, variable, record.frame_index)
                _update_daily_field(daily, daily_counts, station_date, field, aggregation)

    dates = sorted(daily)
    if not dates:
        raise ValueError(f"No complete station-day records were available for {variable}.")
    values = np.stack([_finalize_daily_field(daily[day], daily_counts.get(day), aggregation) for day in dates], axis=0)
    return DailyWrfField(
        dates=dates,
        values=values,
        lat=lat,
        lon=lon,
        source=path,
        variable=variable,
        aggregation=aggregation,
        excluded_days=day_policy.excluded_days,
    )


def read_wrf_hourly_t2_as_daily_tmax(
    path: Path,
    variable: str = "T2",
    file_pattern: str | None = None,
    coord_source: Path | None = None,
    time_offset_hours: int = DEFAULT_TIME_OFFSET_HOURS,
    local_day_boundary_hour: int | None = DEFAULT_LOCAL_DAY_BOUNDARY_HOUR,
    drop_incomplete_start_day: bool = True,
    drop_incomplete_end_day: bool = True,
) -> WrfTmaxDiagnostic:
    """Compatibility wrapper for existing tests and scripts."""
    return read_wrf_hourly_t2_as_daily_temperature(
        path,
        variable=variable,
        file_pattern=file_pattern,
        coord_source=coord_source,
        time_offset_hours=time_offset_hours,
        local_day_boundary_hour=local_day_boundary_hour,
        drop_incomplete_start_day=drop_incomplete_start_day,
        drop_incomplete_end_day=drop_incomplete_end_day,
        aggregation="max",
    )


def read_wrf_hourly_t2_as_daily_temperature(
    path: Path,
    variable: str = "T2",
    file_pattern: str | None = None,
    coord_source: Path | None = None,
    time_offset_hours: int = DEFAULT_TIME_OFFSET_HOURS,
    local_day_boundary_hour: int | None = DEFAULT_LOCAL_DAY_BOUNDARY_HOUR,
    drop_incomplete_start_day: bool = True,
    drop_incomplete_end_day: bool = True,
    aggregation: str = "max",
) -> WrfTmaxDiagnostic:
    """Compatibility wrapper returning the previous WrfTmaxDiagnostic shape."""
    files = discover_wrf_diagnostic_files(path, file_pattern=file_pattern)
    timestamps = []
    arrays = []
    lat = None
    lon = None
    for file in files:
        with Dataset(file) as ds:
            if variable not in ds.variables:
                available = ", ".join(ds.variables.keys())
                raise KeyError(f"Variable {variable!r} was not found in {file}. Available variables: {available}")
            file_lat, file_lon = _read_coordinates(ds, coord_source)
            lat = file_lat if lat is None else lat
            lon = file_lon if lon is None else lon
            file_times = _read_time_axis(ds)
            var = ds.variables[variable]
            units = getattr(var, "units", "")
            for idx, timestamp in enumerate(file_times):
                field = np.ma.filled(var[idx], np.nan).astype(float)
                if units.upper().startswith("K"):
                    field = field - 273.15
                timestamps.append(timestamp)
                arrays.append(field)
    dates, values, _ = aggregate_hourly_field(
        timestamps,
        np.stack(arrays, axis=0),
        aggregation=aggregation,
        time_offset_hours=time_offset_hours,
        local_day_boundary_hour=local_day_boundary_hour,
        drop_incomplete_start_day=drop_incomplete_start_day,
        drop_incomplete_end_day=drop_incomplete_end_day,
    )
    return WrfTmaxDiagnostic(dates=dates, tmax_c=values, lat=lat, lon=lon, source=path, variable=f"{variable}_HOURLY_{aggregation.upper()}")


@dataclass(frozen=True)
class _DayPolicy:
    keep_dates: set[date]
    excluded_days: pd.DataFrame


def _build_day_policy(
    timestamps: list[pd.Timestamp],
    validation_start: str | None,
    validation_end: str | None,
    time_offset_hours: int,
    local_day_boundary_hour: int | None,
    drop_incomplete_start_day: bool,
    drop_incomplete_end_day: bool,
) -> _DayPolicy:
    if not timestamps:
        return _DayPolicy(set(), _excluded_days_frame([]))
    expected = _expected_records_per_day(timestamps)
    station_days = [
        _station_day(timestamp + pd.Timedelta(hours=time_offset_hours), local_day_boundary_hour)
        for timestamp in timestamps
    ]
    counts = Counter(station_days)
    first_day = station_days[0]
    last_day = station_days[-1]
    keep_dates = set()
    excluded_rows = []
    for day in sorted(counts):
        actual = int(counts[day])
        expected_count = int(expected) if expected is not None else actual
        reason = None
        if not _date_in_validation_window(day, validation_start, validation_end):
            reason = "outside_validation_window"
        elif expected is not None and actual < expected_count and (
            (drop_incomplete_start_day and day == first_day)
            or (drop_incomplete_end_day and day == last_day)
            or day not in {first_day, last_day}
        ):
            reason = "incomplete_day"

        if reason:
            excluded_rows.append(
                {
                    "date": day.isoformat(),
                    "reason": reason,
                    "actual_records": actual,
                    "expected_records": expected_count,
                }
            )
        else:
            keep_dates.add(day)
    return _DayPolicy(keep_dates, _excluded_days_frame(excluded_rows))


def _excluded_days_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["date", "reason", "actual_records", "expected_records"])


def _date_in_validation_window(day: date, validation_start: str | None, validation_end: str | None) -> bool:
    start = _parse_validation_bound(day, validation_start)
    end = _parse_validation_bound(day, validation_end)
    if start is None and end is None:
        return True
    if start is not None and end is None:
        return day >= start
    if start is None and end is not None:
        return day <= end
    if start <= end:
        return start <= day <= end
    return day >= start or day <= end


def _parse_validation_bound(day: date, value: str | None) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = text.split("-")
    if len(parts) == 2:
        month, day_num = (int(part) for part in parts)
        return date(day.year, month, day_num)
    return pd.to_datetime(text, errors="raise").date()


def _normalize_target_variable(value: str) -> str:
    key = value.strip().lower()
    aliases = {"tmax": "Tmax", "t2": "T2", "rh": "RH", "rhu": "RH", "relative_humidity": "RH"}
    if key not in aliases:
        raise ValueError(f"Unsupported target variable: {value!r}. Expected T2, Tmax, or RH.")
    return aliases[key]


def _target_source_and_aggregation(variable: str) -> tuple[str, str]:
    if variable == "Tmax":
        return "T2", "max"
    if variable == "T2":
        return "T2", "mean"
    if variable == "RH":
        return "RH", "mean"
    raise ValueError(f"Unsupported target variable: {variable}")


def _ensure_target_available(ds: Dataset, variable: str, file: Path) -> None:
    if variable in {"T2", "Tmax"} and "T2" not in ds.variables:
        available = ", ".join(ds.variables.keys())
        raise KeyError(f"T2 was not found in {file}. Available variables: {available}")
    if variable == "RH" and not _has_rh_source(ds):
        available = ", ".join(ds.variables.keys())
        raise KeyError(f"RH validation requires RH2, RH, or T2+Q2+PSFC in {file}. Available variables: {available}")


def _has_rh_source(ds: Dataset) -> bool:
    return "RH2" in ds.variables or "RH" in ds.variables or {"T2", "Q2", "PSFC"}.issubset(ds.variables.keys())


def _target_frame_count(ds: Dataset, variable: str) -> int:
    if variable in {"T2", "Tmax"}:
        return int(ds.variables["T2"].shape[0])
    if "RH2" in ds.variables:
        return int(ds.variables["RH2"].shape[0])
    if "RH" in ds.variables:
        return int(ds.variables["RH"].shape[0])
    return int(ds.variables["T2"].shape[0])


def _read_target_field(ds: Dataset, variable: str, frame_index: int) -> np.ndarray:
    if variable in {"T2", "Tmax"}:
        return _read_temperature_c(ds, "T2", frame_index)
    return _read_relative_humidity_pct(ds, frame_index)


def _read_temperature_c(ds: Dataset, variable: str, frame_index: int) -> np.ndarray:
    var = ds.variables[variable]
    field = np.ma.filled(var[frame_index], np.nan).astype(float)
    units = getattr(var, "units", "")
    if units.upper().startswith("K"):
        return field - 273.15
    return field


def _read_relative_humidity_pct(ds: Dataset, frame_index: int) -> np.ndarray:
    if "RH2" in ds.variables:
        return _normalize_rh_pct(_read_time_slice(ds.variables["RH2"], frame_index))
    if "RH" in ds.variables:
        return _normalize_rh_pct(_read_time_slice(ds.variables["RH"], frame_index))
    t2_c = _read_temperature_c(ds, "T2", frame_index)
    q2 = np.ma.filled(ds.variables["Q2"][frame_index], np.nan).astype(float)
    psfc = np.ma.filled(ds.variables["PSFC"][frame_index], np.nan).astype(float)
    return _calculate_rh_pct(t2_c, q2, psfc)


def _read_time_slice(var, frame_index: int) -> np.ndarray:
    if len(var.dimensions) == 4:
        return np.ma.filled(var[frame_index, 0], np.nan).astype(float)
    if len(var.dimensions) == 3:
        return np.ma.filled(var[frame_index], np.nan).astype(float)
    raise ValueError(f"Variable {var.name} must be time,y,x or time,z,y,x; got dimensions {var.dimensions}.")


def _normalize_rh_pct(field: np.ndarray) -> np.ndarray:
    out = field.astype(float, copy=True)
    finite = out[np.isfinite(out)]
    if finite.size and float(np.nanmax(finite)) <= 1.5:
        out = out * 100.0
    return np.clip(out, 0.0, 100.0)


def _calculate_rh_pct(t2_c: np.ndarray, q2: np.ndarray, psfc: np.ndarray) -> np.ndarray:
    vapor_pressure = q2 * psfc / (0.622 + 0.378 * q2)
    saturation_vapor_pressure = 611.2 * np.exp((17.67 * t2_c) / (t2_c + 243.5))
    rh = 100.0 * vapor_pressure / saturation_vapor_pressure
    return np.clip(rh, 0.0, 100.0)


def _normalize_aggregation(aggregation: str) -> str:
    normalized = aggregation.strip().lower()
    aliases = {"maximum": "max", "tmax": "max", "average": "mean", "avg": "mean", "tmean": "mean", "minimum": "min", "tmin": "min"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"max", "mean", "min"}:
        raise ValueError(f"Unsupported hourly aggregation: {aggregation!r}. Expected max, mean, or min.")
    return normalized


def _update_daily_field(daily: dict, daily_counts: dict, station_date: date, field: np.ndarray, aggregation: str) -> None:
    if aggregation == "mean":
        valid = np.isfinite(field)
        field_sum = np.where(valid, field, 0.0)
        if station_date not in daily:
            daily[station_date] = field_sum.astype(float, copy=True)
            daily_counts[station_date] = valid.astype(np.int16)
        else:
            daily[station_date] = daily[station_date] + field_sum
            daily_counts[station_date] = daily_counts[station_date] + valid.astype(np.int16)
        return

    if station_date not in daily:
        daily[station_date] = field.astype(float, copy=True)
        return
    if aggregation == "max":
        daily[station_date] = np.fmax(daily[station_date], field)
    elif aggregation == "min":
        daily[station_date] = np.fmin(daily[station_date], field)


def _finalize_daily_field(value: np.ndarray, count: np.ndarray | None, aggregation: str) -> np.ndarray:
    if aggregation != "mean":
        return value
    if count is None:
        raise ValueError("Mean aggregation requires daily sample counts.")
    out = np.full(value.shape, np.nan, dtype=float)
    np.divide(value, count, out=out, where=count > 0)
    return out


def _read_time_axis(ds: Dataset) -> list[pd.Timestamp]:
    if "Times" in ds.variables:
        strings = chartostring(ds.variables["Times"][:])
        return [pd.to_datetime(str(value).strip(), format="%Y-%m-%d_%H:%M:%S", errors="raise") for value in strings]
    if "XTIME" not in ds.variables:
        raise KeyError("wrfout file must contain Times or XTIME.")
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
        raise KeyError("wrfout file must contain XLAT/XLONG or a coordinate source must be provided.")
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
