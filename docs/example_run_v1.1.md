# Example Run for v1.1.x

This example uses portable paths and the recommended `wrfpy` conda environment.

## 1. Prepare Environment

```powershell
cd D:/wrf/wrf-station-verification
$env:PYTHONPATH = "src"
conda run -n wrfpy python -c "import wrf_eval; print(wrf_eval.__version__)"
```

For this release line, the expected version is `1.1.1` or newer.

## 2. Prepare Data

Recommended layout:

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

`Tmax` and `T2` require TEM observation files. `RH` requires RHU observation files and wrfout variables `RH2`, `RH`, or `T2 + Q2 + PSFC`.

## 3. Configure Variable and Window

Open `configs/tmax_validation.yaml` and adjust:

```yaml
validation:
  variable: Tmax
  start: "06-01"
  end: "10-01"
```

Use `T2` for daily mean 2 m temperature or `RH` for daily mean 2 m relative humidity.

## 4. Inspect Inputs

```powershell
conda run -n wrfpy python -m wrf_eval.cli inspect --config configs/tmax_validation.yaml
```

The command reports run id, variable, required wrfout variables, observation file counts, and per-scheme wrfout readiness.

## 5. Run Batch Evaluation

```powershell
conda run -n wrfpy python -m wrf_eval.cli run --config configs/tmax_validation.yaml
```

The command prints progress for scheme discovery, each scheme evaluation, excluded-day counts, matched rows, and best-scheme selection.

## 6. Review Outputs

Default `Tmax` outputs are written under:

```text
outputs/runs/wrf_tmax_station_validation/
```

Check these files first:

```text
<scheme>/tables/overall_score.csv
<scheme>/tables/excluded_days.csv
<scheme>/reports/wrf_tmax_evaluation_report.md
scheme-comparison/scheme_comparison.csv
scheme-comparison/scheme_comparison_report.md
```

## 7. Compare Existing Outputs Only

```powershell
conda run -n wrfpy python -m wrf_eval.cli compare --config configs/tmax_validation.yaml
```
