from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd


def add_scheme_parts(frame: pd.DataFrame) -> pd.DataFrame:
    """Add longwave and shortwave scheme labels parsed from names like lw4-sw2."""
    out = frame.copy()
    lw_values = []
    sw_values = []
    for _, row in out.iterrows():
        name = str(row.get("scheme_name") or row.get("output_name") or "")
        match = re.search(r"(lw[^-_]+)[-_](sw[^-_]+)", name, flags=re.IGNORECASE)
        if match:
            lw_values.append(match.group(1).lower())
            sw_values.append(match.group(2).lower())
        else:
            lw_values.append("")
            sw_values.append("")
    out["lw_scheme"] = lw_values
    out["sw_scheme"] = sw_values
    return out


def rank_schemes(frame: pd.DataFrame) -> pd.DataFrame:
    """Rank schemes by score, then error/correlation tie-breakers."""
    ranked = add_scheme_parts(frame)
    for column in ["score", "rmse", "mae", "pcc", "bias", "normalized_crmse", "rsd"]:
        if column in ranked.columns:
            ranked[column] = pd.to_numeric(ranked[column], errors="coerce")
    if "bias" in ranked.columns:
        ranked["abs_bias"] = ranked["bias"].abs()
    sort_columns = [
        column
        for column in ["score", "rmse", "mae", "abs_bias", "normalized_crmse", "pcc"]
        if column in ranked.columns
    ]
    ascending = [False if column in {"score", "pcc"} else True for column in sort_columns]
    ranked = ranked.sort_values(sort_columns, ascending=ascending).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    return ranked


def collect_overall_scores(output_root: Path, scheme_outputs: list[str] | None = None) -> pd.DataFrame:
    if scheme_outputs:
        files = [output_root / scheme / "tables" / "overall_score.csv" for scheme in scheme_outputs]
    else:
        files = sorted(output_root.glob("*/tables/overall_score.csv"))
    rows = []
    for file in files:
        if not file.exists():
            continue
        frame = pd.read_csv(file)
        if frame.empty:
            continue
        row = frame.iloc[0].to_dict()
        row["output_name"] = file.parents[1].name
        row["overall_score_path"] = str(file)
        if not row.get("scheme_name"):
            row["scheme_name"] = file.parents[1].name
        rows.append(row)
    if not rows:
        raise FileNotFoundError(f"No overall_score.csv files found under {output_root}.")
    return pd.DataFrame(rows)


def frame_to_markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
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


def write_comparison_outputs(ranked: pd.DataFrame, output_dir: Path, report_dir: Path) -> tuple[Path, Path]:
    """Write comparison CSV and a readable Markdown report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "scheme_comparison.csv"
    report_path = report_dir / "scheme_comparison_report.md"
    ranked.to_csv(csv_path, index=False, encoding="utf-8-sig")
    best = ranked.iloc[0]
    display_columns = [
        column
        for column in [
            "rank",
            "scheme_name",
            "lw_scheme",
            "sw_scheme",
            "output_name",
            "input_kind",
            "validation_start",
            "validation_end",
            "n",
            "score",
            "pcc",
            "bias",
            "mae",
            "rmse",
            "normalized_crmse",
            "rsd",
        ]
        if column in ranked.columns
    ]
    lines = [
        "# WRF 参数化方案评分对比",
        "",
        "## 最佳方案",
        "",
        f"- 最佳方案：`{best.get('scheme_name', best.get('output_name'))}`",
        f"- 综合评分：`{float(best['score']):.4f}`",
        "",
        "排序规则：优先按综合评分降序；若接近或相同，再参考 RMSE、MAE、绝对 bias、Normalized cRMSE 较小和 PCC 较高。",
        "",
        "## 方案排序",
        "",
        frame_to_markdown_table(ranked[display_columns]),
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8-sig")
    return csv_path, report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare WRF scheme overall score tables and select the best scheme.")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"))
    parser.add_argument("--schemes", default=None, help="Comma-separated output folder names to compare.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/scheme-comparison/tables"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports/scheme-comparison"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scheme_outputs = [item.strip() for item in args.schemes.split(",")] if args.schemes else None
    scores = collect_overall_scores(args.output_root, scheme_outputs)
    ranked = rank_schemes(scores)
    csv_path, report_path = write_comparison_outputs(ranked, args.output_dir, args.report_dir)
    best = ranked.iloc[0]
    print(f"best_scheme={best.get('scheme_name', best.get('output_name'))}")
    print(f"best_score={float(best['score']):.4f}")
    print(f"comparison={csv_path}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
