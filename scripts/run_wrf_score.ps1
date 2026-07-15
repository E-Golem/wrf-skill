$ErrorActionPreference = "Stop"

$env:PYTHONPATH = "src"

conda run -n wrfpy python -m wrf_eval.cli inspect --config configs/tmax_validation.yaml
conda run -n wrfpy python -m wrf_eval.cli run --config configs/tmax_validation.yaml
conda run -n wrfpy python -m wrf_eval.cli compare --config configs/tmax_validation.yaml
