"""Boundary and failure tests; synthetic values here are not evaluation results."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.weather_adapter import ROOT, utc, validate_model_time
from agent.weather_archive import obtain
from scripts.run_january_evaluation import assumed_availability, collect, coverage_report
import pandas as pd


class JanuaryPipelineTests(unittest.TestCase):
    def setUp(self):
        self.metadata = json.loads((ROOT / "models/backtest_january/metadata.json").read_bytes())

    def test_guard_uses_completed_interval_and_same_utc_plus_five_mapping(self):
        boundary = utc("2025-12-31T19:00:00Z")
        result = validate_model_time(boundary, self.metadata, "Etc/GMT-5")
        self.assertEqual(result["eligible_from_utc"], "2025-12-31T19:00:00Z")
        self.assertFalse(result["training_publication_availability_verified"])
        for issue, delay in [("2025-12-31T18:59:59Z", 0), ("2025-12-31T19:00:00Z", 1)]:
            with self.assertRaisesRegex(ValueError, "interval completion"):
                validate_model_time(utc(issue), self.metadata, "Etc/GMT-5", delay)
        with self.assertRaisesRegex(ValueError, "Explicit source timezone"):
            validate_model_time(utc("2026-01-01T12:00:00Z"), self.metadata)
        bad = deepcopy(self.metadata)
        bad["turbines"]["turbine_1"]["latest_training_hour_end_source"] = "2025-12-31 23:00:00"
        with self.assertRaisesRegex(ValueError, "interval end"):
            validate_model_time(boundary, bad, "Etc/GMT-5")

    def test_production_models_still_rejected_under_explicit_timezone(self):
        production = json.loads((ROOT / "models/metadata.json").read_bytes())
        with self.assertRaisesRegex(ValueError, "as-of-trained"):
            validate_model_time(utc("2026-01-31T12:00:00Z"), production, "Etc/GMT-5")

    def test_assumed_scada_availability_never_precedes_hour_end(self):
        actual = pd.DataFrame({"turbine_id": ["turbine_1"],
                               "target_time_utc": pd.to_datetime(["2026-01-01T11:00:00Z"])})
        result = assumed_availability(actual, 0)
        self.assertEqual(result.iloc[0].available_time_utc, "2026-01-01T12:00:00Z")
        self.assertEqual(result.iloc[0].availability_status, "assumed")

    def test_failed_issue_does_not_stop_later_issues(self):
        issues = pd.date_range("2026-01-01T12:00:00Z", periods=3, freq="D")
        args = argparse.Namespace(wind_height_m=100, model_dir=ROOT / "models/backtest_january",
            source_timezone="Etc/GMT-5", observation_delay_hours=0, cache_dir=ROOT / "data/weather_cache",
            runs_dir=ROOT / "data/processed/test_unused", offline=True)
        with patch("scripts.run_january_evaluation.run", side_effect=ValueError("synthetic cache miss")) as mocked:
            frames, records, evidence = collect(args, issues)
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(len(records), 3)
        self.assertTrue(records.status.eq("failed").all())
        self.assertEqual(frames, [])
        self.assertEqual(evidence, [])

    def test_transient_weather_failure_has_bounded_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch("agent.weather_archive.fetch", side_effect=RuntimeError("synthetic timeout")) as fetch, \
                 patch("agent.weather_archive.time.sleep") as sleep:
                with self.assertRaisesRegex(RuntimeError, "synthetic timeout"):
                    obtain(utc("2026-01-01T12:00:00Z"), utc("2026-01-01T00:00:00Z"), folder / "cache", folder / "seed")
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4])
            self.assertEqual(list((folder / "cache").iterdir()), [])

    def test_january_schedule_exposes_18_uncovered_hours_and_overlaps(self):
        issues = pd.date_range("2026-01-01T12:00:00Z", periods=30, freq="D")
        all_rows = [{"turbine_id": turbine, "target_time_utc": issue + pd.Timedelta(hours=h)}
                    for turbine in ("turbine_1", "turbine_2") for issue in issues for h in range(1, 49)]
        forecasts = pd.DataFrame(all_rows)
        audit = forecasts.loc[forecasts.target_time_utc < pd.Timestamp("2026-01-31T19:00:00Z")].copy()
        audit["evaluated"], audit["actual_missing"], audit["baseline_status"] = True, False, "available"
        report, missing = coverage_report(forecasts, audit, issues, "Etc/GMT-5", pd.DataFrame({"status": ["success"] * 30}))
        self.assertEqual(report["excluded_outside_january_rows"], 36)
        self.assertEqual(report["january_forecast_rows"], 2844)
        self.assertEqual(report["turbines"][0]["unique_forecast_hours"], 726)
        self.assertEqual(report["schedule_uncovered_hours_per_turbine"], 18)
        self.assertEqual(len(missing), 36)


if __name__ == "__main__":
    unittest.main()
