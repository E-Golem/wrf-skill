from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from wrf_eval.metrics import compute_metrics, normalize_metric_names, score_from_metrics
from wrf_eval.observed import read_china_daily_temperature
from wrf_eval.sampling import nearest_grid_indices
from wrf_eval.wrf_diag import WrfTmaxDiagnostic, read_wrf_tmax_diagnostics
from wrf_eval.wrf_hourly import read_wrf_hourly_t2_as_daily_tmax


@dataclass(frozen=True)
class ProcessingConfig:
    wrf_input: Path
    observed_dir: Path
    boundary: Path | None
    output_dir: Path
    report_dir: Path
    scheme_name: str | None = None
    variable: str = "T2MAX"
    input_kind: str = "diagnostic_tmax"
    file_pattern: str | None = None
    coord_source: Path | None = None
    rebuild_start: str | None = None
    time_step_days: int = 1
    drop_initial_frames: int = 0
    time_offset_hours: int = 0
    local_day_boundary_hour: int | None = None
    drop_incomplete_start_day: bool = False
    drop_incomplete_end_day: bool = False
    validation_start: str | None = None
    validation_end: str | None = None
    score_metrics: str | tuple[str, ...] | list[str] | None = None
    date_match: str = "exact"


@dataclass(frozen=True)
class ProcessingResult:
    matched_path: Path
    overall_score_path: Path
    daily_score_path: Path
    station_score_path: Path
    report_path: Path
    matched_rows: int
    station_count: int
    date_count: int
    overall_metrics: dict[str, float]


def _temperature_files(observed_dir: Path) -> list[Path]:
    files = sorted(observed_dir.glob("**/SURF_CLI_CHN_MUL_DAY-TEM-*.TXT"))
    if not files:
        raise FileNotFoundError(f"No China daily TEM files were found under {observed_dir}.")
    return files


def _scheme_name(config: ProcessingConfig) -> str:
    if config.scheme_name:
        return config.scheme_name
    return config.wrf_input.name if config.wrf_input.name else config.wrf_input.stem


def _parse_validation_bound(day: date, value: str | None) -> date | None:
    if value is None:
        return None
    text = value.strip()
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


def _filter_wrf_validation_window(
    wrf: WrfTmaxDiagnostic,
    validation_start: str | None,
    validation_end: str | None,
) -> WrfTmaxDiagnostic:
    if validation_start is None and validation_end is None:
        return wrf
    indices = [
        idx
        for idx, day in enumerate(wrf.dates)
        if date_in_validation_window(day, validation_start, validation_end)
    ]
    if not indices:
        raise ValueError(f"No WRF records remain after validation window filtering: {validation_start} to {validation_end}.")
    return WrfTmaxDiagnostic(
        dates=[wrf.dates[idx] for idx in indices],
        tmax_c=wrf.tmax_c[indices],
        lat=wrf.lat,
        lon=wrf.lon,
        source=wrf.source,
        variable=wrf.variable,
    )


def filter_points_by_boundary(stations: pd.DataFrame, boundary_path: Path | None) -> pd.DataFrame:
    if boundary_path is None:
        return stations.copy()

    boundary = gpd.read_file(boundary_path)
    if boundary.empty:
        raise ValueError(f"Boundary file is empty: {boundary_path}")
    if boundary.crs is None:
        boundary = boundary.set_crs("EPSG:4326")
    boundary = boundary.to_crs("EPSG:4326")
    geometry = boundary.geometry.unary_union

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


