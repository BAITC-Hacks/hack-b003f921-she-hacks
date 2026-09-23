#!/usr/bin/env python3
"""Preliminary January evaluation under explicit, unconfirmed time assumptions.

Reuse the forecast cycle and User 1 evaluator functions. Do not invoke the
confirmed-backtest CLI or attest verified publication times/provenance.
"""
import argparse
from datetime import datetime, timezone
import gzip
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data/processed/.matplotlib"))

import pandas as pd

from agent.artifact_store import publish
from agent.weather_adapter import digest, validate_model_time
from agent.weather_pipeline import run, json_bytes
from backtest.evaluate_january import (SCHEMA, evaluate, evaluation_window,
                                       load_actuals, source_to_utc)
from backtest.train_january import select_training


def csv_data(frame):
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")


def verify_training(directory, model_dir, zone, delay, first_issue):
    metadata = json.loads((model_dir / "metadata.json").read_bytes())
    if metadata.get("model_version") != "january-backtest-v1":
        raise ValueError("Use the separate January models, never the production refits")
    guard = validate_model_time(first_issue.to_pydatetime(), metadata, zone, delay)
    evidence = {}
    for turbine, entry in metadata["turbines"].items():
        source = directory / f"{turbine}_hourly.csv"
        if digest(source.read_bytes()) != entry["source_sha256"]:
            raise ValueError(f"Hourly source checksum differs from January training: {source}")
        if digest((model_dir / entry["artifact"]).read_bytes()) != entry["sha256"]:
            raise ValueError(f"Model checksum differs: {turbine}")
        selected, timestamps, _, _ = select_training(pd.read_csv(source))
        if len(selected) != entry["training_rows"] or str(timestamps.max()) != entry["training_last_timestamp_source"]:
            raise ValueError("Training selection disagrees with saved model metadata")
        available = source_to_utc(timestamps, zone) + pd.Timedelta(hours=1 + delay)
        if (available > first_issue).any():
            raise ValueError("A training interval was not completed/assumed available at the first issue")
        evidence[turbine] = {"source_sha256": entry["source_sha256"], "model_sha256": entry["sha256"],
                            "training_rows_checked": len(selected),
                            "latest_training_interval_end_utc": str(available.max() - pd.Timedelta(hours=delay)),
                            "latest_assumed_training_availability_utc": str(available.max())}
    return metadata, {"guard": guard, "turbines": evidence, "publication_availability_verified": False}


def collect(args, issues):
    frames, records, evidence = [], [], []
    for issue in issues:
        options = argparse.Namespace(issue_time=issue.isoformat().replace("+00:00", "Z"),
            weather_run_time=None, wind_height_m=args.wind_height_m, model_dir=args.model_dir,
            source_timezone=args.source_timezone, observation_delay_hours=args.observation_delay_hours,
            drop_threshold=0.20, cache_dir=args.cache_dir, seed_dir=ROOT / "data/weather_source_check",
            output_root=args.runs_dir, offline=args.offline)
        try:
            result = run(options)
            path = Path(result["output_dir"])
            frame = pd.read_csv(path / "predictions.csv", dtype=str)
            metadata = json.loads((path / "metadata.json").read_bytes())
            frames.append(frame)
            records.append({"issue_time_utc": options.issue_time, "status": result["status"],
                            "forecast_rows": len(frame), "run_id": result["run_id"],
                            "output_dir": str(path.relative_to(ROOT)), "error": ""})
            evidence.append({"issue_time_utc": options.issue_time,
                "weather_run_time_utc": metadata["weather_run_time_utc"],
                "run_id": result["run_id"], "forecast_sha256": metadata["file_sha256"]["predictions.csv"],
                "request": metadata["weather_request_metadata"],
                "weather_validation": metadata["weather_validation"],
                "model_time_check": metadata["model_time_check"]})
            print(f"{options.issue_time}: {result['status']}, {len(frame)} rows", flush=True)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as error:
            records.append({"issue_time_utc": options.issue_time, "status": "failed", "forecast_rows": 0,
                            "run_id": "", "output_dir": "", "error": f"{type(error).__name__}: {error}"})
            print(f"{options.issue_time}: FAILED: {error}; continuing with next issue", flush=True)
    return frames, pd.DataFrame(records), evidence


def assumed_availability(actuals, delay):
    manifest = actuals[["turbine_id", "target_time_utc"]].copy()
    manifest["available_time_utc"] = manifest.target_time_utc + pd.Timedelta(hours=1 + delay)
    for column in ("target_time_utc", "available_time_utc"):
        manifest[column] = manifest[column].map(lambda t: t.isoformat().replace("+00:00", "Z"))
    manifest["availability_status"] = "assumed"
    return manifest


