"""Single-issue forecast orchestration with immutable, validated run versions."""
import argparse
import csv
from datetime import datetime, timezone
from importlib.metadata import version
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

from agent.weather_adapter import ROOT, OUTPUT, WEATHER, adapt, digest, read_csv, utc, validate_model_time
from agent.weather_archive import obtain, select_run
from agent.power_alerts import analyze, FIELDS as ALERT_FIELDS
from agent.artifact_store import publish
from scripts.build_weather_example import COLUMNS, forecast_rows, stamp


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def validate_predictions(data, fields, rows):
    import math
    output_fields, predicted = read_csv(data)
    if output_fields != fields + [OUTPUT] or len(predicted) != len(rows):
        raise ValueError("Unexpected prediction columns or row count")
    for before, after in zip(rows, predicted):
        if any(str(before[k]) != after[k] for k in fields):
            raise ValueError("Prediction changed input values, time strings or row order")
        value = float(after[OUTPUT])
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Invalid normalized power; expected finite [0,1]")
    return predicted


def run(args):
    issue = utc(args.issue_time)
    weather_run = select_run(issue, utc(args.weather_run_time) if args.weather_run_time else None)
    analyze([], args.drop_threshold)  # Validate threshold before network/model work.
    model_bytes = (args.model_dir / "metadata.json").read_bytes()
    model_metadata = json.loads(model_bytes)
    validate_model_time(issue, model_metadata)
    models = {}
    for turbine in ("turbine_1", "turbine_2"):
        entry = model_metadata["turbines"][turbine]
        actual = digest((args.model_dir / entry["artifact"]).read_bytes())
        if actual != entry["sha256"]:
            raise ValueError(f"ML artifact checksum mismatch: {turbine}")
        models[turbine] = {"artifact": entry["artifact"], "sha256": actual}
    body, request, weather_check, weather_origin, cache_path = obtain(
        issue, weather_run, args.cache_dir, args.seed_dir, args.offline)
    weather_csv = csv_bytes(COLUMNS, forecast_rows(json.loads(body), weather_check))
    adapted, fields, rows = adapt(weather_csv, issue, args.wind_height_m, model_metadata)
    code_paths = ["agent/artifact_store.py", "agent/weather_pipeline.py", "agent/weather_archive.py", "agent/weather_adapter.py",
                  "agent/power_alerts.py", "scripts/check_weather_archive.py", "scripts/build_weather_example.py",
                  "prediction/interface.py", "prediction/__main__.py"]
    identity = {
        "schema_version": 1, "issue_time_utc": stamp(issue), "weather_run_time_utc": stamp(weather_run),
        "weather_model": request["request_parameters"]["models"],
        "weather_request": request["request_parameters"], "weather_sha256": digest(body),
        "input_sha256": digest(adapted), "wind_height_m": args.wind_height_m,
        "drop_threshold": args.drop_threshold, "models": models,
        "model_metadata_sha256": digest(model_bytes), "weather_provenance_status": "unverified",
        "environment": {"python": sys.version.split()[0], **{p: version(p) for p in ("catboost", "numpy", "pandas")}},
        "code_sha256": {p: digest((ROOT / p).read_bytes().replace(b"\r\n", b"\n")) for p in code_paths},
    }
    run_id = digest(json_bytes(identity))
    destination = args.output_root / issue.strftime("%Y%m%dT%H%M%SZ") / weather_run.strftime("%Y%m%dT%H%M%SZ") / run_id[:16]
    if destination.exists():
        metadata = json.loads((destination / "metadata.json").read_bytes())
        if metadata["identity"] != identity or metadata["status"] != "success":
            raise ValueError("Existing result identity/status mismatch; refusing reuse")
        expected_names = {"weather.csv", "weather_model_input.csv", "predictions.csv", "alerts.csv"}
        if set(metadata["file_sha256"]) != expected_names:
            raise ValueError("Incomplete result manifest")
        for name, expected in metadata["file_sha256"].items():
            if digest((destination / name).read_bytes()) != expected:
                raise ValueError(f"Corrupted result cache: {name}; no success returned")
        if (destination / "weather_model_input.csv").read_bytes() != adapted:
            raise ValueError("Cached model input differs")
        predicted = validate_predictions((destination / "predictions.csv").read_bytes(), fields, rows)
        alerts, pairs = analyze(predicted, args.drop_threshold)
        if (destination / "alerts.csv").read_bytes() != csv_bytes(ALERT_FIELDS, alerts):
            raise ValueError("Cached alerts differ from validated predictions")
        return {"status": "reused", "weather_origin": weather_origin, "rows": len(rows),
                "alerts": len(alerts), "output_dir": str(destination), "run_id": run_id}
    # Actual User 1 batch invocation; temporary results cannot look like completed runs.
    with tempfile.TemporaryDirectory() as temporary:
        source, target = Path(temporary) / "input.csv", Path(temporary) / "predictions.csv"
        source.write_bytes(adapted)
        command = [sys.executable, "-B", "-m", "prediction", "--model-dir", str(args.model_dir.resolve()),
                   "batch", "--input", str(source), "--output", str(target)]
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        predictions = target.read_bytes()
    predicted = validate_predictions(predictions, fields, rows)
    alerts, pairs = analyze(predicted, args.drop_threshold)
    outputs = {"weather.csv": weather_csv, "weather_model_input.csv": adapted,
               "predictions.csv": predictions, "alerts.csv": csv_bytes(ALERT_FIELDS, alerts)}
    metadata = {
        "status": "success", "run_id": run_id, "identity": identity,
        "issue_time_utc": stamp(issue), "weather_run_time_utc": stamp(weather_run),
        "weather_model": identity["weather_model"], "wind_height_m": args.wind_height_m,
        "weather_provenance_status": "unverified", "weather_request_metadata": request,
        "weather_cache_path": str(cache_path), "weather_origin_at_creation": weather_origin,
        "weather_validation": weather_check, "ml_model_metadata": model_metadata,
        "model_artifacts": models, "original_weather_fields": WEATHER,
        "feature_mapping": {"temperature_c": "temperature_2m_c", "wind_speed_ms": f"wind_speed_{args.wind_height_m}m_ms"},
        "wind_height_assumption": "Technical choice; hub and training sensor heights unconfirmed",
        "terrain_settings": {k: request["request_parameters"][k] for k in ("cell_selection", "elevation")},
        "availability_assumption": {"lag_hours": 12, "verified": False,
                                    "publication_time_utc": None,
                                    "basis": "Typical 4-6h plus 10min propagation, with 5h50 extra margin"},
        "validation": {"rows": len(rows), "missing_values": 0, "duplicate_keys": 0,
                       "input_fields_and_times_preserved": True, "horizons": "1..48 per turbine",
                       "prediction_range": [min(float(r[OUTPUT]) for r in predicted), max(float(r[OUTPUT]) for r in predicted)]},
        "alert_analysis": {"threshold": args.drop_threshold, "threshold_status": "demonstration_not_history_calibrated",
                           "definition": "P(t) - P(t+3h) >= threshold; absolute normalized-power difference",
                           "pairs_checked": pairs, "alerts": len(alerts),
                           "current_value": "Forecast at each target t, not observed power or issue-time power"},
        "file_sha256": {k: digest(v) for k, v in outputs.items()},
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "technical_cycle_not_accuracy_evaluation",
        "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
    }
    outputs["metadata.json"] = json_bytes(metadata)
    publish(destination, outputs)
    return {"status": "success", "weather_origin": weather_origin, "rows": len(rows),
            "alerts": len(alerts), "output_dir": str(destination), "run_id": run_id}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue-time", required=True, help="Explicit UTC timestamp on an hour")
    parser.add_argument("--weather-run-time", help="Optional eligible UTC initialization; default latest with 12h lag")
    parser.add_argument("--wind-height-m", type=int, choices=(10, 100, 200), required=True)
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--drop-threshold", type=float, default=0.20)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/weather_cache")
    parser.add_argument("--seed-dir", type=Path, default=ROOT / "data/weather_source_check")
    parser.add_argument("--output-root", "--output-dir", dest="output_root", type=Path, default=ROOT / "results/forecast_runs")
    parser.add_argument("--offline", action="store_true", help="Use exact cached/saved evidence only")
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as error:
        failure = {"status": "failed", "issue_time_utc": args.issue_time,
                   "requested_weather_run_time_utc": args.weather_run_time,
                   "error_type": type(error).__name__, "reason": str(error),
                   "weather_provenance_status": "unverified", "forecast_produced": False}
        directory = args.output_root / "failures"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8] + ".json")
        path.write_bytes(json_bytes(failure))
        print(json.dumps({**failure, "failure_report": str(path)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0
