from __future__ import annotations

import argparse
from pathlib import Path

from wrf_eval.pipeline import ProcessingConfig, run_processing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate WRF diagnostic daily maximum temperature against station observations.")
    parser.add_argument("--wrf-input", type=Path, default=Path("data/wrfout/wrf_tmax_tmin_d01_2010-05-01_00_00_00"))
    parser.add_argument("--observed-dir", type=Path, default=Path("data/observed"))
    parser.add_argument("--boundary", type=Path, default=Path("data/boundary/Yangtze.shp"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    parser.add_argument("--variable", default="T2MAX")
    parser.add_argument("--coord-source", type=Path, default=None)
    parser.add_argument("--rebuild-start", default=None, help="Rebuild regular dates from this start date, e.g. 2020-05-01.")
    parser.add_argument("--time-step-days", type=int, default=1)
    parser.add_argument("--drop-initial-frames", type=int, default=0)
    parser.add_argument("--time-offset-hours", type=int, default=0, help="Shift WRF UTC timestamps by this many hours before date matching.")
    parser.add_argument(
        "--local-day-boundary-hour",
        type=int,
        default=None,
        help="Assign local timestamps to station-day dates using this local boundary hour, e.g. 20 for Beijing 20:00 day boundary.",
    )
    parser.add_argument(
        "--drop-incomplete-start-day",
        action="store_true",
        help="Drop the first shifted local date when the first WRF timestamp is not local midnight.",
    )
    parser.add_argument("--date-match", choices=["exact", "month_day"], default="exact")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = ProcessingConfig(
        wrf_input=args.wrf_input,
        observed_dir=args.observed_dir,
        boundary=args.boundary if args.boundary else None,
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        variable=args.variable,
        coord_source=args.coord_source,
        rebuild_start=args.rebuild_start,
        time_step_days=args.time_step_days,
        drop_initial_frames=args.drop_initial_frames,
        time_offset_hours=args.time_offset_hours,
        local_day_boundary_hour=args.local_day_boundary_hour,
        drop_incomplete_start_day=args.drop_incomplete_start_day,
        date_match=args.date_match,
    )
    result = run_processing(config)
    print(f"matched_rows={result.matched_rows}")
    print(f"station_count={result.station_count}")
    print(f"date_count={result.date_count}")
    print(f"overall_score={result.overall_metrics.get('score'):.4f}")
    print(f"overall_pcc={result.overall_metrics.get('pcc'):.4f}")
    print(f"overall_rmse={result.overall_metrics.get('rmse'):.4f}")
    print(f"overall_mae={result.overall_metrics.get('mae'):.4f}")
    print(f"overall_rsd={result.overall_metrics.get('rsd'):.4f}")
    print(f"report={result.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
