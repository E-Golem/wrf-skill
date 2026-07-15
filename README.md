# WRF Station Verification Toolkit

Version: v1.1.0

This project provides a configuration-driven Python tool for verifying WRF `wrfout` simulations against Chinese meteorological station daily observations. It is designed for batch comparison of parameterization experiments, especially folders named like `lw4-sw2` where `lw` is the longwave radiation scheme and `sw` is the shortwave radiation scheme.

## v1.1 Scope

- Input type is fixed to WRF `wrfout` structure.
- Observation type is fixed to Chinese station daily data.
- Time handling is fixed: WRF UTC timestamps are converted to Beijing time UTC+8.
- Station daily boundary is fixed at Beijing time 20:00.
- Metrics are fixed: `PCC`, `bias`, `MAE`, `RMSE`, `Normalized cRMSE`, `RSD`.
- Supported validation variables are `Tmax`, `T2`, and `RH`.
- `Tmax` is aggregated from hourly `T2` as daily maximum 2 m temperature and compared with `tmax_obs_c`.
- `T2` is aggregated from hourly `T2` as daily mean 2 m temperature and compared with `tmean_obs_c`.
- `RH` is read from `RH2` or `RH`, or calculated from `T2 + Q2 + PSFC`, then aggregated as daily mean relative humidity and compared with RHU station observations.
- Only complete station-days inside the validation window are scored. Removed dates are written to `excluded_days.csv`.

Current limitations:

- Validation is currently station-based; gridded observations and reanalysis products are not included.
- The local sample data does not include RHU observations or full RH/Q2/PSFC wrfout variables, so RH capability requires additional data.
- Nearest-grid-cell station sampling is used in v1.1. Bilinear interpolation and elevation correction are later extension points.

## Project Structure

- `configs/`: YAML run configurations.
- `src/wrf_eval/`: reusable Python package and CLI.
- `tests/`: unit tests.
- `outputs/runs/`: generated CSV tables and Markdown reports.
- `docs/`: feature notes, release notes, and example run documentation.

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

Inspect configured schemes and input readiness:

```powershell
conda run -n geocompy python -m wrf_eval.cli inspect --config configs/tmax_validation.yaml
```

Run batch evaluation:

```powershell
conda run -n geocompy python -m wrf_eval.cli run --config configs/tmax_validation.yaml
```

Compare existing scheme scores:

```powershell
conda run -n geocompy python -m wrf_eval.cli compare --config configs/tmax_validation.yaml
```

## Configuration

Minimal v1.1 config:

```yaml
version: 1
wrf:
  input_root: data/wrfout
  schemes: auto
  file_patterns:
    - "wrfout_d0*"
observed:
  data_dir: data/observed
  boundary: data/boundary/Yangtze.shp
validation:
  variable: Tmax
  start: "06-01"
  end: "10-01"
output:
  root: outputs/runs
```

The old public fields `input-kind`, `report-dir`, `score-metrics`, time offset, and day-boundary options are intentionally removed in v1.1.

## Outputs

The default run id is derived from the validation variable:

```text
wrf_tmax_station_validation
wrf_t2_station_validation
wrf_rh_station_validation
```

Generated outputs are written to one merged output tree:

```text
outputs/runs/<run_id>/<scheme>/tables/overall_score.csv
outputs/runs/<run_id>/<scheme>/tables/daily_scores.csv
outputs/runs/<run_id>/<scheme>/tables/station_scores.csv
outputs/runs/<run_id>/<scheme>/tables/excluded_days.csv
outputs/runs/<run_id>/<scheme>/reports/wrf_<variable>_evaluation_report.md
outputs/runs/<run_id>/scheme-comparison/scheme_comparison.csv
outputs/runs/<run_id>/scheme-comparison/scheme_comparison_report.md
```

## Tests

```powershell
$env:PYTHONPATH='src'
conda run -n geocompy python -m unittest discover -s tests
```
