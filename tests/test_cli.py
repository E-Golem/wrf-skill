import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from netCDF4 import Dataset

from wrf_eval.cli import build_tool_parser, run_tool_command


class CliTests(unittest.TestCase):
    def test_v11_help_does_not_expose_removed_public_options(self):
        banned = ["input-kind", "score-metrics", "report-dir", "time-offset", "local-day-boundary", "day-boundary"]
        help_texts = [build_tool_parser().format_help()]
        for command in ["run", "inspect", "compare"]:
            parser = build_tool_parser()
            stdout = io.StringIO()
            with self.assertRaises(SystemExit) as raised:
                with redirect_stdout(stdout):
                    parser.parse_args([command, "--help"])
            self.assertEqual(raised.exception.code, 0)
            help_texts.append(stdout.getvalue())

        combined = "\n".join(help_texts)
        for option in banned:
            with self.subTest(option=option):
                self.assertNotIn(option, combined)

    def test_inspect_reports_wrfout_and_observation_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scheme_dir = root / "wrfout" / "lw4-sw2"
            scheme_dir.mkdir(parents=True)
            obs_dir = root / "observed"
            obs_dir.mkdir()
            (obs_dir / "SURF_CLI_CHN_MUL_DAY-TEM-test.TXT").write_text("", encoding="utf-8")
            wrfout = scheme_dir / "wrfout_d01_2020-06-01_00_00_00"
            with Dataset(wrfout, "w") as ds:
                ds.createDimension("Time", 1)
                ds.createDimension("south_north", 1)
                ds.createDimension("west_east", 1)
                ds.createVariable("T2", "f4", ("Time", "south_north", "west_east"))
            config_path = root / "config.yaml"
            config_path.write_text(
                f"""
version: 1
wrf:
  input_root: "{root / 'wrfout'}"
  schemes: auto
  file_patterns:
    - "wrfout_d0*"
observed:
  data_dir: "{obs_dir}"
validation:
  variable: Tmax
output:
  root: "{root / 'outputs' / 'runs'}"
""",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = run_tool_command(["inspect", "--config", str(config_path)])

            output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("variable=Tmax", output)
            self.assertIn("observed_tem_files=1", output)
            self.assertIn("scheme=lw4-sw2", output)
            self.assertIn("wrf_status=ok", output)


if __name__ == "__main__":
    unittest.main()
