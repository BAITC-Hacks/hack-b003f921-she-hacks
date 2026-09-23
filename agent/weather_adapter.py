#!/usr/bin/env python3
"""Adapt one saved weather issue and invoke the real prediction batch CLI offline."""

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import math
from pathlib import Path

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
    validate_model_time(issue, model_metadata)
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



def validate_model_time(issue, model_metadata):
    # The model cutoff has no source timezone. A whole-day buffer is a
    # conservative technical guard, not a certification of training availability.
    cutoff = datetime.fromisoformat(model_metadata["training_cutoff_exclusive"])
    if cutoff.tzinfo is not None:
        safe_after = cutoff.astimezone(timezone.utc)
    else:
        safe_after = cutoff.replace(tzinfo=timezone.utc) + timedelta(days=1)
    if issue < safe_after:
        raise ValueError("Final refit cannot be used at this issue time; an as-of-trained model is required")
