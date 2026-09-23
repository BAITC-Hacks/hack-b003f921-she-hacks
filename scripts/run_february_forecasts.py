#!/usr/bin/env python3
"""Complete only missing daily issues for February coverage; no accuracy evaluation."""
import argparse
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data/processed/.matplotlib"))

from agent.artifact_store import publish
from agent.forecast_reuse import compatible_versions, reuse_version
from agent.weather_adapter import OUTPUT, digest, utc
from agent.weather_pipeline import run, json_bytes, csv_bytes
from agent.power_alerts import FIELDS as ALERT_FIELDS
from scripts.build_weather_example import stamp

ISSUE_FIELDS = ["issue_time_utc", "weather_run_time_utc", "status", "model_role", "model_version",
                "forecast_rows", "alerts", "run_id", "output_dir", "error"]
MONTH_ALERT_FIELDS = ["issue_time_utc", "weather_run_time_utc", *ALERT_FIELDS]


def schedule():
    return [datetime(2026, 1, 31, 12, tzinfo=timezone.utc) + timedelta(days=day) for day in range(29)]


def options_for(args, issue):
    return argparse.Namespace(issue_time=stamp(issue), weather_run_time=None,
        wind_height_m=args.wind_height_m, model_dir=args.january_model_dir if issue.month == 1 else args.production_model_dir,
        source_timezone=args.source_timezone, observation_delay_hours=args.observation_delay_hours,
        drop_threshold=args.drop_threshold, cache_dir=args.cache_dir, seed_dir=ROOT / "data/weather_source_check",
        output_root=args.runs_dir, offline=args.offline)


def collect(args):
    forecasts, alerts, issues, evidence = [], [], [], []
    for issue in schedule():
        options = options_for(args, issue)
        role = "january" if issue.month == 1 else "production"
        record = dict.fromkeys(ISSUE_FIELDS, "")
        record.update(issue_time_utc=stamp(issue), weather_run_time_utc=stamp(issue - timedelta(hours=12)),
                      model_role=role, forecast_rows=0, alerts=0)
        try:
            candidates = compatible_versions(options, [args.runs_dir, ROOT / "results/forecast_runs"])
            if candidates:
                path = candidates[0][0]
                status = "reused"
            else:
                result = run(options)  # Existing loader, guard, adapter, batch and alerts.
                path = Path(result["output_dir"]) / "metadata.json"
                status = result["status"]
            rows, run_alerts, proof = reuse_version(options, path)
            forecasts.extend(rows)
            alerts.extend([{**item, "issue_time_utc": stamp(issue),
                            "weather_run_time_utc": record["weather_run_time_utc"]} for item in run_alerts])
            evidence.append(proof)
            record.update(status=status, model_version=rows[0]["model_version"], forecast_rows=len(rows),
                          alerts=len(run_alerts), run_id=proof["run_id"], output_dir=str(path.parent.relative_to(ROOT)))
            print(f"{stamp(issue)}: {status}, {role}, {len(rows)} rows, {len(run_alerts)} alerts", flush=True)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
            print(f"{stamp(issue)}: FAILED: {error}; continuing", flush=True)
        issues.append(record)
    return forecasts, alerts, issues, evidence