def _sample_wrf_for_stations(dates: list[date], tmax_c: np.ndarray, station_index: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for station in station_index.itertuples(index=False):
        values = tmax_c[:, int(station.grid_y), int(station.grid_x)]
        for day, value in zip(dates, values):
            rows.append(
                {
                    "station_id": station.station_id,
                    "date": day,
                    "tmax_wrf_c": float(value) if np.isfinite(value) else np.nan,
                    "wrf_lat": station.wrf_lat,
                    "wrf_lon": station.wrf_lon,
                    "grid_y": int(station.grid_y),
                    "grid_x": int(station.grid_x),
                    "grid_distance_deg": station.grid_distance_deg,
                }
            )
    return pd.DataFrame(rows)


def merge_observed_and_sampled(observed: pd.DataFrame, sampled: pd.DataFrame, mode: str = "exact") -> pd.DataFrame:
    """Merge observed and WRF sampled values either by exact date or month-day."""
    if mode == "exact":
        matched = observed.merge(sampled, on=["station_id", "date"], how="inner")
        matched["observed_date"] = matched["date"]
        return matched
    if mode == "month_day":
        obs = observed.copy()
        wrf = sampled.copy()
        obs["month"] = pd.to_datetime(obs["date"]).dt.month
        obs["day"] = pd.to_datetime(obs["date"]).dt.day
        wrf["month"] = pd.to_datetime(wrf["date"]).dt.month
        wrf["day"] = pd.to_datetime(wrf["date"]).dt.day
        obs = obs.rename(columns={"date": "observed_date"})
        wrf = wrf.rename(columns={"date": "wrf_date"})
        matched = obs.merge(wrf, on=["station_id", "month", "day"], how="inner")
        matched["date"] = matched["wrf_date"]
        return matched
    raise ValueError(f"Unsupported date match mode: {mode}")


def _metrics_frame(grouped, group_columns: list[str], selected_metrics: list[str]) -> pd.DataFrame:
    rows = []
    for keys, group in grouped:
        metrics = compute_metrics(group["tmax_obs_c"].to_numpy(), group["tmax_wrf_c"].to_numpy())
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


def _report_metric_columns(config: ProcessingConfig) -> list[str]:
    return ["n", "score", *normalize_metric_names(config.score_metrics)]


def _table_columns(base_columns: list[str], config: ProcessingConfig) -> list[str]:
    columns = [*base_columns, "n", "score", *normalize_metric_names(config.score_metrics)]
    seen = []
    for column in columns:
        if column not in seen:
            seen.append(column)
    return seen


def frame_to_markdown_table(frame: pd.DataFrame) -> str:
    """Render a small DataFrame as a Markdown table without optional dependencies."""
    if frame.empty:
        return "_无记录_"

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


def _input_kind_note(config: ProcessingConfig) -> str:
    if config.input_kind == "hourly_t2":
        return "说明：本次输入按逐小时 WRF 输出处理，读取逐小时 `T2` 并按本地日界聚合为日最高温。"
    return "说明：本次输入按 WRF 气象诊断结果处理，直接读取诊断日最高温变量。"


def _processing_step_1(config: ProcessingConfig) -> str:
    if config.input_kind == "hourly_t2":
        return "1. 读取逐小时 WRF NetCDF 文件，解析时间轴、`XLAT`、`XLONG` 和逐小时 `T2`。"
    return "1. 读取 WRF 气象诊断 NetCDF 文件，解析 `Times`、`XLAT`、`XLONG` 和诊断日最高温变量。"


def _processing_step_2(config: ProcessingConfig) -> str:
    if config.input_kind == "hourly_t2":
        return "2. 将逐小时 `T2` 从 K 转换为摄氏度，先按配置校正到本地时间，再按本地日界聚合为日最高温。"
    return "2. 将诊断日最高温从 K 转换为摄氏度，按配置校正时间轴和本地日界，并剔除无效时间或不合理温度格点。"


def _write_report(
    config: ProcessingConfig,
    result_context: dict,
    overall: dict[str, float],
    daily: pd.DataFrame,
    station: pd.DataFrame,
    report_path: Path,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    best_station = station.sort_values("score", ascending=False).head(5)
    worst_station = station.sort_values("score", ascending=True).head(5)
    daily_preview = daily.sort_values("date").copy()

    lines = [
        "# WRF 日最高温后处理与评分报告",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 输入数据",
        "",
        f"- WRF 输入：`{config.wrf_input}`",
        f"- 当前参数化方案：`{_scheme_name(config)}`",
        f"- 输入类型：`{config.input_kind}`",
        f"- 文件匹配模式：`{config.file_pattern}`",
        f"- WRF 变量：`{config.variable}`",
        f"- 坐标参考文件：`{config.coord_source}`",
        f"- 观测目录：`{config.observed_dir}`",
        f"- 边界文件：`{config.boundary}`",
        f"- 日期匹配模式：`{config.date_match}`",
        f"- 时间轴重建起始日：`{config.rebuild_start}`",
        f"- 时间步长：`{config.time_step_days}` 天",
        f"- 丢弃起始帧数：`{config.drop_initial_frames}`",
        f"- WRF 时间偏移：`UTC{config.time_offset_hours:+d}` 小时",
        f"- 本地日界小时：`{config.local_day_boundary_hour}`",
        f"- 丢弃首个不完整本地日：`{config.drop_incomplete_start_day}`",
        f"- 丢弃末尾不完整本地日：`{config.drop_incomplete_end_day}`",
        f"- 验证起始日期：`{config.validation_start}`",
        f"- 验证结束日期：`{config.validation_end}`",
        f"- 参与评分指标：`{', '.join(normalize_metric_names(config.score_metrics))}`",
        "",
        _input_kind_note(config),
        "",
        "## 2. 处理过程",
        "",
        _processing_step_1(config),
        _processing_step_2(config),
        "3. 读取中国地面气象站日值温度 TXT，解析站号、经纬度、日期和日最高温。",
        "4. 使用研究区边界筛选站点，并将站点匹配到最近 WRF 网格。",
        "5. 对站点-日期配对样本计算候选指标，并按配置选择部分指标生成综合评分。",
        "",
        "## 3. 数据覆盖",
        "",
        f"- WRF 有效日期数：{result_context['wrf_date_count']}",
        f"- WRF 有效日期范围：{result_context['wrf_date_min']} 至 {result_context['wrf_date_max']}",
        f"- 观测记录数：{result_context['observed_rows']}",
        f"- 边界内观测站数：{result_context['station_count']}",
        f"- 成功匹配样本数：{result_context['matched_rows']}",
        "",
        "## 4. 总体评分",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
    ]
    for key in _report_metric_columns(config):
        value = overall.get(key, np.nan)
        if isinstance(value, (int, np.integer)):
            formatted = str(value)
        else:
            formatted = f"{float(value):.4f}" if np.isfinite(value) else "NaN"
        lines.append(f"| {key} | {formatted} |")

    lines.extend(
        [
            "",
            "## 5. 逐日评分",
            "",
            frame_to_markdown_table(daily_preview[_table_columns(["date"], config)]),
            "",
            "## 6. 站点评分摘要",
            "",
            "得分最高的站点：",
            "",
            frame_to_markdown_table(best_station[_table_columns(["station_id"], config)]),
            "",
            "得分最低的站点：",
            "",
            frame_to_markdown_table(worst_station[_table_columns(["station_id"], config)]),
            "",
            "## 7. 输出文件",
            "",
            f"- 匹配明细：`{result_context['matched_path']}`",
            f"- 总体评分：`{result_context['overall_score_path']}`",
            f"- 逐日评分：`{result_context['daily_score_path']}`",
            f"- 逐站评分：`{result_context['station_score_path']}`",
            "",
            "## 8. 注意事项",
            "",
            "- 若启用 WRF 时间偏移，程序会先将 WRF 时间转换到观测数据对应时区，再按本地日界归属站点日值日期。",
            "- 当本地日界小时为 20 时，北京时间 20:00 及之前归当天站点日值，20:00 之后归下一天站点日值。",
            "- 若启用丢弃首个不完整本地日，程序只会对整个输入序列的第一个文件生效，避免多文件拼接时误删每个分段文件的首日。",
            "- 逐小时输入可启用丢弃末尾不完整本地日，避免用不足 24 小时的窗口低估日最高温。",
            "- 当前评分支持通过 `--score-metrics` 或 YAML 配置选择参与综合评分的指标，适合按统一口径批量比较不同参数化方案。",
            "- 批量方案对比可采用统一输入规范：每个方案一个文件夹，文件夹名作为方案名；程序自动生成各方案 `overall_score.csv` 后，再汇总排序选择最高分方案。",
            "- 当日期匹配模式为 `month_day` 时，评分表示同月日参考对比，不表示严格的同年份实况检验。",
            "- 站点匹配采用最近邻格点，后续可扩展为双线性插值或站点海拔订正。",
            "- 综合评分用于快速比较模型表现，不替代对 PCC、RMSE、MAE、RSD 等单项指标的专业判断。",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8-sig")


def run_processing(config: ProcessingConfig) -> ProcessingResult:
    if config.input_kind == "diagnostic_tmax":
        wrf = read_wrf_tmax_diagnostics(
            config.wrf_input,
            variable=config.variable,
            coord_source=config.coord_source,
            rebuild_start=config.rebuild_start,
            time_step_days=config.time_step_days,
            drop_initial_frames=config.drop_initial_frames,
            time_offset_hours=config.time_offset_hours,
            local_day_boundary_hour=config.local_day_boundary_hour,
            drop_incomplete_start_day=config.drop_incomplete_start_day,
            file_pattern=config.file_pattern,
        )
    elif config.input_kind == "hourly_t2":
        wrf = read_wrf_hourly_t2_as_daily_tmax(
            config.wrf_input,
            variable=config.variable,
            coord_source=config.coord_source,
            time_offset_hours=config.time_offset_hours,
            local_day_boundary_hour=config.local_day_boundary_hour,
            drop_incomplete_start_day=config.drop_incomplete_start_day,
            drop_incomplete_end_day=config.drop_incomplete_end_day,
            file_pattern=config.file_pattern,
        )
    else:
        raise ValueError(f"Unsupported input_kind: {config.input_kind}")

    wrf = _filter_wrf_validation_window(wrf, config.validation_start, config.validation_end)
    observed = read_china_daily_temperature(_temperature_files(config.observed_dir))
    if config.date_match == "exact":
        observed = observed[observed["date"].isin(wrf.dates)].copy()
    elif config.date_match == "month_day":
        month_days = {(day.month, day.day) for day in wrf.dates}
        observed = observed[
            pd.to_datetime(observed["date"]).apply(lambda value: (value.month, value.day) in month_days)
        ].copy()
    else:
        raise ValueError(f"Unsupported date_match: {config.date_match}")
    observed = filter_points_by_boundary(observed, config.boundary)
    if observed.empty:
        raise ValueError("No observed station records remain after date and boundary filtering.")

    station_index = _build_station_grid_index(observed, wrf.lat, wrf.lon)
    sampled = _sample_wrf_for_stations(wrf.dates, wrf.tmax_c, station_index)
    matched = merge_observed_and_sampled(observed, sampled, mode=config.date_match)
    matched = matched.dropna(subset=["tmax_obs_c", "tmax_wrf_c"]).copy()
    if matched.empty:
        raise ValueError("No matched station-date pairs were available after WRF sampling.")
    matched["error_c"] = matched["tmax_wrf_c"] - matched["tmax_obs_c"]

    selected_metrics = normalize_metric_names(config.score_metrics)
    overall_metrics = compute_metrics(matched["tmax_obs_c"].to_numpy(), matched["tmax_wrf_c"].to_numpy())
    overall_metrics["score"] = score_from_metrics(overall_metrics, selected_metrics=selected_metrics)
    overall_metrics["scheme_name"] = _scheme_name(config)
    overall_metrics["input_kind"] = config.input_kind
    overall_metrics["validation_start"] = config.validation_start
    overall_metrics["validation_end"] = config.validation_end
    overall_metrics["score_metrics"] = ",".join(selected_metrics)
    overall = pd.DataFrame([overall_metrics])
    daily = _metrics_frame(matched.groupby("date"), ["date"], selected_metrics).sort_values("date")
    station = _metrics_frame(matched.groupby("station_id"), ["station_id"], selected_metrics).sort_values("score", ascending=False)
    daily.insert(0, "scheme_name", _scheme_name(config))
    station.insert(0, "scheme_name", _scheme_name(config))

    table_dir = config.output_dir / "tables"
    matched_path = table_dir / "matched_station_daily_tmax.csv"
    overall_score_path = table_dir / "overall_score.csv"
    daily_score_path = table_dir / "daily_scores.csv"
    station_score_path = table_dir / "station_scores.csv"
    _write_csv(matched, matched_path)
    _write_csv(overall, overall_score_path)
    _write_csv(daily, daily_score_path)
    _write_csv(station, station_score_path)

    report_path = config.report_dir / "wrf_tmax_evaluation_report.md"
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
    }
    _write_report(config, context, overall_metrics, daily, station, report_path)

    return ProcessingResult(
        matched_path=matched_path,
        overall_score_path=overall_score_path,
        daily_score_path=daily_score_path,
        station_score_path=station_score_path,
        report_path=report_path,
        matched_rows=len(matched),
        station_count=station_index["station_id"].nunique(),
        date_count=len(wrf.dates),
        overall_metrics=overall_metrics,
    )
