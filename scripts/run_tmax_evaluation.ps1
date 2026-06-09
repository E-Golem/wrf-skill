$ErrorActionPreference = "Stop"

$env:PYTHONPATH = "src"
conda run -n geocompy python -m wrf_eval.cli `
  --wrf-input "data/wrfout/wrf_tmax_tmin_d01_2010-05-01_00_00_00" `
  --observed-dir "data/observed" `
  --boundary "data/boundary/Yangtze.shp" `
  --output-dir "outputs" `
  --report-dir "reports" `
  --variable "T2MAX" `
  --time-offset-hours 8 `
  --local-day-boundary-hour 20 `
  --drop-incomplete-start-day
