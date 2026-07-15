from __future__ import annotations

import argparse
import sys
from pathlib import Path

from netCDF4 import Dataset

from wrf_eval.batch import run_batch_from_config_path
from wrf_eval.compare_schemes import collect_overall_scores, rank_schemes, write_comparison_outputs
from wrf_eval.config import FIXED_SCORE_METRICS, ScoreToolConfig, discover_schemes, load_score_config
from wrf_eval.wrf_hourly import DEFAULT_LOCAL_DAY_BOUNDARY_HOUR, DEFAULT_TIME_OFFSET_HOURS


def build_tool_parser() -> argparse.ArgumentParser:
    """Build the v1.1 configuration-driven CLI parser."""
    parser = argparse.ArgumentParser(prog="wrf-score", description="WRF wrfout station verification tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run all schemes defined by a YAML config.")
    run_parser.add_argument("--config", type=Path, required=True, help="YAML config file.")

    compare_parser = subparsers.add_parser("compare", help="Compare existing per-scheme overall score tables.")
    compare_parser.add_argument("--config", type=Path, default=None, help="Optional YAML config used to derive roots and run id.")
    compare_parser.add_argument("--run-id", default=None, help="Run id under the output root. Defaults to config output.run_id.")
    compare_parser.add_argument("--output-root", type=Path, default=Path("outputs/runs"), help="Root containing run output folders.")
    compare_parser.add_argument("--schemes", default=None, help="Comma-separated scheme names to compare.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect scheme discovery, wrfout variables, and observation files.")
    inspect_parser.add_argument("--config", type=Path, required=True, help="YAML config file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_tool_command(list(sys.argv[1:] if argv is None else argv))


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

    output_root = (config.output.root if config else args.output_root) / run_id
    scheme_names = [item.strip() for item in args.schemes.split(",")] if args.schemes else None
    scores = collect_overall_scores(output_root, scheme_names)
    ranked = rank_schemes(scores)
    csv_path, report_path = write_comparison_outputs(ranked, output_dir=output_root / "scheme-comparison")
    best = ranked.iloc[0]
    print(f"best_scheme={best.get('scheme_name', best.get('output_name'))}")
    print(f"best_score={float(best['score']):.4f}")
    print(f"comparison={csv_path}")
    print(f"report={report_path}")
    return 0


def run_inspect_command(args: argparse.Namespace) -> int:
    config = load_score_config(args.config)
    schemes = discover_schemes(config)
    print(f"run_id={config.run_id}")
    print(f"variable={config.validation.variable}")
    print(f"input_type=wrfout")
    print(f"time_handling=UTC+{DEFAULT_TIME_OFFSET_HOURS},day_boundary={DEFAULT_LOCAL_DAY_BOUNDARY_HOUR}:00 Beijing time")
    print(f"metrics={','.join(FIXED_SCORE_METRICS)}")
    print(f"required_wrf_variables={_required_wrf_variables(config.validation.variable)}")
    print(_observation_status(config))
    for scheme in schemes:
        print(f"scheme={scheme.name}\tpath={scheme.path}\tfile_pattern={scheme.file_pattern}")
        print(f"wrf_status={_wrf_status(scheme.path, scheme.file_pattern, config.validation.variable)}")
    return 0


def _required_wrf_variables(variable: str) -> str:
    if variable in {"T2", "Tmax"}:
        return "T2"
    return "RH2 or RH or T2+Q2+PSFC"


def _observation_status(config: ScoreToolConfig) -> str:
    if config.validation.variable == "RH":
        pattern = "SURF_CLI_CHN_MUL_DAY-RHU-*.TXT"
        label = "RHU"
    else:
        pattern = "SURF_CLI_CHN_MUL_DAY-TEM-*.TXT"
        label = "TEM"
    files = sorted(config.observed.data_dir.glob(f"**/{pattern}"))
    return f"observed_{label.lower()}_files={len(files)}\tpattern={pattern}"


def _wrf_status(path: Path, file_pattern: str | None, variable: str) -> str:
    matches = _matched_files(path, file_pattern)
    if not matches:
        return "missing:no_matching_wrfout_files"
    try:
        with Dataset(matches[0]) as ds:
            variables = set(ds.variables.keys())
            if variable in {"T2", "Tmax"}:
                missing = [] if "T2" in variables else ["T2"]
            else:
                has_direct = "RH2" in variables or "RH" in variables
                has_computable = {"T2", "Q2", "PSFC"}.issubset(variables)
                missing = [] if has_direct or has_computable else ["RH2/RH or T2+Q2+PSFC"]
            if missing:
                return f"missing:{','.join(missing)}\tmatches={len(matches)}\tfirst_file={matches[0]}"
            return f"ok\tmatches={len(matches)}\tfirst_file={matches[0]}"
    except OSError as exc:
        return f"unreadable:{exc}\tmatches={len(matches)}\tfirst_file={matches[0]}"


def _matched_files(path: Path, file_pattern: str | None) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    pattern = file_pattern or "wrfout_d0*"
    return sorted(item for item in path.glob(pattern) if item.is_file())


if __name__ == "__main__":
    raise SystemExit(main())
