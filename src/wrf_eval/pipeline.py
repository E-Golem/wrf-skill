from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from wrf_eval.config import FIXED_SCORE_METRICS, SUPPORTED_VARIABLES
from wrf_eval.metrics import compute_metrics, normalize_metric_names, score_from_metrics
from wrf_eval.observed import read_china_daily_humidity, read_china_daily_temperature
from wrf_eval.sampling import nearest_grid_indices
from wrf_eval.wrf_hourly import (
    DEFAULT_LOCAL_DAY_BOUNDARY_HOUR,
    DEFAULT_TIME_OFFSET_HOURS,
    DailyWrfField,
    read_wrfout_as_daily_field,
)


@dataclass(frozen=True)
class ProcessingConfig:
    wrf_input: Path
    observed_dir: Path
    boundary: Path | None
    output_dir: Path
    scheme_name: str | None = None
    variable: str = "Tmax"
    file_pattern: str | None = None
    coord_source: Path | None = None
    validation_start: str | None = "06-01"
    validation_end: str | None = "10-01"


@dataclass(frozen=True)
class ProcessingResult:
    matched_path: Path
    overall_score_path: Path
    daily_score_path: Path
    station_score_path: Path
    excluded_days_path: Path
    report_path: Path
    matched_rows: int
    station_count: int
    date_count: int
    excluded_day_count: int
    overall_metrics: dict[str, float]


@dataclass(frozen=True)
class _VariableSpec:
    variable: str
    observation_kind: str
    observed_column: str
    model_column: str
    matched_filename: str
    report_filename: str
    unit_label: str
    description: str


def _variable_spec(variable: str) -> _VariableSpec:
    normalized = _normalize_variable(variable)
    if normalized == "Tmax":
        return _VariableSpec(
            variable="Tmax",
            observation_kind="TEM",
            observed_column="tmax_obs_c",
            model_column="tmax_wrf_c",
            matched_filename="matched_station_daily_tmax.csv",
            report_filename="wrf_tmax_evaluation_report.md",
            unit_label="degC",
            description="daily maximum 2 m temperature",
        )
    if normalized == "T2":
        return _VariableSpec(
            variable="T2",
            observation_kind="TEM",
            observed_column="tmean_obs_c",
            model_column="t2_wrf_c",
            matched_filename="matched_station_daily_t2.csv",
            report_filename="wrf_t2_evaluation_report.md",
            unit_label="degC",
            description="daily mean 2 m temperature",
        )
    return _VariableSpec(
        variable="RH",
        observation_kind="RHU",
        observed_column="rh_mean_obs_pct",
        model_column="rh_wrf_pct",
        matched_filename="matched_station_daily_rh.csv",
        report_filename="wrf_rh_evaluation_report.md",
        unit_label="%",
        description="daily mean 2 m relative humidity",
    )


def _normalize_variable(variable: str) -> str:
    aliases = {"tmax": "Tmax", "t2": "T2", "rh": "RH", "rhu": "RH", "relative_humidity": "RH"}
    key = variable.strip().lower()
    if key not in aliases:
        raise ValueError(f"Unsupported validation variable: {variable!r}. Expected one of: {', '.join(SUPPORTED_VARIABLES)}.")
    return aliases[key]


def _temperature_files(observed_dir: Path) -> list[Path]:
    files = sorted(observed_dir.glob("**/SURF_CLI_CHN_MUL_DAY-TEM-*.TXT"))
    if not files:
        raise FileNotFoundError(f"No China daily TEM files were found under {observed_dir}.")
    return files


def _humidity_files(observed_dir: Path) -> list[Path]:
    files = sorted(observed_dir.glob("**/SURF_CLI_CHN_MUL_DAY-RHU-*.TXT"))
    if not files:
        raise FileNotFoundError(
            f"RH validation requires China daily RHU files named SURF_CLI_CHN_MUL_DAY-RHU-*.TXT under {observed_dir}."
        )
    return files


def _scheme_name(config: ProcessingConfig) -> str:
    if config.scheme_name:
        return config.scheme_name
    return config.wrf_input.name if config.wrf_input.name else config.wrf_input.stem


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


def date_in_validation_window(day: date, validation_start: str | None, validation_end: str | None) -> bool:
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


