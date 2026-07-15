# WRF Station Verification Toolkit

Version: v1.1.1

This project provides a configuration-driven Python toolkit for verifying WRF `wrfout` simulations against Chinese meteorological station daily observations. It is intended for reproducible batch evaluation of parameterization experiments, especially experiment folders named like `lw4-sw2`, where `lw` denotes the longwave radiation scheme and `sw` denotes the shortwave radiation scheme.

## Scope

- Input type: WRF `wrfout` files only.
- Observation type: Chinese station daily data.
- Time handling: WRF UTC timestamps are converted to Beijing time UTC+8.
- Station-day boundary: Beijing time 20:00.
- Fixed metrics: `PCC`, `bias`, `MAE`, `RMSE`, `Normalized cRMSE`, `RSD`.
- Supported validation variables: `Tmax`, `T2`, and `RH`.
- Output root: all CSV tables and Markdown reports are written under `outputs/runs/<run_id>/`.

Variable rules:

- `Tmax`: daily maximum 2 m temperature aggregated from hourly `T2`, compared with station `tmax_obs_c`.
- `T2`: daily mean 2 m temperature aggregated from hourly `T2`, compared with station `tmean_obs_c`.
- `RH`: daily mean 2 m relative humidity read from `RH2` or `RH`, or calculated from `T2 + Q2 + PSFC`, compared with station RHU observations.

## Repository Layout

- `configs/`: YAML run configurations.
- `src/wrf_eval/`: Python package and CLI implementation.
- `tests/`: unit tests.
- `scripts/`: portable command examples.
- `docs/`: user-facing feature notes and release notes.
- `data/`: local input data location. This directory is ignored by Git.
- `outputs/`: generated results. This directory is ignored by Git.
- `reports/`: legacy or local reports. This directory is ignored by Git.

Large WRF outputs, station observations, boundaries, and generated verification reports should not be committed to the public repository.

## Environment

The recommended conda environment name is `wrfpy`:

```powershell
conda env create -f environment.yml
conda activate wrfpy
```

To verify the core dependencies:

```powershell
conda run -n wrfpy python -c "import numpy, pandas, geopandas, netCDF4"
```

## Example Workspace

Use a generic project location such as:

```powershell
cd D:/wrf/wrf-station-verification
$env:PYTHONPATH = "src"
```

Recommended data layout:

```text
data/
  wrfout/
    lw1-sw1/
      wrfout_d01_2020-06-01_00_00_00
    lw4-sw2/
      wrfout_d01_2020-06-01_00_00_00
  observed/
    SURF_CLI_CHN_MUL_DAY-TEM-*.TXT
    SURF_CLI_CHN_MUL_DAY-RHU-*.TXT
  boundary/
    study_area.shp
```

## Basic Usage

Inspect configured schemes and data readiness:

```powershell
conda run -n wrfpy python -m wrf_eval.cli inspect --config configs/tmax_validation.yaml
```

Run batch verification:

```powershell
conda run -n wrfpy python -m wrf_eval.cli run --config configs/tmax_validation.yaml
```

Compare existing scheme scores:

```powershell
conda run -n wrfpy python -m wrf_eval.cli compare --config configs/tmax_validation.yaml
```

## Minimal Configuration

```yaml
version: 1
wrf:
  input_root: data/wrfout
  schemes: auto
  file_patterns:
    - "wrfout_d0*"
observed:
  data_dir: data/observed
  boundary: data/boundary/study_area.shp
validation:
  variable: Tmax
  start: "06-01"
  end: "10-01"
output:
  root: outputs/runs
```

The public interface intentionally does not expose input-kind, report-dir, score-metric, time-offset, or day-boundary options. These are fixed defaults in v1.1.x.

## Outputs

Default run ids are derived from the selected variable:

```text
wrf_tmax_station_validation
wrf_t2_station_validation
wrf_rh_station_validation
```

Generated files:

```text
outputs/runs/<run_id>/<scheme>/tables/overall_score.csv
outputs/runs/<run_id>/<scheme>/tables/daily_scores.csv
outputs/runs/<run_id>/<scheme>/tables/station_scores.csv
outputs/runs/<run_id>/<scheme>/tables/excluded_days.csv
outputs/runs/<run_id>/<scheme>/reports/wrf_<variable>_evaluation_report.md
outputs/runs/<run_id>/scheme-comparison/scheme_comparison.csv
outputs/runs/<run_id>/scheme-comparison/scheme_comparison_report.md
```

`excluded_days.csv` records dates removed because they are outside the validation window or do not contain a complete station-day.

## Tests

```powershell
$env:PYTHONPATH = "src"
conda run -n wrfpy python -m unittest discover -s tests
```
