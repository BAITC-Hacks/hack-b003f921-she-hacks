"""Offline cycle, cache and failure tests. Synthetic alerts only live in tests."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.weather_adapter import ROOT, digest, utc
from agent.weather_archive import obtain, select_run
from agent.weather_pipeline import main, run
from agent.power_alerts import analyze


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.args = argparse.Namespace(issue_time="2026-02-14T12:00:00Z", weather_run_time=None,
            wind_height_m=100, model_dir=ROOT / "models", drop_threshold=0.20,
            cache_dir=base / "cache", seed_dir=ROOT / "data/weather_source_check",
            output_root=base / "runs", offline=True)
        self.issue = utc(self.args.issue_time)
        self.weather_run = select_run(self.issue)

    def test_selection_and_eligibility(self):
        self.assertEqual(self.weather_run, utc("2026-02-14T00:00:00Z"))
        self.assertEqual(select_run(self.issue + timedelta(hours=5)), self.weather_run)
        self.assertEqual(select_run(self.issue + timedelta(hours=6)), self.weather_run + timedelta(hours=6))
        with self.assertRaisesRegex(ValueError, "12 hours"):
            select_run(self.issue, self.weather_run + timedelta(hours=6))
        with self.assertRaisesRegex(ValueError, "UTC hour"):
            select_run(self.issue + timedelta(minutes=1))

    def test_repeat_reuses_weather_and_predictions_without_inference(self):
        first = run(self.args)
        destination = Path(first["output_dir"])
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in destination.iterdir()}
        with patch("agent.weather_archive.fetch", side_effect=AssertionError("Unexpected download")), \
             patch("agent.weather_pipeline.subprocess.run", side_effect=AssertionError("Unexpected inference")):
            second = run(self.args)
        self.assertEqual(second["status"], "reused")
        self.assertEqual(second["weather_origin"], "cache")
        self.assertEqual(second["output_dir"], first["output_dir"])
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in destination.iterdir()})

    def test_corrupt_cache_does_not_return_old_success(self):
        first = run(self.args)
        cache = next(self.args.cache_dir.iterdir())
        body = json.loads((cache / "response.json").read_bytes())
        body[0]["hourly"]["wind_speed_100m"][20] = None
        damaged = json.dumps(body).encode()
        (cache / "response.json").write_bytes(damaged)
        meta = json.loads((cache / "request.json").read_bytes())
        meta["response_sha256"] = digest(damaged)  # Even with a matching checksum, semantic checks must fail.
        (cache / "request.json").write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "null/non-finite"):
            run(self.args)
        self.assertTrue(Path(first["output_dir"]).exists())

    def test_new_selected_run_never_uses_previous_run_cache(self):
        first = run(self.args)
        self.args.issue_time = "2026-02-14T18:00:00Z"
        with self.assertRaisesRegex(ValueError, "exact selected run"):
            run(self.args)
        self.assertTrue(Path(first["output_dir"]).exists())

    def test_changed_threshold_creates_version_preserving_old(self):
        first = run(self.args)
        self.args.drop_threshold = 1.0
        second = run(self.args)
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertTrue(Path(first["output_dir"]).exists())
        self.assertEqual(second["alerts"], 0)
        self.assertEqual(len((Path(second["output_dir"]) / "alerts.csv").read_text().splitlines()), 1)

    def test_different_weather_run_creates_separate_version(self):
        first = run(self.args)
        self.args.weather_run_time = "2026-02-13T18:00:00Z"
        self.args.offline = False
        def synthetic_run(url, raw, request_path, params):
            # Synthetic timing fixture ONLY for version/coverage tests in a temporary directory.
            # This is not an additional real forecast or a saved scientific example.
            payload = json.loads((ROOT / "data/weather_source_check/ecmwf_ifs_2026-02-14_00.json").read_bytes())
            init = utc(self.args.weather_run_time)
            for location in payload:
                hourly = location["hourly"]
                hourly["time"] = [(init + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
                                  for i in range(params["forecast_hours"])]
                for field in hourly.keys() - {"time"}:
                    hourly[field] = [hourly[field][0]] * 6 + hourly[field]
            body = json.dumps(payload).encode()
            metadata = {"request_url": url, "request_parameters": params,
                        "response_sha256": digest(body), "http_status": 200,
                        "test_fixture": "synthetic_not_real_weather"}
            raw.write_bytes(body)
            request_path.write_text(json.dumps(metadata))
            return body, metadata
        with patch("agent.weather_archive.fetch", side_effect=synthetic_run):
            second = run(self.args)
        self.assertNotEqual(first["output_dir"], second["output_dir"])
        self.assertTrue(Path(first["output_dir"]).exists())
        self.assertEqual(second["rows"], 96)
        metadata = json.loads((Path(second["output_dir"]) / "metadata.json").read_bytes())
        self.assertEqual(metadata["weather_run_time_utc"], self.args.weather_run_time)

    def test_corrupt_output_is_not_reused(self):
        first = run(self.args)
        path = Path(first["output_dir"]) / "alerts.csv"
        path.write_text("corrupt")
        with self.assertRaisesRegex(ValueError, "Corrupted result cache"):
            run(self.args)

    def test_http_error_not_published_as_cache(self):
        self.args.seed_dir = self.args.cache_dir / "no-seed"
        def unavailable(url, raw, request, params):
            body = b'{"error":true,"reason":"fixture: run unavailable"}'
            return body, {"request_url": url, "request_parameters": params,
                          "response_sha256": digest(body), "http_status": 400}
        with patch("agent.weather_archive.fetch", side_effect=unavailable), self.assertRaisesRegex(ValueError, "HTTP 400"):
            obtain(self.issue, self.weather_run, self.args.cache_dir, self.args.seed_dir, offline=False)
        self.assertEqual(list(self.args.cache_dir.iterdir()), [])
        self.assertFalse(self.args.output_root.exists())

    def test_failure_cli_records_error_only(self):
        code = main(["--issue-time", self.args.issue_time, "--wind-height-m", "100", "--offline",
                     "--cache-dir", str(self.args.cache_dir), "--seed-dir", str(self.args.cache_dir / "empty"),
                     "--output-root", str(self.args.output_root)])
        self.assertEqual(code, 1)
        reports = list(self.args.output_root.glob("failures/*.json"))
        self.assertEqual(len(reports), 1)
        self.assertFalse(json.loads(reports[0].read_bytes())["forecast_produced"])
        self.assertEqual(list(self.args.output_root.rglob("predictions.csv")), [])


class AlertTests(unittest.TestCase):
    def rows(self, start_power, end_power):
        return [{"turbine_id": turbine, "issue_time_utc": "2026-02-14T12:00:00Z",
                 "weather_run_time_utc": "2026-02-14T00:00:00Z", "target_time_utc": target,
                 "predicted_normalized_power": power}
                for turbine in ("turbine_1", "turbine_2")
                for target, power in [("2026-02-14T13:00:00Z", start_power), ("2026-02-14T16:00:00Z", end_power)]]

    def test_absolute_inclusive_threshold_and_separate_turbines(self):
        alerts, pairs = analyze(self.rows("0.30", "0.10"), 0.20)
        self.assertEqual((len(alerts), pairs), (2, 2))
        self.assertEqual({a["turbine_id"] for a in alerts}, {"turbine_1", "turbine_2"})
        self.assertEqual(analyze(self.rows("0.10", "0.07"), 0.20)[0], [])  # Relative 30% is not 0.20 absolute.

    def test_no_alerts_and_invalid_threshold(self):
        self.assertEqual(analyze(self.rows("0.30", "0.30"))[0], [])
        for value in (0, -1, float("nan"), 1.1):
            with self.assertRaises(ValueError):
                analyze([], value)


if __name__ == "__main__":
    unittest.main()
