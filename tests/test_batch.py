import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from wrf_eval.batch import run_batch
from wrf_eval.config import score_config_from_mapping
from wrf_eval.pipeline import ProcessingResult


class BatchTests(unittest.TestCase):
    def test_run_batch_processes_discovered_schemes_and_writes_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrf_root = root / "wrfout"
            for scheme in ["lw1-sw1", "lw4-sw2"]:
                scheme_dir = wrf_root / scheme
                scheme_dir.mkdir(parents=True)
                (scheme_dir / "T2_out.nc").write_text("", encoding="utf-8")
            config = score_config_from_mapping(
                {
                    "project": {"name": "batch_test"},
                    "wrf": {"input_root": str(wrf_root), "file_patterns": ["T2_out*.nc"]},
                    "observed": {"data_dir": str(root / "observed")},
                    "output": {
                        "run_id": "batch_test",
                        "output_root": str(root / "outputs"),
                        "report_root": str(root / "reports"),
                    },
                }
            )

            def fake_run_processing(processing_config):
                table_dir = processing_config.output_dir / "tables"
                table_dir.mkdir(parents=True)
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
                            "input_kind": processing_config.input_kind,
                            "validation_start": processing_config.validation_start,
                            "validation_end": processing_config.validation_end,
                        }
                    ]
                ).to_csv(table_dir / "overall_score.csv", index=False)
                return ProcessingResult(
                    matched_path=table_dir / "matched_station_daily_tmax.csv",
                    overall_score_path=table_dir / "overall_score.csv",
                    daily_score_path=table_dir / "daily_scores.csv",
                    station_score_path=table_dir / "station_scores.csv",
                    report_path=processing_config.report_dir / "wrf_tmax_evaluation_report.md",
                    matched_rows=10,
                    station_count=2,
                    date_count=5,
                    overall_metrics={"score": score},
                )

            progress_messages = []
            with patch("wrf_eval.batch.run_processing", side_effect=fake_run_processing):
                result = run_batch(config, progress_callback=progress_messages.append)

            self.assertEqual(result.successful_scheme_names, ["lw1-sw1", "lw4-sw2"])
            self.assertTrue(result.comparison_csv.exists())
            comparison = pd.read_csv(result.comparison_csv)
            self.assertEqual(comparison.iloc[0]["scheme_name"], "lw4-sw2")
            self.assertTrue(any("Discovered 2 scheme" in message for message in progress_messages))
            self.assertTrue(any("Best scheme: lw4-sw2" in message for message in progress_messages))


if __name__ == "__main__":
    unittest.main()
