# WRF Station Verification Toolkit v1.1.1

## Summary

v1.1.1 is a documentation, packaging, and repository-hygiene patch for the v1.1 WRF station verification toolkit. It keeps the v1.1 scientific and engineering behavior unchanged while making the repository suitable for external users.

## Highlights

- Public README and docs use portable examples instead of machine-specific paths.
- Recommended environment name is `wrfpy`.
- Historical local verification reports are removed from the tracked repository.
- Generated data and reports are ignored by default.
- A portable PowerShell example is provided at `scripts/run_wrf_score.ps1`.
- Python distribution artifacts can be built from the tag with standard packaging tools.

## Install From Source

```powershell
cd D:/wrf/wrf-station-verification
conda env create -f environment.yml
conda activate wrfpy
python -m pip install -e .
```

## Run

```powershell
$env:PYTHONPATH = "src"
python -m wrf_eval.cli inspect --config configs/tmax_validation.yaml
python -m wrf_eval.cli run --config configs/tmax_validation.yaml
python -m wrf_eval.cli compare --config configs/tmax_validation.yaml
```

## Package Artifacts

Committed release package files:

```text
release-assets/v1.1.1/wrf_learning-1.1.1-py3-none-any.whl
release-assets/v1.1.1/wrf-station-verification-v1.1.1.zip
release-assets/v1.1.1/wrf-station-verification-v1.1.1.tar.gz
```
