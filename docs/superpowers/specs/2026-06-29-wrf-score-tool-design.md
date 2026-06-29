# WRF Score Tool Design

Date: 2026-06-29

## Purpose

Build a configuration-driven WRF verification tool around the scoring workflow already proven in this repository. The first version should be a command line tool, not a web platform. It should make the current Tmax verification workflow repeatable, auditable, and easy to apply to many parameterization schemes.

The tool will support station-based verification of WRF daily maximum temperature from two input families:

- Hourly WRF `T2` outputs, aggregated to station-day Tmax.
- WRF meteorological diagnostic files that already contain daily Tmax.

The main operational use case is batch evaluation of folders named like `lw4-sw2`, where `lw` indicates the longwave radiation scheme and `sw` indicates the shortwave radiation scheme.

## Goals

- Run one or many WRF schemes from a single YAML configuration file.
- Standardize UTC to local time conversion and China station-day handling.
- Support Beijing time with a 20:00 local day boundary.
- Drop incomplete leading or trailing station days when requested.
- Validate a configurable date window, such as `06-01` to `10-01`.
- Match stations inside a boundary polygon to the nearest WRF grid cell.
- Compute overall, daily, and station-level metrics.
- Compute a bounded 0 to 100 composite score from selected metrics.
- Compare parameterization schemes and select the best scheme by a documented ranking rule.
- Produce CSV tables and Markdown reports suitable for thesis records and engineering reuse.

## Non Goals For Version 1

- Web UI or desktop GUI.
- Database storage.
- Online map rendering.
- Automatic meteorological data download.
- Automatic scientific explanation of each WRF physical scheme.
- Full heatwave event verification. Heatwave metrics can be added as a later module.

## Recommended First Version

The first version should be a Python CLI with YAML configuration:

```powershell
conda run -n geocompy wrf-score run --config configs/tmax_validation.yaml
conda run -n geocompy wrf-score compare --run-id yangtze_tmax_validation
conda run -n geocompy wrf-score inspect --wrf-input data/wrfout/lw4-sw2
```

This gives a stable engineering core before any visual platform work. A later web or desktop interface can call the same Python package.

## Current Repository Fit

The existing repository already contains most of the computational core:

- `src/wrf_eval/wrf_hourly.py`: reads hourly `T2` and aggregates it to daily Tmax.
- `src/wrf_eval/wrf_diag.py`: reads WRF diagnostic daily Tmax files.
- `src/wrf_eval/observed.py`: reads China daily station temperature files.
- `src/wrf_eval/sampling.py`: nearest grid-cell station sampling.
- `src/wrf_eval/metrics.py`: metrics and composite score.
- `src/wrf_eval/pipeline.py`: single-scheme processing pipeline.
- `src/wrf_eval/compare_schemes.py`: multi-scheme ranking and comparison.
- `src/wrf_eval/cli.py`: current command line entry point.

The main design change is to add a configuration layer and a batch runner layer, while keeping these existing modules as the core implementation.

## Architecture

Version 1 should organize responsibilities like this:

```text
configs/
  tmax_validation.yaml

src/wrf_eval/
  config.py
  cli.py
  batch.py

  inputs/
    wrf_hourly.py
    wrf_diagnostic.py
    observed.py

  core/
    time_axis.py
    aggregation.py
    spatial_match.py
    validation.py

  metrics/
    basic.py
    scoring.py

  compare/
    schemes.py
    ranking.py

  reports/
    markdown.py
    tables.py
```

The current files do not need to be moved immediately. The implementation can first add `config.py` and `batch.py`, then gradually split large modules only when needed.

## Data Flow

The batch workflow should be:

```text
Read YAML config
  -> discover scheme folders
  -> build one ProcessingConfig per scheme
  -> read WRF input
  -> correct time axis
  -> aggregate or read daily Tmax
  -> filter validation window
  -> read observed station data
  -> filter stations by boundary
  -> match stations to WRF grid
  -> merge station-date pairs
  -> compute metrics and score
  -> write per-scheme outputs
  -> compare all schemes
  -> write comparison report
```

## Configuration Contract

The YAML configuration should be explicit and versioned:

```yaml
version: 1

project:
  name: yangtze_tmax_validation

wrf:
  input_root: data/wrfout
  schemes: auto
  scheme_name_pattern: "lw{lw}-sw{sw}"
  input_kind: hourly_t2
  variable: T2
  file_patterns:
    - "T2_out*.nc"
    - "T2_output*.nc"

observed:
  data_dir: data/observed
  boundary: data/boundary/Yangtze.shp
  station_policy: all_in_boundary

time:
  time_offset_hours: 8
  local_day_boundary_hour: 20
  drop_incomplete_start_day: true
  drop_incomplete_end_day: true

validation:
  start: "06-01"
  end: "10-01"
  date_match: exact

metrics:
  selected:
    - pcc
    - bias
    - mae
    - rmse
    - normalized_crmse
    - rsd
  weights:
    pcc: 1
    bias: 1
    mae: 1
    rmse: 1
    normalized_crmse: 1
    rsd: 1

output:
  run_id: yangtze_tmax_validation
  output_root: outputs/runs
  report_root: reports
  formats:
    - csv
    - markdown
```

