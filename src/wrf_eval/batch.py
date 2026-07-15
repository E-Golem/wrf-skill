from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable

from wrf_eval.compare_schemes import collect_overall_scores, rank_schemes, write_comparison_outputs
from wrf_eval.config import SchemeInput, ScoreToolConfig, discover_schemes, load_score_config
from wrf_eval.pipeline import ProcessingConfig, ProcessingResult, run_processing


@dataclass(frozen=True)
class SchemeRunResult:
    scheme: SchemeInput
    result: ProcessingResult | None
    error: str | None = None


@dataclass(frozen=True)
class BatchRunResult:
    run_id: str
    output_root: Path
    scheme_results: tuple[SchemeRunResult, ...]
    comparison_csv: Path | None
    comparison_report: Path | None

    @property
    def successful_scheme_names(self) -> list[str]:
        return [item.scheme.name for item in self.scheme_results if item.result is not None]

    @property
    def failed_scheme_names(self) -> list[str]:
        return [item.scheme.name for item in self.scheme_results if item.result is None]


ProgressCallback = Callable[[str], None]


def run_batch_from_config_path(path: Path | str, progress_callback: ProgressCallback | None = None) -> BatchRunResult:
    """Load a YAML config and run the configured WRF scoring batch."""
    return run_batch(load_score_config(path), progress_callback=progress_callback)


def run_batch(config: ScoreToolConfig, progress_callback: ProgressCallback | None = None) -> BatchRunResult:
    """Run all configured schemes and generate a scheme comparison report."""
    schemes = discover_schemes(config)
    run_output_root = config.output.root / config.run_id
    scheme_results: list[SchemeRunResult] = []

    _emit(progress_callback, f"[1/3] Discovered {len(schemes)} scheme(s) for run '{config.run_id}'.")
    for index, scheme in enumerate(schemes, start=1):
        started_at = perf_counter()
        _emit(progress_callback, f"[2/3] ({index}/{len(schemes)}) Evaluating scheme '{scheme.name}'...")
        processing_config = processing_config_for_scheme(config, scheme)
        try:
            result = run_processing(processing_config)
        except Exception as exc:
            if not config.continue_on_error:
                raise
            scheme_results.append(SchemeRunResult(scheme=scheme, result=None, error=str(exc)))
            elapsed = perf_counter() - started_at
            _emit(progress_callback, f"[2/3] ({index}/{len(schemes)}) Failed '{scheme.name}' after {elapsed:.1f}s: {exc}")
        else:
            scheme_results.append(SchemeRunResult(scheme=scheme, result=result))
            elapsed = perf_counter() - started_at
            _emit(
                progress_callback,
                f"[2/3] ({index}/{len(schemes)}) Completed '{scheme.name}' in {elapsed:.1f}s; "
                f"matched_rows={result.matched_rows}, excluded_days={result.excluded_day_count}, "
                f"score={result.overall_metrics.get('score'):.4f}.",
            )

    successful_names = [item.scheme.name for item in scheme_results if item.result is not None]
    if not successful_names:
        raise RuntimeError("No schemes completed successfully; comparison cannot be generated.")

    _emit(progress_callback, f"[3/3] Building comparison report for {len(successful_names)} successful scheme(s)...")
    ranked = rank_schemes(collect_overall_scores(run_output_root, successful_names))
    comparison_csv, comparison_report = write_comparison_outputs(
        ranked,
        output_dir=run_output_root / "scheme-comparison",
    )
    best = ranked.iloc[0]
    _emit(
        progress_callback,
        f"[3/3] Best scheme: {best.get('scheme_name', best.get('output_name'))}; score={float(best['score']):.4f}.",
    )

    return BatchRunResult(
        run_id=config.run_id,
        output_root=run_output_root,
        scheme_results=tuple(scheme_results),
        comparison_csv=comparison_csv,
        comparison_report=comparison_report,
    )


def processing_config_for_scheme(config: ScoreToolConfig, scheme: SchemeInput) -> ProcessingConfig:
    """Build the single-scheme processing config for one discovered scheme."""
    return ProcessingConfig(
        wrf_input=scheme.path,
        observed_dir=config.observed.data_dir,
        boundary=config.observed.boundary,
        output_dir=config.output.root / config.run_id / scheme.name,
        scheme_name=scheme.name,
        variable=config.validation.variable,
        file_pattern=scheme.file_pattern,
        coord_source=config.wrf.coord_source,
        validation_start=config.validation.start,
        validation_end=config.validation.end,
    )


def _emit(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)