def coverage_report(forecasts, audit, issues, zone, issue_records):
    start, end = evaluation_window(zone)
    month = pd.date_range(start, end, freq="h", inclusive="left")
    scheduled = pd.DatetimeIndex(sorted({i + pd.Timedelta(hours=h) for i in issues for h in range(1, 49)
                                        if start <= i + pd.Timedelta(hours=h) < end}))
    scheduled_missing = month.difference(scheduled)
    records = []
    missing_rows = []
    for turbine in ("turbine_1", "turbine_2"):
        group = audit.loc[audit.turbine_id.eq(turbine)]
        covered = pd.DatetimeIndex(group.target_time_utc.unique()).sort_values()
        missing = month.difference(covered)
        for target in missing:
            missing_rows.append({"turbine_id": turbine, "target_time_utc": target.isoformat(),
                                 "reason": "outside_issue_schedule" if target not in scheduled else "failed_issue"})
        records.append({"turbine_id": turbine, "january_hours": len(month),
            "forecast_rows": len(group), "unique_forecast_hours": len(covered),
            "evaluated_rows": int(group.evaluated.sum()),
            "evaluated_unique_hours": int(group.loc[group.evaluated, "target_time_utc"].nunique()),
            "missing_actual_rows": int(group.actual_missing.sum()),
            "missing_actual_unique_hours": int(group.loc[group.actual_missing, "target_time_utc"].nunique()),
            "baseline_unavailable_rows": int(group.baseline_status.eq("baseline_unavailable").sum()),
            "baseline_stale_rows": int(group.baseline_status.eq("baseline_stale").sum()),
            "uncovered_january_hours": len(missing),
            "first_target_utc": str(covered.min()) if len(covered) else None,
            "last_target_utc": str(covered.max()) if len(covered) else None})
    return {"january_start_utc": str(start), "january_end_exclusive_utc": str(end),
            "source_timezone_assumed": zone, "requested_issues": len(issues),
            "successful_issues": int(issue_records.status.ne("failed").sum()),
            "failed_issues": int(issue_records.status.eq("failed").sum()),
            "full_forecast_rows_including_outside_january": len(forecasts),
            "january_forecast_rows": len(audit), "excluded_outside_january_rows": len(forecasts) - len(audit),
            "schedule_uncovered_hours_per_turbine": len(scheduled_missing), "turbines": records}, pd.DataFrame(
                missing_rows, columns=["turbine_id", "target_time_utc", "reason"])


