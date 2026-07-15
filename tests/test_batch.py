import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from wrf_eval.batch import run_batch
from wrf_eval.config import score_config_from_mapping
from wrf_eval.pipeline import ProcessingResult


class BatchTests(unittest.TestCase):
    def test_run_batch_processes_discovered_schemes_and_writes_merged_comparison_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrf_root = root / "wrfout"
            for scheme in ["lw1-sw1", "lw4-sw2"]:
                scheme_dir = wrf_root / scheme
                scheme_dir.mkdir(parents=True)
                (scheme_dir / "wrfout_d01_2020-06-01_00_00_00").write_text("", encoding="utf-8")
            config = score_config_from_mapping(
                {
                    "wrf": {"input_root": str(wrf_root), "file_patterns": ["wrfout_d0*"]},
                    "observed": {"data_dir": str(root / "observed")},
                    "validation": {"variable": "Tmax", "start": "06-01", "end": "10-01"},
                    "output": {"run_id": "batch_test", "root": str(root / "outputs" / "runs")},
                }
            )

            def fake_run_processing(processing_config):
                table_dir = processing_config.output_dir / "tables"
                report_dir = processing_config.output_dir / "reports"
                table_dir.mkdir(parents=True)
                report_dir.mkdir(parents=True)
                score = 80.0 if processing_config.scheme_name == "lw4-sw2" else 70.0
                pd.DataFrame(
                    [
                        {
                            "n": 10,
                            "score": score,
                            "pcc": 0.9,
                            "bias": -1.0,
                            "mae": 2.0,
                            "rmse": 3.0,
                            "normalized_crmse": 0.5,
                            "rsd": 1.0,
                            "scheme_name": processing_config.scheme_name,
                            "variable": processing_config.variable,
                            "validation_start": processing_config.validation_start,
                            "validation_end": processing_config.validation_end,
                        }
                    ]
                ).to_csv(table_dir / "overall_score.csv", index=False)
                excluded_path = table_dir / "excluded_days.csv"
                pd.DataFrame([{"date": "2020-05-31", "reason": "outside_validation_window"}]).to_csv(
                    excluded_path, index=False
                )
                return ProcessingResult(
                    matched_path=table_dir / "matched_station_daily_tmax.csv",
                    overall_score_path=table_dir / "overall_score.csv",
                    daily_score_path=table_dir / "daily_scores.csv",
                    station_score_path=table_dir / "station_scores.csv",
                    excluded_days_path=excluded_path,
                    report_path=report_dir / "wrf_tmax_evaluation_report.md",
                    matched_rows=10,
                    station_count=2,
                    date_count=5,
                    excluded_day_count=1,
                    overall_metrics={"score": score},
                )

            progress_messages = []
            with patch("wrf_eval.batch.run_processing", side_effect=fake_run_processing):
                result = run_batch(config, progress_callback=progress_messages.append)

            self.assertEqual(result.successful_scheme_names, ["lw1-sw1", "lw4-sw2"])
            self.assertEqual(result.output_root, root / "outputs" / "runs" / "batch_test")
            self.assertTrue(result.comparison_csv.exists())
            self.assertTrue(result.comparison_report.exists())
            self.assertTrue(str(result.comparison_report).startswith(str(result.output_root)))
            comparison = pd.read_csv(result.comparison_csv)
            self.assertEqual(comparison.iloc[0]["scheme_name"], "lw4-sw2")
            self.assertTrue(any("Discovered 2 scheme" in message for message in progress_messages))
            self.assertTrue(any("excluded_days=1" in message for message in progress_messages))
            self.assertTrue(any("Best scheme: lw4-sw2" in message for message in progress_messages))


if __name__ == "__main__":
    unittest.main()
