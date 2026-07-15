import tempfile
import unittest
from pathlib import Path

from wrf_eval.config import (
    FIXED_SCORE_METRICS,
    discover_schemes,
    load_score_config,
    score_config_from_mapping,
)


class ConfigTests(unittest.TestCase):
    def test_loads_v11_yaml_config_and_discovers_matching_scheme_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrf_root = root / "wrfout"
            (wrf_root / "lw4-sw2").mkdir(parents=True)
            (wrf_root / "lw5-sw5").mkdir(parents=True)
            (wrf_root / "ignore-me").mkdir(parents=True)
            (wrf_root / "lw4-sw2" / "wrfout_d01_2020-06-01_00_00_00").write_text("", encoding="utf-8")
            (wrf_root / "lw5-sw5" / "wrfout_d01_2020-06-01_00_00_00").write_text("", encoding="utf-8")
            config_path = root / "config.yaml"
            config_path.write_text(
                f"""
version: 1
project:
  name: test_run
wrf:
  input_root: "{wrf_root}"
  schemes: auto
  file_patterns:
    - "wrfout_d0*"
observed:
  data_dir: "{root / 'observed'}"
validation:
  variable: Tmax
  start: "06-01"
  end: "10-01"
output:
  run_id: test_run
  root: "{root / 'outputs' / 'runs'}"
""",
                encoding="utf-8",
            )

            config = load_score_config(config_path)
            schemes = discover_schemes(config)

            self.assertEqual(config.run_id, "test_run")
            self.assertEqual(config.validation.variable, "Tmax")
            self.assertEqual(config.score_metrics, FIXED_SCORE_METRICS)
            self.assertEqual([scheme.name for scheme in schemes], ["lw4-sw2", "lw5-sw5"])
            self.assertEqual(schemes[0].file_pattern, "wrfout_d0*")

    def test_mapping_defaults_are_v11_station_validation_defaults(self):
        config = score_config_from_mapping({"project": {"name": "defaults"}})

        self.assertEqual(config.run_id, "wrf_tmax_station_validation")
        self.assertEqual(config.wrf.input_root, Path("data/wrfout"))
        self.assertEqual(config.wrf.file_patterns, ("wrfout_d0*",))
        self.assertEqual(config.validation.variable, "Tmax")
        self.assertEqual(config.validation.start, "06-01")
        self.assertEqual(config.validation.end, "10-01")
        self.assertEqual(config.output.root, Path("outputs/runs"))
        self.assertEqual(config.score_metrics, FIXED_SCORE_METRICS)

    def test_rejects_legacy_config_fields_removed_in_v11(self):
        legacy_cases = [
            {"time": {"time_offset_hours": 8}},
            {"metrics": {"selected": ["pcc"]}},
            {"wrf": {"input_kind": "hourly_t2"}},
            {"wrf": {"variable": "T2"}},
            {"wrf": {"temperature_stat": "max"}},
            {"validation": {"date_match": "month_day"}},
            {"output": {"output_root": "outputs"}},
            {"output": {"report_root": "reports"}},
        ]
        for data in legacy_cases:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    score_config_from_mapping(data)

    def test_validation_variable_is_limited_to_supported_v11_variables(self):
        for variable, expected in [("Tmax", "Tmax"), ("t2", "T2"), ("RHU", "RH")]:
            with self.subTest(variable=variable):
                config = score_config_from_mapping({"validation": {"variable": variable}})
                self.assertEqual(config.validation.variable, expected)

        with self.assertRaises(ValueError):
            score_config_from_mapping({"validation": {"variable": "Tmin"}})


if __name__ == "__main__":
    unittest.main()