def filter_points_by_boundary(stations: pd.DataFrame, boundary_path: Path | None) -> pd.DataFrame:
    if boundary_path is None:
        return stations.copy()

    boundary = gpd.read_file(boundary_path)
    if boundary.empty:
        raise ValueError(f"Boundary file is empty: {boundary_path}")
    if boundary.crs is None:
        boundary = boundary.set_crs("EPSG:4326")
    boundary = boundary.to_crs("EPSG:4326")
    geometry = boundary.geometry.union_all() if hasattr(boundary.geometry, "union_all") else boundary.geometry.unary_union

    unique_stations = stations[["station_id", "lat", "lon"]].drop_duplicates("station_id").copy()
    station_gdf = gpd.GeoDataFrame(
        unique_stations,
        geometry=gpd.points_from_xy(unique_stations["lon"], unique_stations["lat"]),
        crs="EPSG:4326",
    )
    mask = [bool(geometry.covers(point)) for point in station_gdf.geometry.to_numpy()]
    allowed_station_ids = set(station_gdf.loc[mask, "station_id"])
    filtered = stations.loc[stations["station_id"].isin(allowed_station_ids)].copy()
    return filtered.reset_index(drop=True)


def _build_station_grid_index(stations: pd.DataFrame, lat: np.ndarray, lon: np.ndarray) -> pd.DataFrame:
    unique = stations[["station_id", "lat", "lon", "elevation_m"]].drop_duplicates("station_id").copy()
    grid_y = []
    grid_x = []
    grid_lat = []
    grid_lon = []
    for row in unique.itertuples(index=False):
        iy, ix = nearest_grid_indices(lat, lon, float(row.lat), float(row.lon))
        grid_y.append(iy)
        grid_x.append(ix)
        grid_lat.append(float(lat[iy, ix]))
        grid_lon.append(float(lon[iy, ix]))
    unique["grid_y"] = grid_y
    unique["grid_x"] = grid_x
    unique["wrf_lat"] = grid_lat
    unique["wrf_lon"] = grid_lon
    unique["grid_distance_deg"] = np.sqrt((unique["lat"] - unique["wrf_lat"]) ** 2 + (unique["lon"] - unique["wrf_lon"]) ** 2)
    return unique


def _sample_wrf_for_stations(
    dates: list[date],
    values: np.ndarray,
    station_index: pd.DataFrame,
    model_column: str,
) -> pd.DataFrame:
    rows = []
    for station in station_index.itertuples(index=False):
        station_values = values[:, int(station.grid_y), int(station.grid_x)]
        for day, value in zip(dates, station_values):
            rows.append(
                {
                    "station_id": station.station_id,
                    "date": day,
                    model_column: float(value) if np.isfinite(value) else np.nan,
                    "wrf_lat": station.wrf_lat,
                    "wrf_lon": station.wrf_lon,
                    "grid_y": int(station.grid_y),
                    "grid_x": int(station.grid_x),
                    "grid_distance_deg": station.grid_distance_deg,
                }
            )
    return pd.DataFrame(rows)


def merge_observed_and_sampled(observed: pd.DataFrame, sampled: pd.DataFrame, mode: str = "exact") -> pd.DataFrame:
    """Merge observed and WRF sampled station-day values by exact date."""
    if mode != "exact":
        raise ValueError("v1.1 only supports exact station-day matching.")
    matched = observed.merge(sampled, on=["station_id", "date"], how="inner")
    if not matched.empty:
        matched["observed_date"] = matched["date"]
    return matched


