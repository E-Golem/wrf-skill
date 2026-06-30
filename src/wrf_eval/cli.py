from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wrf_eval.batch import run_batch_from_config_path
from wrf_eval.compare_schemes import collect_overall_scores, rank_schemes, write_comparison_outputs
from wrf_eval.config import ScoreToolConfig, discover_schemes, load_score_config
from wrf_eval.pipeline import ProcessingConfig, run_processing


def build_parser() -> argparse.ArgumentParser:
    """Build the legacy single-scheme parser kept for existing scripts."""
    parser = argparse.ArgumentParser(description="Evaluate WRF diagnostic daily maximum temperature against station observations.")
    parser.add_argument("--wrf-input", type=Path, default=Path("data/wrfout/wrf_tmax_tmin_d01_2010-05-01_00_00_00"))
    parser.add_argument("--observed-dir", type=Path, default=Path("data/observed"))
    parser.add_argument("--boundary", type=Path, default=Path("data/boundary/Yangtze.shp"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    parser.add_argument("--scheme-name", default=None, help="Parameterization scheme name written to reports and output tables.")
    parser.add_argument("--variable", default="T2MAX")
    parser.add_argument("--input-kind", choices=["diagnostic_tmax", "hourly_t2"], default="diagnostic_tmax")
    parser.add_argument("--file-pattern", default=None, help="Optional glob pattern when --wrf-input is a directory.")
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
    parser.add_argument(
        "--drop-incomplete-end-day",
        action="store_true",
        help="Drop the last local date when the hourly input does not cover a full station day.",
    )
    parser.add_argument("--validation-start", default=None, help="Validation start date as MM-DD or YYYY-MM-DD, e.g. 06-01.")
    parser.add_argument("--validation-end", default=None, help="Validation end date as MM-DD or YYYY-MM-DD, e.g. 10-01.")
    parser.add_argument(
        "--score-metrics",
        default=None,
        help="Comma-separated metrics used for score, e.g. pcc,mae,rmse,normalized_crmse,rsd.",
    )
    parser.add_argument("--date-match", choices=["exact", "month_day"], default="exact")
    return parser


def build_tool_parser() -> argparse.ArgumentParser:
    """Build the configuration-driven CLI parser."""
    parser = argparse.ArgumentParser(prog="wrf-score", description="Configuration-driven WRF station verification tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run all schemes defined by a YAML config.")
    run_parser.add_argument("--config", type=Path, required=True, help="YAML config file.")

    compare_parser = subparsers.add_parser("compare", help="Compare existing per-scheme overall score tables.")
    compare_parser.add_argument("--config", type=Path, default=None, help="Optional YAML config used to derive roots and run id.")
    compare_parser.add_argument("--run-id", default=None, help="Run id under output/report roots. Defaults to config output.run_id or project.name.")
    compare_parser.add_argument("--output-root", type=Path, default=Path("outputs/runs"), help="Root containing run output folders.")
    compare_parser.add_argument("--report-root", type=Path, default=Path("reports/runs"), help="Root for comparison reports.")
    compare_parser.add_argument("--schemes", default=None, help="Comma-separated scheme names to compare.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect scheme discovery and file matching.")
    inspect_parser.add_argument("--config", type=Path, default=None, help="YAML config to inspect.")
    inspect_parser.add_argument("--wrf-input", type=Path, default=None, help="WRF file or directory to inspect without config.")
    inspect_parser.add_argument("--file-pattern", action="append", default=None, help="Glob pattern to inspect; can be repeated.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"run", "compare", "inspect"}:
        return run_tool_command(args)
    return run_legacy_command(args)


def run_legacy_command(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    config = ProcessingConfig(
        wrf_input=args.wrf_input,
        observed_dir=args.observed_dir,
        boundary=args.boundary if args.boundary else None,
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        scheme_name=args.scheme_name,
        variable=args.variable,
        input_kind=args.input_kind,
        file_pattern=args.file_pattern,
        coord_source=args.coord_source,
        rebuild_start=args.rebuild_start,
        time_step_days=args.time_step_days,
        drop_initial_frames=args.drop_initial_frames,
        time_offset_hours=args.time_offset_hours,
        local_day_boundary_hour=args.local_day_boundary_hour,
        drop_incomplete_start_day=args.drop_incomplete_start_day,
        drop_incomplete_end_day=args.drop_incomplete_end_day,
        validation_start=args.validation_start,
        validation_end=args.validation_end,
        score_metrics=args.score_metrics,
        date_match=args.date_match,
    )
    result = run_processing(config)
    _print_processing_result(result)
    return 0


def run_tool_command(argv: list[str]) -> int:
    args = build_tool_parser().parse_args(argv)
    if args.command == "run":
        result = run_batch_from_config_path(args.config, progress_callback=print)
        print(f"run_id={result.run_id}")
        print(f"successful_schemes={','.join(result.successful_scheme_names)}")
        if result.failed_scheme_names:
            print(f"failed_schemes={','.join(result.failed_scheme_names)}")
        print(f"comparison={result.comparison_csv}")
        print(f"report={result.comparison_report}")
        return 0
    if args.command == "compare":
        return run_compare_command(args)
    if args.command == "inspect":
        return run_inspect_command(args)
    raise ValueError(f"Unsupported command: {args.command}")


def run_compare_command(args: argparse.Namespace) -> int:
    config: ScoreToolConfig | None = load_score_config(args.config) if args.config else None
    run_id = args.run_id or (config.run_id if config else None)
    if not run_id:
        raise ValueError("--run-id is required when --config is not provided.")

    output_root = (config.output.output_root if config else args.output_root) / run_id
    report_root = (config.output.report_root if config else args.report_root) / run_id
    scheme_names = [item.strip() for item in args.schemes.split(",")] if args.schemes else None
    scores = collect_overall_scores(output_root, scheme_names)
    ranked = rank_schemes(scores)
    csv_path, report_path = write_comparison_outputs(
        ranked,
        output_dir=output_root / "scheme-comparison",
        report_dir=report_root / "scheme-comparison",
    )
    best = ranked.iloc[0]
    print(f"best_scheme={best.get('scheme_name', best.get('output_name'))}")
    print(f"best_score={float(best['score']):.4f}")
    print(f"comparison={csv_path}")
    print(f"report={report_path}")
    return 0


def run_inspect_command(args: argparse.Namespace) -> int:
    if args.config:
        config = load_score_config(args.config)
        schemes = discover_schemes(config)
        print(f"run_id={config.run_id}")
        for scheme in schemes:
            print(f"scheme={scheme.name}\tpath={scheme.path}\tfile_pattern={scheme.file_pattern}")
        return 0

    if args.wrf_input is None:
        raise ValueError("--wrf-input is required when --config is not provided.")
    path = args.wrf_input
    patterns = tuple(args.file_pattern or ["*"])
    if path.is_file():
        print(f"file={path}")
        return 0
    if not path.is_dir():
        raise FileNotFoundError(f"WRF input does not exist: {path}")
    for pattern in patterns:
        matches = sorted(item for item in path.glob(pattern) if item.is_file())
        print(f"pattern={pattern}\tmatches={len(matches)}")
        for match in matches:
            print(f"file={match}")
    return 0


def _print_processing_result(result) -> None:
    print(f"matched_rows={result.matched_rows}")
    print(f"station_count={result.station_count}")
    print(f"date_count={result.date_count}")
    print(f"overall_score={result.overall_metrics.get('score'):.4f}")
    print(f"overall_pcc={result.overall_metrics.get('pcc'):.4f}")
    print(f"overall_rmse={result.overall_metrics.get('rmse'):.4f}")
    print(f"overall_mae={result.overall_metrics.get('mae'):.4f}")
    print(f"overall_rsd={result.overall_metrics.get('rsd'):.4f}")
    print(f"report={result.report_path}")


if __name__ == "__main__":
    raise SystemExit(main())
