import tempfile
import unittest
from pathlib import Path

from wrf_eval.config import discover_schemes, load_score_config, score_config_from_mapping


class ConfigTests(unittest.TestCase):
    def test_loads_yaml_config_and_discovers_matching_scheme_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrf_root = root / "wrfout"
            (wrf_root / "lw4-sw2").mkdir(parents=True)
            (wrf_root / "lw5-sw5").mkdir(parents=True)
            (wrf_root / "ignore-me").mkdir(parents=True)
            (wrf_root / "lw4-sw2" / "T2_out.nc").write_text("", encoding="utf-8")
            (wrf_root / "lw5-sw5" / "T2_output.nc").write_text("", encoding="utf-8")
            config_path = root / "config.yaml"
            config_path.write_text(
                f"""
version: 1
project:
  name: test_run
wrf:
  input_root: "{wrf_root}"
  schemes: auto
  input_kind: hourly_t2
  variable: T2
  file_patterns:
    - "T2_output*.nc"
    - "T2_out*.nc"
observed:
  data_dir: "{root / 'observed'}"
time:
  time_offset_hours: 8
  local_day_boundary_hour: 20
validation:
  start: "06-01"
  end: "10-01"
metrics:
  selected:
    - pcc
    - bias
    - rmse
output:
  run_id: test_run
  output_root: "{root / 'outputs'}"
  report_root: "{root / 'reports'}"
""",
                encoding="utf-8",
            )

            config = load_score_config(config_path)
            schemes = discover_schemes(config)

            self.assertEqual(config.run_id, "test_run")
            self.assertEqual([scheme.name for scheme in schemes], ["lw4-sw2", "lw5-sw5"])
            self.assertEqual(schemes[0].file_pattern, "T2_out*.nc")
            self.assertEqual(schemes[1].file_pattern, "T2_output*.nc")

    def test_mapping_defaults_match_current_tmax_workflow(self):
        config = score_config_from_mapping({"project": {"name": "defaults"}})

        self.assertEqual(config.run_id, "defaults")
        self.assertEqual(config.wrf.input_kind, "hourly_t2")
        self.assertEqual(config.wrf.variable, "T2")
        self.assertIn("normalized_crmse", config.metrics.selected)
        self.assertEqual(config.time.local_day_boundary_hour, 20)


if __name__ == "__main__":
    unittest.main()
