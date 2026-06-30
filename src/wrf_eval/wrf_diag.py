from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from netCDF4 import Dataset, chartostring


@dataclass(frozen=True)
class WrfTmaxDiagnostic:
    dates: list[date]
    tmax_c: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    source: Path
    variable: str


def discover_wrf_diagnostic_files(path: Path, file_pattern: str | None = None) -> list[Path]:
    """Return one or more WRF diagnostic files from a file or directory path."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"WRF input does not exist: {path}")
    if file_pattern:
        files = sorted(p for p in path.glob(file_pattern) if p.is_file() and not p.name.startswith("."))
    else:
        files = sorted(p for p in path.iterdir() if p.is_file() and not p.name.startswith("."))
    if not files:
        raise FileNotFoundError(f"No WRF diagnostic files were found in directory: {path}")
    return files


def merge_wrf_tmax_diagnostics(diagnostics: list[WrfTmaxDiagnostic]) -> WrfTmaxDiagnostic:
    """Merge multiple WRF Tmax diagnostics into one continuous date-sorted dataset."""
    if not diagnostics:
        raise ValueError("At least one WRF diagnostic is required for merging.")
    if len(diagnostics) == 1:
        return diagnostics[0]

    reference = diagnostics[0]
    records = []
    seen_dates = set()
    for diagnostic in diagnostics:
        if diagnostic.variable != reference.variable:
            raise ValueError("All WRF diagnostics must use the same variable.")
        if diagnostic.lat.shape != reference.lat.shape or diagnostic.lon.shape != reference.lon.shape:
            raise ValueError("All WRF diagnostics must use the same coordinate grid.")
        if not np.allclose(diagnostic.lat, reference.lat, equal_nan=True) or not np.allclose(diagnostic.lon, reference.lon, equal_nan=True):
            raise ValueError("All WRF diagnostics must have matching XLAT/XLONG coordinates.")
        for idx, day in enumerate(diagnostic.dates):
            if day in seen_dates:
                raise ValueError(f"Duplicate WRF diagnostic date found while merging: {day}")
            seen_dates.add(day)
            records.append((day, diagnostic.tmax_c[idx]))

    records.sort(key=lambda item: item[0])
    dates = [item[0] for item in records]
    values = np.stack([item[1] for item in records], axis=0)
    return WrfTmaxDiagnostic(
        dates=dates,
        tmax_c=values,
        lat=reference.lat,
        lon=reference.lon,
        source=reference.source.parent,
        variable=reference.variable,
    )


def _parse_times(ds: Dataset) -> list[datetime | None]:
    if "Times" not in ds.variables:
        return []
    strings = chartostring(ds.variables["Times"][:])
    out: list[datetime | None] = []
    for value in strings:
        text = str(value).strip()
        if not text:
            out.append(None)
            continue
        parsed = pd.to_datetime(text, format="%Y-%m-%d_%H:%M:%S", errors="coerce")
        out.append(None if pd.isna(parsed) else parsed.to_pydatetime())
    return out


def _local_timestamp(value, time_offset_hours: int) -> pd.Timestamp | None:
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed + pd.Timedelta(hours=time_offset_hours)


def _station_day(local_time: pd.Timestamp, local_day_boundary_hour: int | None) -> date:
    if local_day_boundary_hour is None:
        return local_time.date()
    boundary = pd.Timestamp(local_time.date()) + pd.Timedelta(hours=local_day_boundary_hour)
    if local_time > boundary:
        return (local_time + pd.Timedelta(days=1)).date()
    return local_time.date()


def _boundary_time_for_date(day: date, local_day_boundary_hour: int | None) -> pd.Timestamp:
    hour = 0 if local_day_boundary_hour is None else local_day_boundary_hour
    return pd.Timestamp(day) + pd.Timedelta(hours=hour)


def select_record_dates(
    record_count: int,
    parsed_dates: list[date | datetime | None],
    rebuild_start: str | date | None = None,
    time_step_days: int = 1,
    drop_initial_frames: int = 0,
    time_offset_hours: int = 0,
    local_day_boundary_hour: int | None = None,
    drop_incomplete_start_day: bool = False,
) -> tuple[list[int], list[date]]:
    """Select valid record indices and local dates, optionally rebuilding a regular daily axis."""
    if drop_initial_frames < 0:
        raise ValueError("drop_initial_frames must be >= 0.")
    if time_step_days <= 0:
        raise ValueError("time_step_days must be positive.")
    if local_day_boundary_hour is not None and not 0 <= local_day_boundary_hour <= 23:
        raise ValueError("local_day_boundary_hour must be between 0 and 23.")

    if rebuild_start is not None:
        start = pd.to_datetime(rebuild_start, errors="raise")
        candidates = [
            (
                idx,
                start + pd.Timedelta(days=i * time_step_days) + pd.Timedelta(hours=time_offset_hours),
            )
            for i, idx in enumerate(range(drop_initial_frames, record_count))
        ]
    else:
        all_dates = list(parsed_dates[:record_count])
        if len(all_dates) < record_count:
            all_dates.extend([None] * (record_count - len(all_dates)))
        candidates = []
        for idx in range(drop_initial_frames, record_count):
            local_time = _local_timestamp(all_dates[idx], time_offset_hours)
            if local_time is None:
                continue
            candidates.append((idx, local_time))

    if drop_incomplete_start_day and candidates:
        first_local_time = candidates[0][1]
        first_boundary = _boundary_time_for_date(first_local_time.date(), local_day_boundary_hour)
        if first_local_time != first_boundary:
            first_station_day = _station_day(first_local_time, local_day_boundary_hour)
            candidates = [
                (idx, local_time)
                for idx, local_time in candidates
                if _station_day(local_time, local_day_boundary_hour) != first_station_day
            ]

    indices = [idx for idx, _ in candidates]
    dates = [_station_day(local_time, local_day_boundary_hour) for _, local_time in candidates]
    return indices, dates


def build_effective_dates(
    raw_dates: list[date | datetime | None],
    frame_count: int,
    drop_initial_frames: int = 0,
    override_start_date: date | None = None,
    frequency_days: int = 1,
    time_offset_hours: int = 0,
    local_day_boundary_hour: int | None = None,
    drop_incomplete_start_day: bool = False,
) -> tuple[list[date], list[int]]:
    """Compatibility wrapper returning dates first, then source indices."""
    indices, dates = select_record_dates(
        record_count=frame_count,
        parsed_dates=raw_dates,
        rebuild_start=override_start_date,
        time_step_days=frequency_days,
        drop_initial_frames=drop_initial_frames,
        time_offset_hours=time_offset_hours,
        local_day_boundary_hour=local_day_boundary_hour,
        drop_incomplete_start_day=drop_incomplete_start_day,
    )
    return dates, indices


def _read_coordinates(ds: Dataset, coord_source: Path | None) -> tuple[np.ndarray, np.ndarray]:
    if "XLAT" in ds.variables and "XLONG" in ds.variables:
        lat = np.ma.filled(ds.variables["XLAT"][0], np.nan).astype(float)
        lon = np.ma.filled(ds.variables["XLONG"][0], np.nan).astype(float)
        return lat, lon
    if coord_source is None:
        raise KeyError("WRF diagnostic file must contain XLAT/XLONG or a coordinate source must be provided.")
    with Dataset(coord_source) as coord_ds:
        if "XLAT" not in coord_ds.variables or "XLONG" not in coord_ds.variables:
            raise KeyError(f"Coordinate source does not contain XLAT/XLONG: {coord_source}")
        lat = np.ma.filled(coord_ds.variables["XLAT"][0], np.nan).astype(float)
        lon = np.ma.filled(coord_ds.variables["XLONG"][0], np.nan).astype(float)
        return lat, lon


def read_wrf_tmax_diagnostic(
    path: Path,
    variable: str = "T2MAX",
    min_valid_c: float = -80.0,
    max_valid_c: float = 70.0,
    coord_source: Path | None = None,
    rebuild_start: str | date | None = None,
    time_step_days: int = 1,
    drop_initial_frames: int = 0,
    time_offset_hours: int = 0,
    local_day_boundary_hour: int | None = None,
    drop_incomplete_start_day: bool = False,
) -> WrfTmaxDiagnostic:
    """Read daily maximum temperature from WRF diagnostic NetCDF or diagnostic-like files."""
    with Dataset(path) as ds:
        if variable not in ds.variables:
            available = ", ".join(ds.variables.keys())
            raise KeyError(f"Variable {variable!r} was not found in {path}. Available variables: {available}")
        dates = _parse_times(ds)
        raw = np.ma.filled(ds.variables[variable][:], np.nan).astype(float)
        units = getattr(ds.variables[variable], "units", "")
        lat, lon = _read_coordinates(ds, coord_source)

    if raw.ndim != 3:
        raise ValueError(f"{variable} must have dimensions Time, south_north, west_east; got {raw.shape}.")

    if units.upper().startswith("K"):
        temp_c = raw - 273.15
    else:
        temp_c = raw.copy()

    selected_indices, selected_dates = select_record_dates(
        record_count=temp_c.shape[0],
        parsed_dates=dates,
        rebuild_start=rebuild_start,
        time_step_days=time_step_days,
        drop_initial_frames=drop_initial_frames,
        time_offset_hours=time_offset_hours,
        local_day_boundary_hour=local_day_boundary_hour,
        drop_incomplete_start_day=drop_incomplete_start_day,
    )

    valid_records = []
    valid_dates = []
    for idx, day in zip(selected_indices, selected_dates):
        field = temp_c[idx]
        valid_fraction = np.isfinite(field) & (field >= min_valid_c) & (field <= max_valid_c)
        if float(np.mean(valid_fraction)) < 0.5:
            continue
        cleaned = np.where(valid_fraction, field, np.nan)
        valid_records.append(cleaned)
        valid_dates.append(day)

    if not valid_records:
        raise ValueError(f"No valid {variable} records were found in {path}.")

    return WrfTmaxDiagnostic(
        dates=valid_dates,
        tmax_c=np.stack(valid_records, axis=0),
        lat=lat,
        lon=lon,
        source=path,
        variable=variable,
    )


def read_wrf_tmax_diagnostics(
    path: Path,
    variable: str = "T2MAX",
    min_valid_c: float = -80.0,
    max_valid_c: float = 70.0,
    coord_source: Path | None = None,
    rebuild_start: str | date | None = None,
    time_step_days: int = 1,
    drop_initial_frames: int = 0,
    time_offset_hours: int = 0,
    local_day_boundary_hour: int | None = None,
    drop_incomplete_start_day: bool = False,
    file_pattern: str | None = None,
) -> WrfTmaxDiagnostic:
    """Read and merge one or more WRF diagnostic files from a file or directory."""
    files = discover_wrf_diagnostic_files(path, file_pattern=file_pattern)
    diagnostics = []
    for file_index, file in enumerate(files):
        diagnostics.append(
            read_wrf_tmax_diagnostic(
                file,
                variable=variable,
                min_valid_c=min_valid_c,
                max_valid_c=max_valid_c,
                coord_source=coord_source,
                rebuild_start=rebuild_start,
                time_step_days=time_step_days,
                drop_initial_frames=drop_initial_frames,
                time_offset_hours=time_offset_hours,
                local_day_boundary_hour=local_day_boundary_hour,
                drop_incomplete_start_day=drop_incomplete_start_day and file_index == 0,
            )
        )
    return merge_wrf_tmax_diagnostics(diagnostics)
