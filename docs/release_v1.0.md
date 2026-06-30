# WRF Tmax Station Verification Toolkit v1.0

Release tag: `v1.0`

## Summary

v1.0 is the first stable engineering release of the WRF Tmax station verification toolkit. It provides a YAML-driven command line workflow for batch scoring and comparison of WRF longwave/shortwave radiation parameterization experiments.

## Scope

This release is limited to:

- Longwave radiation scheme and shortwave radiation scheme sensitivity experiments.
- Daily maximum temperature verification.
- Chinese ground meteorological station daily temperature observations.
- Station-to-WRF nearest-grid matching.
- CSV tables and Markdown reports.

## Main Features

- YAML configuration for repeatable runs.
- Automatic scheme discovery under `data/wrfout`.
- Support for `T2_output*.nc` and `T2_out*.nc`.
- UTC to Beijing time conversion.
- Beijing 20:00 station-day boundary handling.
- Validation window selection, for example `06-01` to `10-01`.
- Metrics: `PCC`, `bias`, `MAE`, `RMSE`, `Normalized cRMSE`, `RSD`.
- Composite score and automatic best-scheme ranking.
- Progress messages during batch runs.
- Generic output paths:

```text
outputs/runs/wrf_tmax_station_validation/
reports/runs/wrf_tmax_station_validation/
```

## Not Included

- Heatwave event verification metrics.
- Variables other than Tmax.
- Observation formats outside the current China station daily temperature format.
- Gridded observation or reanalysis validation.
- Web UI or dashboard.
- Automatic WRF simulation execution.

## Basic Usage

```powershell
cd D:\文档\wrf_learning
$env:PYTHONPATH='src'
conda run -n geocompy python -m wrf_eval.cli inspect --config configs/tmax_validation.yaml
conda run -n geocompy python -m wrf_eval.cli run --config configs/tmax_validation.yaml
```

## Verification

Before release, run:

```powershell
$env:PYTHONPATH='src'
conda run -n geocompy python -m unittest discover -s tests
```
