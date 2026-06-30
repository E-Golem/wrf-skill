# WRF Tmax Station Verification Toolkit

Version: v1.0

This project provides a configuration-driven Python tool for WRF daily maximum temperature verification against Chinese meteorological station observations. It is designed for batch comparison of WRF parameterization experiments, especially folders named like `lw4-sw2`.

## v1.0 Scope

This release is intentionally narrow and reproducible:

- Only compares experiments formed by changing longwave radiation (`lw`) and shortwave radiation (`sw`) schemes.
- Only validates daily maximum temperature (`Tmax`).
- Currently supports station-observation verification for Chinese ground meteorological daily temperature data.
- Current spatial matching uses nearest WRF grid cell to station location.
- Current outputs are CSV tables and Markdown reports.
- Heatwave-event metrics, gridded observations, reanalysis verification, other countries' station formats, and web visualization are not included in v1.0.

## Project Structure

- `configs/`: YAML run configurations.
- `src/wrf_eval/`: reusable Python package and CLI.
- `tests/`: unit tests.
- `outputs/runs/`: generated CSV outputs.
- `reports/runs/`: generated Markdown reports.
- `docs/`: design notes, release notes, and example run documentation.

Large WRF files and station data should stay under `data/` and are not intended to be published to GitHub.

## Environment

Use the existing conda environment:

```powershell
conda run -n geocompy python -c "import numpy, pandas, geopandas, netCDF4"
```

If rebuilding the environment, use:

```powershell
conda env update -f environment.yml
```

## Recommended Workflow

Set the source path:

```powershell
cd D:\文档\wrf_learning
$env:PYTHONPATH='src'
```

Inspect which schemes will be evaluated:

```powershell
conda run -n geocompy python -m wrf_eval.cli inspect --config configs/tmax_validation.yaml
```

Run the full batch evaluation:

```powershell
conda run -n geocompy python -m wrf_eval.cli run --config configs/tmax_validation.yaml
```

The `run` command shows progress while processing each scheme.

## Default Output Names

The default run id is now generic:

```text
wrf_tmax_station_validation
```

Generated outputs are written to:

```text
outputs/runs/wrf_tmax_station_validation/
reports/runs/wrf_tmax_station_validation/
```

Important files:

```text
outputs/runs/wrf_tmax_station_validation/<scheme>/tables/overall_score.csv
outputs/runs/wrf_tmax_station_validation/<scheme>/tables/daily_scores.csv
outputs/runs/wrf_tmax_station_validation/<scheme>/tables/station_scores.csv
outputs/runs/wrf_tmax_station_validation/scheme-comparison/scheme_comparison.csv
reports/runs/wrf_tmax_station_validation/<scheme>/wrf_tmax_evaluation_report.md
reports/runs/wrf_tmax_station_validation/scheme-comparison/scheme_comparison_report.md
```

## Default Metrics

The default composite score uses:

- `PCC`
- `bias`
- `MAE`
- `RMSE`
- `Normalized cRMSE`
- `RSD`

The composite score is for fast scheme ranking. Scientific interpretation should still inspect the individual metrics.

## Legacy Single-Scheme CLI

The earlier one-scheme command remains supported:

```powershell
conda run -n geocompy python -m wrf_eval.cli `
  --wrf-input "data/wrfout/lw4-sw2" `
  --scheme-name "lw4-sw2" `
  --input-kind "hourly_t2" `
  --file-pattern "T2_output*.nc" `
  --observed-dir "data/observed" `
  --boundary "data/boundary/Yangtze.shp" `
  --output-dir "outputs/lw4-sw2-hourly-t2" `
  --report-dir "reports/lw4-sw2-hourly-t2" `
  --variable "T2" `
  --time-offset-hours 8 `
  --local-day-boundary-hour 20 `
  --drop-incomplete-start-day `
  --drop-incomplete-end-day `
  --validation-start "06-01" `
  --validation-end "10-01" `
  --score-metrics "pcc,bias,mae,rmse,normalized_crmse,rsd"
```

For v1.0 and later work, prefer the YAML batch workflow.

## Tests

```powershell
$env:PYTHONPATH='src'
conda run -n geocompy python -m unittest discover -s tests
```
