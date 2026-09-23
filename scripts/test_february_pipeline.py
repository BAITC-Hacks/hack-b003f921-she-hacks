"""Focused February coverage and immutable reuse checks; never run ML or network."""
import argparse
from datetime import timedelta
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from agent.forecast_reuse import compatible_versions, reuse_version
from agent.weather_adapter import OUTPUT, ROOT, digest, read_csv, utc
from scripts.build_weather_example import stamp
from scripts.run_february_forecasts import collect, coverage_report, options_for, schedule


SAVED_FEBRUARY = (ROOT / "results/forecast_runs/20260214T120000Z/20260214T000000Z"
                  / "64248dfb5e925d39/metadata.json")


def arguments(cache_dir):
    return argparse.Namespace(
        wind_height_m=100, january_model_dir=ROOT / "models/backtest_january",
        production_model_dir=ROOT / "models", source_timezone="Etc/GMT-5",
        observation_delay_hours=0, drop_threshold=0.20, cache_dir=cache_dir,
        runs_dir=ROOT / "data/processed/february_test_unused", offline=True)


def forecast_rows(issues):
    """Synthetic schedule fixtures, not power predictions or evaluation results."""
    return [{"issue_time_utc": stamp(issue), "turbine_id": turbine,
             "target_time_utc": stamp(issue + timedelta(hours=h))}
            for issue in issues for turbine in ("turbine_1", "turbine_2")
            for h in range(1, 49)]


def issue_records(failed=None):
    return [{"issue_time_utc": stamp(issue), "status": "failed" if issue == failed else "success"}
            for issue in schedule()]