def coverage_report(forecasts, issues, zone):
    start = datetime(2026, 2, 1, tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
    end = datetime(2026, 3, 1, tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
    expected = {start + timedelta(hours=h) for h in range(int((end - start).total_seconds() / 3600))}
    if len(expected) != 672:
        raise ValueError("Configured February source clock does not produce the expected 672 hourly starts")
    keys = [(r["issue_time_utc"], r["turbine_id"], r["target_time_utc"]) for r in forecasts]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate issue/turbine/target forecast case")
    selected = [r for r in forecasts if start <= utc(r["target_time_utc"]) < end]
    turbines, missing = [], []
    for turbine in ("turbine_1", "turbine_2"):
        group = [r for r in selected if r["turbine_id"] == turbine]
        actual = {utc(r["target_time_utc"]) for r in group}
        absent = sorted(expected - actual)
        turbines.append({"turbine_id": turbine, "expected_hours": len(expected), "covered_hours": len(actual),
                         "missing_hours": len(absent), "forecast_rows": len(group),
                         "first_target_utc": stamp(min(actual)) if actual else None,
                         "last_target_utc": stamp(max(actual)) if actual else None})
        missing.extend({"turbine_id": turbine, "target_time_utc": stamp(t)} for t in absent)
    failed = [r["issue_time_utc"] for r in issues if r["status"] == "failed"]
    return {"source_timezone": zone, "timezone_status": "assumed", "timestamp_label": "interval_start_assumed",
            "month_start_utc": stamp(start), "month_end_exclusive_utc": stamp(end),
            "issues_requested": len(issues), "issues_succeeded": len(issues) - len(failed), "issues_failed": len(failed),
            "failed_issue_times": failed, "full_forecast_rows": len(forecasts), "february_forecast_rows": len(selected),
            "outside_february_rows": len(forecasts) - len(selected), "duplicate_keys": 0,
            "all_february_hours_covered": not missing, "turbines": turbines}, selected, missing


def execute(args):
    forecasts, alerts, issues, evidence = collect(args)
    coverage, february, missing = coverage_report(forecasts, issues, args.source_timezone)
    coverage.update(alert_threshold=args.drop_threshold, alert_windows=len(alerts), wind_height_m=args.wind_height_m,
                    observation_delay_hours=args.observation_delay_hours)
    settings = {"source_timezone": args.source_timezone, "timezone_status": "assumed",
                "timestamp_label": "interval_start_assumed", "observation_delay_hours": args.observation_delay_hours,
                "observation_availability_status": "assumed", "weather_availability_lag_hours": 12,
                "weather_availability_status": "assumed", "weather_provenance_status": "unverified",
                "wind_height_m": args.wind_height_m, "wind_height_status": "technical_assumption",
                "drop_threshold": args.drop_threshold, "threshold_status": "demonstration_not_history_calibrated",
                "issue_schedule": "2026-01-31 through 2026-02-28 daily at 12:00 UTC, horizons 1..48"}
    # Keep every issue and every 48h target; a separate subset defines month coverage.
    fields = list(forecasts[0]) if forecasts else ["issue_time_utc", "turbine_id", "target_time_utc", OUTPUT]
    files = {"forecasts.csv": csv_bytes(fields, forecasts), "february_forecasts.csv": csv_bytes(fields, february),
             "alerts.csv": csv_bytes(MONTH_ALERT_FIELDS, alerts), "issues.csv": csv_bytes(ISSUE_FIELDS, issues),
             "coverage.json": json_bytes(coverage), "weather_evidence.json": json_bytes(evidence),
             "missing_hours.csv": csv_bytes(["turbine_id", "target_time_utc"], missing)}
    code_paths = ["scripts/run_february_forecasts.py", "agent/forecast_reuse.py", "agent/february_report.py"]
    identity = {"settings": settings, "forecasts_sha256": digest(files["forecasts.csv"]),
                "alerts_sha256": digest(files["alerts.csv"]),
                "issues": [{k: row[k] for k in ("issue_time_utc", "run_id", "model_role", "error")} for row in issues],
                "code_sha256": {p: digest((ROOT / p).read_bytes().replace(b"\r\n", b"\n")) for p in code_paths}}
    run_id = digest(json_bytes(identity))[:16]
    destination = args.output_root / run_id
    if destination.exists():
        metadata = json.loads((destination / "metadata.json").read_bytes())
        if metadata["identity"] != identity:
            raise ValueError("Existing monthly result identity differs")
        for name, expected in metadata["file_sha256"].items():
            if digest((destination / name).read_bytes()) != expected:
                raise ValueError(f"Corrupted monthly result: {name}")
        print(f"Validated existing monthly result: {destination}", flush=True)
    else:
        from agent.february_report import render_report
        files.update(render_report(forecasts, alerts, coverage))
        files["metadata.json"] = json_bytes({"status": "complete" if not coverage["issues_failed"] else "incomplete",
            "purpose": "February forecast coverage demonstration, not accuracy evaluation",
            "identity": identity, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "weather_provenance_status": "unverified", "historical_availability_verified": False,
            "model_selection": "January artifacts on January 31; production artifacts on February 1..28",
            "february_actual_power_available": False, "accuracy_evaluated": False,
            "environment": {"python": sys.version.split()[0], **{p: version(p) for p in ("catboost", "pandas", "matplotlib")}},
            "validation": {"all_successful_issues_have_96_rows": all(r["forecast_rows"] == 96 for r in issues if r["status"] != "failed"),
                           "weather_fields_and_times_checked": True, "models_and_training_boundaries_checked": True,
                           "predictions_finite_in_0_1": True, "missing_forecast_fields": 0,
                           "all_february_hours_covered": coverage["all_february_hours_covered"]},
            "file_sha256": {name: digest(body) for name, body in files.items()}})
        publish(destination, files)
        print(f"Monthly results saved to {destination}", flush=True)
    print(json.dumps(coverage, indent=2), flush=True)
    return 1 if coverage["issues_failed"] or not coverage["all_february_hours_covered"] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-timezone", default="Etc/GMT-5", help="Assumed fixed UTC+05 source clock")
    parser.add_argument("--observation-delay-hours", type=float, default=0, help="Assumed delay after training interval ends")
    parser.add_argument("--wind-height-m", type=int, choices=(10, 100, 200), default=100)
    parser.add_argument("--drop-threshold", type=float, default=0.20)
    parser.add_argument("--january-model-dir", type=Path, default=ROOT / "models/backtest_january")
    parser.add_argument("--production-model-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/weather_cache")
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "data/processed/february_runs")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/february_forecasts")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    for key in ("january_model_dir", "production_model_dir", "cache_dir", "runs_dir", "output_root"):
        setattr(args, key, getattr(args, key).resolve())
    return execute(args)


if __name__ == "__main__":
    sys.exit(main())