def _metrics_frame(grouped, group_columns: list[str], selected_metrics: list[str], observed_column: str, model_column: str) -> pd.DataFrame:
    rows = []
    for keys, group in grouped:
        metrics = compute_metrics(group[observed_column].to_numpy(), group[model_column].to_numpy())
        metrics["score"] = score_from_metrics(metrics, selected_metrics=selected_metrics)
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_columns, keys))
        row.update(metrics)
        rows.append(row)
    return pd.DataFrame(rows)


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def frame_to_markdown_table(frame: pd.DataFrame) -> str:
    """Render a small DataFrame as a Markdown table without optional dependencies."""
    if frame.empty:
        return "_No records._"

    columns = [str(col) for col in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        values = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                values.append(f"{float(value):.4f}" if np.isfinite(value) else "NaN")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _read_observed(config: ProcessingConfig, spec: _VariableSpec) -> pd.DataFrame:
    if spec.observation_kind == "TEM":
        observed = read_china_daily_temperature(_temperature_files(config.observed_dir))
    else:
        observed = read_china_daily_humidity(_humidity_files(config.observed_dir))
    if spec.observed_column not in observed.columns:
        raise ValueError(f"Observed data does not contain required column {spec.observed_column!r}.")
    return observed


def _filter_observed_to_wrf_dates(observed: pd.DataFrame, wrf_dates: list[date]) -> pd.DataFrame:
    return observed[observed["date"].isin(set(wrf_dates))].copy()


def _report_metric_columns() -> list[str]:
    return ["n", "score", *normalize_metric_names(FIXED_SCORE_METRICS)]


def _table_columns(base_columns: list[str]) -> list[str]:
    columns = [*base_columns, "n", "score", *normalize_metric_names(FIXED_SCORE_METRICS)]
    seen = []
    for column in columns:
        if column not in seen:
            seen.append(column)
    return seen


def _excluded_days_preview(excluded_days: pd.DataFrame) -> pd.DataFrame:
    if excluded_days.empty:
        return excluded_days
    return excluded_days.head(30).copy()


def _write_report(
    config: ProcessingConfig,
    spec: _VariableSpec,
    wrf: DailyWrfField,
    result_context: dict,
    overall: dict[str, float],
    daily: pd.DataFrame,
    station: pd.DataFrame,
    excluded_days: pd.DataFrame,
    report_path: Path,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    best_station = station.sort_values("score", ascending=False).head(5)
    worst_station = station.sort_values("score", ascending=True).head(5)
    daily_preview = daily.sort_values("date").copy()

    lines = [
        f"# WRF {spec.variable} station verification report",
        "",
        f"Generated at: {generated_at}",
        "",
        "## 1. Fixed v1.1 settings",
        "",
        "- Input type: `wrfout` only.",
        "- Observation type: China meteorological station daily data.",
        f"- Time handling: WRF UTC timestamps are shifted to UTC+{DEFAULT_TIME_OFFSET_HOURS}.",
        f"- Station-day boundary: Beijing time {DEFAULT_LOCAL_DAY_BOUNDARY_HOUR}:00.",
        f"- Metrics: `{', '.join(FIXED_SCORE_METRICS)}`.",
        "",
        "## 2. Input data",
        "",
        f"- Scheme: `{_scheme_name(config)}`",
        f"- WRF input: `{config.wrf_input}`",
        f"- File pattern: `{config.file_pattern}`",
        f"- Validation variable: `{spec.variable}` ({spec.description})",
        f"- WRF aggregation: `{wrf.aggregation}`",
        f"- Observed column: `{spec.observed_column}`",
        f"- Model column: `{spec.model_column}`",
        f"- Coordinate source: `{config.coord_source}`",
        f"- Observed directory: `{config.observed_dir}`",
        f"- Boundary file: `{config.boundary}`",
        f"- Validation start: `{config.validation_start}`",
        f"- Validation end: `{config.validation_end}`",
        "",
        "## 3. Data coverage",
        "",
        f"- Kept complete WRF station-day count: {result_context['wrf_date_count']}",
        f"- Kept WRF date range: {result_context['wrf_date_min']} to {result_context['wrf_date_max']}",
        f"- Excluded date count: {len(excluded_days)}",
        f"- Observed records after date/boundary filtering: {result_context['observed_rows']}",
        f"- Stations inside boundary: {result_context['station_count']}",
        f"- Matched station-date samples: {result_context['matched_rows']}",
        "",
        "## 4. Excluded dates",
        "",
        frame_to_markdown_table(_excluded_days_preview(excluded_days)),
        "",
        "## 5. Overall score",
        "",
        "| metric | value |",
        "|---|---:|",
    ]
    for key in _report_metric_columns():
        value = overall.get(key, np.nan)
        if isinstance(value, (int, np.integer)):
            formatted = str(value)
        else:
            formatted = f"{float(value):.4f}" if np.isfinite(value) else "NaN"
        lines.append(f"| {key} | {formatted} |")

    lines.extend(
        [
            "",
            "## 6. Daily scores",
            "",
            frame_to_markdown_table(daily_preview[_table_columns(["date"])]),
            "",
            "## 7. Station score summary",
            "",
            "Highest scoring stations:",
            "",
            frame_to_markdown_table(best_station[_table_columns(["station_id"])]),
            "",
            "Lowest scoring stations:",
            "",
            frame_to_markdown_table(worst_station[_table_columns(["station_id"])]),
            "",
            "## 8. Output files",
            "",
            f"- Matched samples: `{result_context['matched_path']}`",
            f"- Overall score: `{result_context['overall_score_path']}`",
            f"- Daily scores: `{result_context['daily_score_path']}`",
            f"- Station scores: `{result_context['station_score_path']}`",
            f"- Excluded dates: `{result_context['excluded_days_path']}`",
            "",
            "## 9. Notes",
            "",
            "- A date is scored only when the wrfout sequence provides a complete station-day within the validation window.",
            "- Nearest-grid-cell station sampling is used in v1.1.",
            "- The composite score is for batch ranking; inspect the individual metrics before scientific interpretation.",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8-sig")


def run_processing(config: ProcessingConfig) -> ProcessingResult:
    spec = _variable_spec(config.variable)
    wrf = read_wrfout_as_daily_field(
        config.wrf_input,
        target_variable=spec.variable,
        file_pattern=config.file_pattern,
        coord_source=config.coord_source,
        validation_start=config.validation_start,
        validation_end=config.validation_end,
    )
    observed = _read_observed(config, spec)
    observed = _filter_observed_to_wrf_dates(observed, wrf.dates)
    observed = filter_points_by_boundary(observed, config.boundary)
    observed = observed.dropna(subset=[spec.observed_column]).copy()
    if observed.empty:
        raise ValueError("No observed station records remain after date, boundary, and variable filtering.")

    station_index = _build_station_grid_index(observed, wrf.lat, wrf.lon)
    sampled = _sample_wrf_for_stations(wrf.dates, wrf.values, station_index, model_column=spec.model_column)
    matched = merge_observed_and_sampled(observed, sampled)
    matched = matched.dropna(subset=[spec.observed_column, spec.model_column]).copy()
    if matched.empty:
        raise ValueError("No matched station-date pairs were available after WRF sampling.")
    matched[f"error_{spec.unit_label}"] = matched[spec.model_column] - matched[spec.observed_column]

    selected_metrics = normalize_metric_names(FIXED_SCORE_METRICS)
    overall_metrics = compute_metrics(matched[spec.observed_column].to_numpy(), matched[spec.model_column].to_numpy())
    overall_metrics["score"] = score_from_metrics(overall_metrics, selected_metrics=selected_metrics)
    overall_metrics["scheme_name"] = _scheme_name(config)
    overall_metrics["variable"] = spec.variable
    overall_metrics["validation_start"] = config.validation_start
    overall_metrics["validation_end"] = config.validation_end
    overall_metrics["score_metrics"] = ",".join(selected_metrics)
    overall_metrics["time_offset_hours"] = DEFAULT_TIME_OFFSET_HOURS
    overall_metrics["local_day_boundary_hour"] = DEFAULT_LOCAL_DAY_BOUNDARY_HOUR
    overall = pd.DataFrame([overall_metrics])
    daily = _metrics_frame(
        matched.groupby("date"),
        ["date"],
        selected_metrics,
        spec.observed_column,
        spec.model_column,
    ).sort_values("date")
    station = _metrics_frame(
        matched.groupby("station_id"),
        ["station_id"],
        selected_metrics,
        spec.observed_column,
        spec.model_column,
    ).sort_values("score", ascending=False)
    daily.insert(0, "scheme_name", _scheme_name(config))
    daily.insert(1, "variable", spec.variable)
    station.insert(0, "scheme_name", _scheme_name(config))
    station.insert(1, "variable", spec.variable)

    table_dir = config.output_dir / "tables"
    report_dir = config.output_dir / "reports"
    matched_path = table_dir / spec.matched_filename
    overall_score_path = table_dir / "overall_score.csv"
    daily_score_path = table_dir / "daily_scores.csv"
    station_score_path = table_dir / "station_scores.csv"
    excluded_days_path = table_dir / "excluded_days.csv"
    _write_csv(matched, matched_path)
    _write_csv(overall, overall_score_path)
    _write_csv(daily, daily_score_path)
    _write_csv(station, station_score_path)
    _write_csv(wrf.excluded_days, excluded_days_path)

    report_path = report_dir / spec.report_filename
    context = {
        "wrf_date_count": len(wrf.dates),
        "wrf_date_min": min(wrf.dates),
        "wrf_date_max": max(wrf.dates),
        "observed_rows": len(observed),
        "station_count": station_index["station_id"].nunique(),
        "matched_rows": len(matched),
        "matched_path": matched_path,
        "overall_score_path": overall_score_path,
        "daily_score_path": daily_score_path,
        "station_score_path": station_score_path,
        "excluded_days_path": excluded_days_path,
    }
    _write_report(config, spec, wrf, context, overall_metrics, daily, station, wrf.excluded_days, report_path)

    return ProcessingResult(
        matched_path=matched_path,
        overall_score_path=overall_score_path,
        daily_score_path=daily_score_path,
        station_score_path=station_score_path,
        excluded_days_path=excluded_days_path,
        report_path=report_path,
        matched_rows=len(matched),
        station_count=station_index["station_id"].nunique(),
        date_count=len(wrf.dates),
        excluded_day_count=len(wrf.excluded_days),
        overall_metrics=overall_metrics,
    )
