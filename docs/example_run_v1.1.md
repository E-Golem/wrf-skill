# Example Run for v1.1

## 1. Prepare Environment

```powershell
cd D:\文档\wrf_learning
$env:PYTHONPATH='src'
conda run -n geocompy python -c "import wrf_eval; print(wrf_eval.__version__)"
```

Expected version:

```text
1.1.0
```

## 2. Check Config

Open `configs/tmax_validation.yaml` and confirm:

```yaml
validation:
  variable: Tmax
  start: "06-01"
  end: "10-01"
```

For `T2`, change `variable` to `T2`. For `RH`, change it to `RH` and provide RHU station files plus wrfout files containing `RH2`, `RH`, or `T2 + Q2 + PSFC`.

## 3. Inspect Inputs

```powershell
conda run -n geocompy python -m wrf_eval.cli inspect --config configs/tmax_validation.yaml
```

The command reports run id, variable, required wrfout variables, observation file counts, and per-scheme wrfout readiness.

## 4. Run Batch Evaluation

```powershell
conda run -n geocompy python -m wrf_eval.cli run --config configs/tmax_validation.yaml
```

The command prints progress for discovery, each scheme, excluded-day count, matched rows, and best scheme.

## 5. Review Outputs

Default Tmax outputs are written under:

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

## 6. Re-run Comparison Only

If per-scheme outputs already exist:

```powershell
conda run -n geocompy python -m wrf_eval.cli compare --config configs/tmax_validation.yaml
```