The first implementation should support equal weights and preserve the current scoring formula. Weighted scoring can be implemented after the unweighted YAML flow is stable.

`output.run_id` is the stable identifier for a batch run. If it is omitted, the tool should use `project.name`.

## Scheme Discovery

When `wrf.schemes` is `auto`, the tool should scan `wrf.input_root` for directories. A scheme directory is valid when it contains at least one file matching any configured file pattern. The folder name becomes `scheme_name`.

For names like `lw4-sw2`, the comparison report should parse:

- `lw_scheme`: `lw4`
- `sw_scheme`: `sw2`

If parsing fails, the tool should still evaluate the scheme and leave those fields empty.

## Time Handling

The default verified time policy is:

- WRF raw time is treated as UTC.
- Add `time_offset_hours=8` to convert to Beijing time.
- Use `local_day_boundary_hour=20` for China daily station observations.
- Assign timestamps at or before 20:00 to the same station day.
- Assign timestamps after 20:00 to the next station day.
- Drop the first or last station day if the hourly window is incomplete and the corresponding config switch is true.

This policy should be recorded in every per-scheme report.

## Metrics And Score

The basic metric set is:

- `pcc`: Pearson correlation coefficient. Higher is better.
- `bias`: mean model minus observation error in deg C. Closer to 0 is better.
- `mae`: mean absolute error in deg C. Lower is better.
- `rmse`: root mean square error in deg C. Lower is better.
- `normalized_crmse`: centered RMSE divided by observed standard deviation. Lower is better.
- `rsd`: model standard deviation divided by observed standard deviation. Closer to 1 is better.

The current composite score should remain:

```text
score = 100 * mean(normalized metric components)
```

Component rules:

- `pcc`: `(pcc + 1) / 2`, clipped to 0 to 1.
- `bias`: `1 / (1 + abs(bias) / obs_std)`.
- `mae`: `1 / (1 + mae / obs_std)`.
- `rmse`: `1 / (1 + rmse / obs_std)`.
- `normalized_crmse`: `1 / (1 + normalized_crmse)`.
- `rsd`: `1 / (1 + abs(rsd - 1))`.

The report must state that the composite score is for fast scheme comparison and does not replace separate scientific interpretation of each metric.

## Ranking Rule

The scheme comparison should sort by:

1. Higher composite score.
2. Lower RMSE.
3. Lower MAE.
4. Lower absolute bias.
5. Lower normalized cRMSE.
6. Higher PCC.

The best scheme is the first ranked row.

## Outputs

Each scheme run should write:

```text
outputs/runs/<run_id>/<scheme_name>/tables/matched_station_daily_tmax.csv
outputs/runs/<run_id>/<scheme_name>/tables/overall_score.csv
outputs/runs/<run_id>/<scheme_name>/tables/daily_scores.csv
outputs/runs/<run_id>/<scheme_name>/tables/station_scores.csv
reports/<run_id>/<scheme_name>/wrf_tmax_evaluation_report.md
```

The comparison stage should write:

```text
outputs/runs/<run_id>/scheme-comparison/scheme_comparison.csv
reports/<run_id>/scheme-comparison/scheme_comparison_report.md
```

## Error Handling

The tool should fail early with clear messages when:

- No WRF files match the input pattern.
- The target WRF variable is missing.
- WRF files in one scheme have inconsistent grids.
- The time axis cannot be parsed.
- No station records remain after date or boundary filtering.
- No station-date pairs can be matched.
- A metric selected in config is unsupported.

Batch mode should record failed schemes and continue only when `continue_on_error: true` is configured. The default should be to stop on the first failed scheme.

## Testing Strategy

Tests should cover:

- YAML config parsing and default expansion.
- Scheme discovery from folder names.
- Time conversion and 20:00 station-day assignment.
- Dropping incomplete station days.
- Metric calculation and composite score.
- Station boundary filtering.
- Single-scheme pipeline output paths.
- Multi-scheme ranking.
- Failure cases for missing variable, missing files, and unsupported metrics.

Existing tests should be preserved and extended rather than replaced.

## Implementation Phases

Phase 1: Configuration and CLI shell

- Add `config.py` for YAML parsing and validation.
- Add a `wrf-score` console entry point.
- Support single-scheme execution from config.

Phase 2: Batch runner

- Add scheme discovery.
- Run all discovered schemes with one shared config.
- Write outputs under a run id.

Phase 3: Comparison and reports

- Reuse and harden the current comparison logic.
- Repair garbled Chinese report strings.
- Write comparison report with ranking rule and best scheme.

Phase 4: Engineering hardening

- Improve error messages.
- Add tests for config, batch, and reports.
- Add README usage examples.

Phase 5: Future extension

- Add heatwave event verification metrics.
- Add figures and HTML reports.
- Add a visualization platform that calls the CLI or package API.

## Acceptance Criteria

Version 1 is complete when:

- A single YAML file can reproduce the current `lw1-sw1`, `lw3-sw3`, `lw4-sw2`, `lw4-sw4`, and `lw5-sw5` batch comparison.
- The reported scores match the current pipeline within normal floating point tolerance.
- The best scheme selected from the batch run is the same as the current comparison under the same inputs.
- Per-scheme and comparison reports are generated without garbled text.
- Tests pass in the `geocompy` conda environment.