class FebruaryPipelineTests(unittest.TestCase):
    def test_schedule_and_model_switch_preserve_explicit_assumptions(self):
        issues = schedule()
        self.assertEqual(len(issues), 29)
        self.assertEqual(issues[0], utc("2026-01-31T12:00:00Z"))
        self.assertEqual(issues[-1], utc("2026-02-28T12:00:00Z"))
        self.assertTrue(all(b - a == timedelta(days=1) for a, b in zip(issues, issues[1:])))
        args = arguments(Path("unused_cache"))
        for index, issue in enumerate(issues):
            options = options_for(args, issue)
            expected = args.january_model_dir if index == 0 else args.production_model_dir
            self.assertEqual(options.model_dir, expected)
            self.assertEqual(options.issue_time, stamp(issue))
            self.assertEqual(options.source_timezone, "Etc/GMT-5")
            self.assertEqual(options.observation_delay_hours, 0)
            self.assertEqual(options.wind_height_m, 100)
            self.assertEqual(options.drop_threshold, 0.20)
            self.assertTrue(options.offline)
            self.assertIsNone(options.weather_run_time)

    def test_complete_schedule_covers_672_hours_with_overlapping_issues(self):
        coverage, selected, missing = coverage_report(forecast_rows(schedule()), issue_records(), "Etc/GMT-5")
        self.assertEqual(coverage["full_forecast_rows"], 2784)
        self.assertEqual(coverage["february_forecast_rows"], 2652)
        self.assertEqual(coverage["outside_february_rows"], 132)
        self.assertEqual(coverage["month_start_utc"], "2026-01-31T19:00:00Z")
        self.assertEqual(coverage["month_end_exclusive_utc"], "2026-02-28T19:00:00Z")
        self.assertEqual(coverage["timezone_status"], "assumed")
        self.assertEqual(coverage["issues_succeeded"], 29)
        self.assertTrue(coverage["all_february_hours_covered"])
        self.assertEqual(len(selected), 2652)
        self.assertEqual(missing, [])
        for turbine in coverage["turbines"]:
            self.assertEqual(turbine["covered_hours"], 672)
            self.assertEqual(turbine["forecast_rows"], 1326)
            self.assertEqual(turbine["missing_hours"], 0)

    def test_missing_first_issue_reports_actual_uncovered_hours(self):
        issues = schedule()
        coverage, _, missing = coverage_report(
            forecast_rows(issues[1:]), issue_records(failed=issues[0]), "Etc/GMT-5")
        self.assertEqual(coverage["issues_succeeded"], 28)
        self.assertEqual(coverage["issues_failed"], 1)
        self.assertEqual(coverage["failed_issue_times"], [stamp(issues[0])])
        self.assertFalse(coverage["all_february_hours_covered"])
        self.assertEqual(len(missing), 36)
        for turbine in coverage["turbines"]:
            self.assertEqual(turbine["covered_hours"], 654)
            self.assertEqual(turbine["missing_hours"], 18)
        self.assertEqual(min(row["target_time_utc"] for row in missing), "2026-01-31T19:00:00Z")
        self.assertEqual(max(row["target_time_utc"] for row in missing), "2026-02-01T12:00:00Z")

    def test_duplicate_forecast_case_is_rejected(self):
        rows = forecast_rows(schedule())
        with self.assertRaisesRegex(ValueError, "Duplicate issue/turbine/target"):
            coverage_report(rows + [rows[0].copy()], issue_records(), "Etc/GMT-5")

    def test_saved_february_predictions_are_enriched_without_ml_or_network(self):
        original = {p.name: digest(p.read_bytes()) for p in SAVED_FEBRUARY.parent.iterdir() if p.is_file()}
        with tempfile.TemporaryDirectory() as directory:
            options = options_for(arguments(Path(directory) / "cache"), utc("2026-02-14T12:00:00Z"))
            with patch("subprocess.run", side_effect=AssertionError("ML invocation forbidden")) as invoke, \
                 patch("agent.weather_archive.fetch", side_effect=AssertionError("Network forbidden")) as fetch:
                candidates = compatible_versions(options, [ROOT / "results/forecast_runs"])
                self.assertEqual(candidates[0][0], SAVED_FEBRUARY)
                rows, alerts, proof = reuse_version(options, SAVED_FEBRUARY)
            invoke.assert_not_called()
            fetch.assert_not_called()
            self.assertEqual(len(list((Path(directory) / "cache").glob("*/response.json"))), 1)
        _, saved = read_csv((SAVED_FEBRUARY.parent / "predictions.csv").read_bytes())
        self.assertEqual(len(rows), 96)
        self.assertEqual(len(alerts), 7)
        self.assertEqual(proof["added_audit_columns"],
                         ["model_sha256", "model_version", "weather_availability_status", "weather_available_time_utc"])
        for old, new in zip(saved, rows):
            self.assertEqual({key: new[key] for key in old}, old)
            self.assertEqual(new["weather_available_time_utc"], "2026-02-14T12:00:00Z")
            self.assertEqual(new["weather_availability_status"], "assumed")
            self.assertEqual(new["weather_provenance_status"], "unverified")
            self.assertTrue(0 <= float(new[OUTPUT]) <= 1)
        self.assertTrue(proof["prediction_values_preserved"])
        self.assertEqual(proof["model_time_check_for_this_schedule"]["eligible_from_utc"], "2026-01-31T19:00:00Z")
        self.assertEqual(original, {p.name: digest(p.read_bytes()) for p in SAVED_FEBRUARY.parent.iterdir() if p.is_file()})

    def test_corrupt_saved_prediction_is_rejected_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied = root / "corrupt_saved_run"
            shutil.copytree(SAVED_FEBRUARY.parent, copied)
            with (copied / "predictions.csv").open("ab") as stream:
                stream.write(b"corrupted\n")
            options = options_for(arguments(root / "cache"), utc("2026-02-14T12:00:00Z"))
            with patch("subprocess.run", side_effect=AssertionError("ML invocation forbidden")), \
                 patch("agent.weather_archive.fetch", side_effect=AssertionError("Network forbidden")), \
                 self.assertRaisesRegex(ValueError, "file checksum mismatch"):
                reuse_version(options, copied / "metadata.json")
            self.assertFalse((root / "cache").exists())

    def test_collection_continues_after_failed_issue_without_stale_rows(self):
        selected = schedule()[:3]
        args = arguments(Path("unused_cache"))

        def saved_rows(options, path):
            issue = utc(options.issue_time)
            rows = [{**row, "model_version": "synthetic_test_version"} for row in forecast_rows([issue])]
            return rows, [], {"run_id": options.issue_time}

        results = [{"status": "success", "output_dir": str(ROOT / "test_unused_first")},
                   ValueError("Synthetic weather failure"),
                   {"status": "success", "output_dir": str(ROOT / "test_unused_third")}]
        with patch("scripts.run_february_forecasts.schedule", return_value=selected), \
             patch("scripts.run_february_forecasts.compatible_versions", return_value=[]), \
             patch("scripts.run_february_forecasts.run", side_effect=results) as invoke, \
             patch("scripts.run_february_forecasts.reuse_version", side_effect=saved_rows) as reuse, \
             patch("sys.stdout", new_callable=io.StringIO):
            forecasts, alerts, records, evidence = collect(args)
        self.assertEqual(invoke.call_count, 3)
        self.assertEqual(reuse.call_count, 2)
        self.assertEqual([record["status"] for record in records], ["success", "failed", "success"])
        self.assertIn("Synthetic weather failure", records[1]["error"])
        self.assertEqual(records[1]["forecast_rows"], 0)
        self.assertEqual(len(forecasts), 192)
        self.assertEqual({row["issue_time_utc"] for row in forecasts}, {stamp(selected[0]), stamp(selected[2])})
        self.assertEqual(len(evidence), 2)
        self.assertEqual(alerts, [])


if __name__ == "__main__":
    unittest.main()
