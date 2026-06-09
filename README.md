# WRF Learning Evaluation Toolkit

This project contains a reusable Python pipeline for WRF diagnostic post-processing and station-based verification.

## Structure

- `data/`: input data, including WRF diagnostics, station observations, and boundary files.
- `src/wrf_eval/`: reusable processing package.
- `tests/`: unit tests for parsing, metrics, and grid sampling.
- `outputs/tables/`: generated score tables and matched samples.
- `reports/`: generated processing reports.

## Environment

Use the existing conda environment:

```powershell
conda run -n geocompy python -c "import numpy, pandas, geopandas, netCDF4"
```

## Run

```powershell
$env:PYTHONPATH='src'
conda run -n geocompy python -m wrf_eval.cli
```

The default run reads `data/wrfout/wrf_tmax_tmin_d01_2010-05-01_00_00_00` as a WRF diagnostic file and evaluates `T2MAX` against China daily station temperature observations.
