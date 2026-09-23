#!/usr/bin/env python3
"""Adapt one saved weather issue and invoke the real prediction batch CLI offline."""

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TIMES = ["issue_time_utc", "weather_run_time_utc", "target_time_utc"]
WEATHER = ["temperature_2m_c", "wind_speed_10m_ms", "wind_speed_100m_ms",
           "wind_speed_200m_ms", "wind_direction_100m_deg"]
OUTPUT = "predicted_normalized_power"
ALIASES = {"1": "turbine_1", "2": "turbine_2", "turbine_1": "turbine_1", "turbine_2": "turbine_2"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def utc(text):
    if not text.endswith(("Z", "+00:00")):
        raise ValueError(f"Expected explicit UTC: {text}")
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def read_csv(data):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    fields = reader.fieldnames or []
    if len(fields) != len(set(fields)):
        raise ValueError("Duplicate CSV headers")
    return fields, list(reader)


def adapt(data, issue, height, model_metadata):
    fields, all_rows = read_csv(data)
    required = TIMES + ["turbine_id", "forecast_horizon_h"] + WEATHER
    if set(required) - set(fields):
        raise ValueError("Missing weather contract columns")
    added = ["temperature_c", "wind_speed_ms", "wind_height_m", "weather_provenance_status"]
    if set(added + [OUTPUT]) & set(fields):
        raise ValueError("Refusing to overwrite existing adapter/prediction columns")
    # The model cutoff has no source timezone. A whole-day buffer is a
    # conservative technical guard, not a certification of training availability.
    cutoff = datetime.fromisoformat(model_metadata["training_cutoff_exclusive"])
    if cutoff.tzinfo is not None:
        safe_after = cutoff.astimezone(timezone.utc)
    else:
        safe_after = cutoff.replace(tzinfo=timezone.utc) + timedelta(days=1)
    if issue < safe_after:
        raise ValueError("Final refit cannot be used at this issue time; an as-of-trained model is required")
    rows, keys, runs = [], set(), set()
    horizons = {t: set() for t in ("turbine_1", "turbine_2")}
    wind = f"wind_speed_{height}m_ms"
    for source in all_rows:
        if utc(source["issue_time_utc"]) != issue:
            continue
        row = source.copy()
        turbine = ALIASES.get(row["turbine_id"].strip())
        if turbine is None:
            raise ValueError("Unsupported turbine_id")
        row["turbine_id"] = turbine
        run, target = (utc(row[k]) for k in TIMES[1:])
        horizon = int(row["forecast_horizon_h"])
        if (target - issue).total_seconds() != horizon * 3600 or horizon not in range(1, 49):
            raise ValueError("Incorrect issue-relative horizon")
        if target.minute or target.second or target.microsecond:
            raise ValueError("Target must be on the UTC hour")
        if issue - run < timedelta(hours=12):
            raise ValueError("Weather run violates the provisional 12-hour availability lag")
        key = (turbine, target)
        if key in keys:
            raise ValueError("Duplicate turbine/target in selected issue")
        keys.add(key)
        runs.add(run)
        horizons[turbine].add(horizon)
        for field in WEATHER:
            value = float(row[field])
            if not math.isfinite(value):
                raise ValueError(f"Non-finite weather: {field}")
            if field.startswith("wind_speed") and value < 0:
                raise ValueError("Negative wind speed")
        if not 0 <= float(row["wind_direction_100m_deg"]) <= 360:
            raise ValueError("Invalid wind direction")
        row.update(temperature_c=row["temperature_2m_c"], wind_speed_ms=row[wind],
                   wind_height_m=str(height), weather_provenance_status="unverified")
        rows.append(row)
    if len(rows) != 96 or len(runs) != 1 or any(h != set(range(1, 49)) for h in horizons.values()):
        raise ValueError("Expected one run, 48 hours and both turbines (96 rows)")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields + added, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8"), fields + added, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/weather_examples/v1/weather_forecasts.csv")
    parser.add_argument("--weather-metadata", type=Path,
                        default=ROOT / "data/weather_examples/v1/weather_forecasts.metadata.json")
    parser.add_argument("--issue-time", default="2026-02-14T12:00:00Z")
    parser.add_argument("--wind-height-m", type=int, choices=(10, 100, 200), required=True)
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "examples/integration_20260214_100m")
    args = parser.parse_args()
    issue = utc(args.issue_time)
    source = args.input.read_bytes()
    weather_metadata = json.loads(args.weather_metadata.read_bytes())
    if digest(source) != weather_metadata["csv_sha256"]:
        raise ValueError("Weather CSV checksum mismatch")
    model_bytes = (args.model_dir / "metadata.json").read_bytes()
    model_metadata = json.loads(model_bytes)
    adapted, fields, rows = adapt(source, issue, args.wind_height_m, model_metadata)
    selected_metadata = [r for r in weather_metadata["runs"] if utc(r["issue_time_utc"]) == issue]
    if len(selected_metadata) != 1 or utc(selected_metadata[0]["weather_run_time_utc"]) != utc(rows[0]["weather_run_time_utc"]):
        raise ValueError("Weather run metadata does not match selected rows")
    # Use the actual batch CLI without modifying User 1's interface or models.
    with tempfile.TemporaryDirectory() as directory:
        batch_input, batch_output = Path(directory) / "input.csv", Path(directory) / "output.csv"
        batch_input.write_bytes(adapted)
        command = [sys.executable, "-B", "-m", "prediction", "--model-dir", str(args.model_dir.resolve()),
                   "batch", "--input", str(batch_input), "--output", str(batch_output)]
        subprocess.run(command, cwd=ROOT, check=True)
        predicted = batch_output.read_bytes()
    output_fields, output_rows = read_csv(predicted)
    if output_fields != fields + [OUTPUT] or len(output_rows) != 96:
        raise ValueError("Unexpected output schema or row count")
    for before, after in zip(rows, output_rows):
        if any(before[k] != after[k] for k in fields):
            raise ValueError("Batch changed source values, time strings or row order")
        value = float(after[OUTPUT])
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Invalid predicted normalized power")
    stats = {}
    for turbine in ("turbine_1", "turbine_2"):
        values = [float(r[OUTPUT]) for r in output_rows if r["turbine_id"] == turbine]
        artifact = args.model_dir / model_metadata["turbines"][turbine]["artifact"]
        stats[turbine] = {"rows": len(values), "minimum": min(values), "maximum": max(values),
                          "model_sha256": digest(artifact.read_bytes())}
    metadata = {
        "purpose": "technical_integration_not_forecast_accuracy_evaluation",
        "weather_provenance_status": "unverified",
        "issue_time_utc": args.issue_time,
        "selected_wind_height_m": args.wind_height_m,
        "wind_height_assumption": "Technical feature choice, not confirmed turbine hub or training sensor height",
        "feature_mapping": {"temperature_c": "temperature_2m_c",
                            "wind_speed_ms": f"wind_speed_{args.wind_height_m}m_ms"},
        "original_weather_fields": WEATHER,
        "weather_dataset_id": weather_metadata["dataset_id"],
        "weather_csv_sha256": digest(source),
        "weather_metadata": selected_metadata[0],
        "model_metadata": model_metadata,
        "model_metadata_sha256": digest(model_bytes),
        "model_source_commit": subprocess.check_output(["git", "rev-parse", "origin/data-model"], cwd=ROOT, text=True).strip(),
        "environment": {"python": sys.version.split()[0], **{p: version(p) for p in ("catboost", "numpy", "pandas")}},
        "input_sha256": digest(adapted), "prediction_sha256": digest(predicted),
        "validation": {"rows": 96, "missing_values": 0, "duplicate_keys": 0,
                       "all_input_fields_and_time_strings_preserved": True,
                       "horizons": "1..48 per turbine; target minus issue", "turbines": stats},
        "output_postprocessing": "User 1 interface clips finite raw model predictions to [0,1]",
        "training_time_limitation": "No January backtest or Jan 31 12:00 run with final refits; need as-of-trained models and confirmed data arrival/timezone",
        "reproduction": "python scripts/run_weather_integration.py --issue-time " + args.issue_time
                        + " --wind-height-m " + str(args.wind_height_m),
        "batch_syntax": "python -m prediction --model-dir models batch --input INPUT.csv --output OUTPUT.csv",
    }
    outputs = {"weather_model_input.csv": adapted, "predictions.csv": predicted,
               "metadata.json": (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")}
    for name, content in outputs.items():
        path = args.output_dir / name
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"Refusing to overwrite {path}; use a new --output-dir")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        path = args.output_dir / name
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(content)
    print(json.dumps({"rows": 96, "output": str(args.output_dir / "predictions.csv"), "turbines": stats}, indent=2))


if __name__ == "__main__":
    main()