def execute(args):
    if not 1 <= args.first_day <= args.last_day <= 30:
        raise ValueError("Issue days must be within January 1..30")
    issues = pd.date_range(f"2026-01-{args.first_day:02}T12:00:00Z",
                           f"2026-01-{args.last_day:02}T12:00:00Z", freq="D")
    model_metadata, training_check = verify_training(args.processed_dir, args.model_dir, args.source_timezone,
                                                     args.observation_delay_hours, issues[0])
    frames, issue_records, evidence = collect(args, issues)
    settings = {"source_timezone": args.source_timezone, "source_timezone_status": "assumed",
                "timestamp_label": "interval_start_assumed", "weather_availability_status": "assumed",
                "weather_availability_lag_hours": 12, "weather_provenance_status": "unverified",
                "scada_availability_status": "assumed", "observation_delay_hours": args.observation_delay_hours,
                "wind_height_m": args.wind_height_m, "wind_height_status": "technical_assumption_not_confirmed_hub_height",
                "first_day": args.first_day, "last_day": args.last_day}
    files = {"issues.csv": csv_data(issue_records)}
    if not frames:
        files["evaluation_metadata.json"] = json_bytes({"status": "failed_no_forecasts", "settings": settings})
        destination = args.output_root / ("failed_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        publish(destination, files)
        print(f"No evaluation possible; failure report: {destination}")
        return 1
    forecasts = pd.concat(frames, ignore_index=True)
    target = pd.to_datetime(forecasts.target_time_utc, utc=True)
    start, end = evaluation_window(args.source_timezone)
    january = forecasts.loc[target.ge(start) & target.lt(end)].copy()
    actuals = load_actuals(args.processed_dir, args.source_timezone)
    availability = assumed_availability(actuals, args.observation_delay_hours)
    # Numerical evaluator is reused; its confirmed-provenance CLI is NOT invoked.
    audit, metrics = evaluate(january, actuals, availability, model_metadata, source_timezone=args.source_timezone)
    coverage, missing = coverage_report(forecasts, audit, issues, args.source_timezone, issue_records)
    compact_columns = SCHEMA + ["wind_height_m", "weather_availability_status", "weather_provenance_status"]
    files["forecasts.csv"] = csv_data(january[compact_columns])
    files["metrics.csv"] = csv_data(pd.DataFrame(metrics))
    files["forecast_case_audit.csv.gz"] = gzip.compress(csv_data(audit), mtime=0)
    files["coverage.json"] = json_bytes(coverage)
    files["uncovered_hours.csv"] = csv_data(missing)
    baseline = audit[["turbine_id", "issue_time_utc", "baseline_source_time_utc",
                      "baseline_available_time_utc", "baseline_prediction", "baseline_status"]].drop_duplicates()
    baseline["availability_status"] = "assumed"
    files["baseline_availability.csv"] = csv_data(baseline)
    files["weather_evidence.json"] = json_bytes(evidence)
    code_paths = ["scripts/run_january_evaluation.py", "scripts/prepare_hourly.ps1", "agent/weather_adapter.py",
                  "agent/weather_pipeline.py", "agent/weather_archive.py", "scripts/check_weather_archive.py",
                  "scripts/build_weather_example.py", "backtest/evaluate_january.py", "backtest/train_january.py",
                  "prediction/interface.py", "agent/artifact_store.py", "agent/power_alerts.py"]
    identity = {"settings": settings, "training_check": training_check,
                "model_metadata_sha256": digest((args.model_dir / "metadata.json").read_bytes()),
                "code_sha256": {p: digest((ROOT / p).read_bytes().replace(b"\r\n", b"\n")) for p in code_paths},
                "forecast_sha256": digest(files["forecasts.csv"]),
                "successful_run_ids": issue_records.loc[issue_records.status.ne("failed"), "run_id"].tolist()}
    version_id = digest(json_bytes(identity))[:16]
    metadata = {"status": "preliminary_january_evaluation_with_time_and_archive_assumptions",
                "schedule_complete": not issue_records.status.eq("failed").any(),
                "identity": identity, "weather_provenance_status": "unverified",
                "training_publication_availability_verified": False, "real_archival_forecasts_attested": False,
                "weather_historical_publication_verified": False,
                "scada_source_timezone_confirmed": False, "scada_availability_verified": False,
                "environment": {"python": sys.version.split()[0],
                    **{p: version(p) for p in ("catboost", "numpy", "pandas", "scikit-learn", "matplotlib")}},
                "training_availability_status": "assumed_after_hour_end_plus_delay",
                "case_weighting": "Each issue/turbine/target is a case; overlapping issues retained",
                "baseline": "Persistence; latest finite completed hour assumed available by issue, maximum age 24h; paired cases",
                "partial_actual_hours": "Finite means accepted by existing evaluator; no filling",
                "raw_sources": {p.name: digest(p.read_bytes()) for p in (ROOT / "data/raw").glob("*.csv")},
                "file_sha256": {name: digest(body) for name, body in files.items()},
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "command_arguments": sys.argv[1:],
                "limitations": ["Not a confirmed historical backtest", "SCADA revisions and publication times unknown",
                                "Retrospectively trained in September; hyperparameter selection independence unverified",
                                "Weather initialization does not prove historical publication or operational origin",
                                "Wind-height compatibility with measured training weather is unconfirmed"]}
    files["evaluation_metadata.json"] = json_bytes(metadata)
    destination = args.output_root / version_id
    if destination.exists():
        previous = json.loads((destination / "evaluation_metadata.json").read_bytes())
        if previous["identity"] != identity:
            raise ValueError("Existing evaluation identity differs")
        for name, expected in previous["file_sha256"].items():
            if digest((destination / name).read_bytes()) != expected:
                raise ValueError(f"Corrupted existing evaluation: {name}")
        print(f"Validated existing evaluation: {destination}", flush=True)
    else:
        publish(destination, files)
        print(f"Preliminary evaluation saved to {destination}", flush=True)
    print(pd.DataFrame(metrics).to_string(index=False))
    print(json.dumps(coverage, indent=2))
    return 1 if issue_records.status.eq("failed").any() else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-timezone", required=True, help="Explicit assumption, e.g. Etc/GMT-5 = UTC+05")
    parser.add_argument("--observation-delay-hours", required=True, type=float, help="Assumed delay after hour end")
    parser.add_argument("--first-day", type=int, default=1)
    parser.add_argument("--last-day", type=int, default=30)
    parser.add_argument("--wind-height-m", type=int, choices=(10, 100, 200), default=100)
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models/backtest_january")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/weather_cache")
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "data/processed/january_runs")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/january_preliminary")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    # Canonical paths also allow relative CLI arguments in manifest references.
    for name in ("model_dir", "processed_dir", "cache_dir", "runs_dir", "output_root"):
        setattr(args, name, getattr(args, name).resolve())
    return execute(args)


if __name__ == "__main__":
    sys.exit(main())
