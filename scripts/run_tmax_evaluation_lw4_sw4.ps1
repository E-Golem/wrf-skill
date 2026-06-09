$ErrorActionPreference = "Stop"

$env:PYTHONPATH = "src"
conda run -n geocompy python -m wrf_eval.cli `
  --wrf-input "data/wrfout/lw4-sw4" `
  --coord-source "data/wrfout/wrf_tmax_tmin_d01_2010-05-01_00_00_00" `
  --observed-dir "data/observed" `
  --boundary "data/boundary/Yangtze.shp" `
  --output-dir "outputs/lw4-sw4" `
  --report-dir "reports/lw4-sw4" `
  --variable "T2MAX" `
  --time-offset-hours 8 `
  --local-day-boundary-hour 20 `
  --drop-incomplete-start-day `
  --date-match "exact"
