#!/usr/bin/env python3
"""Build an immutable CSV handoff from the two saved responses, without network I/O."""

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path

from check_weather_archive import DATES, ROOT, check

FIELD_MAP = {
    "temperature_2m_c": "temperature_2m",
    "wind_speed_10m_ms": "wind_speed_10m",
    "wind_speed_100m_ms": "wind_speed_100m",
    "wind_speed_200m_ms": "wind_speed_200m",
    "wind_direction_100m_deg": "wind_direction_100m",
}
COLUMNS = ["issue_time_utc", "weather_run_time_utc", "target_time_utc", "turbine_id",
           "forecast_horizon_h", *FIELD_MAP]


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build(dataset_id="weather_handoff_example_v1"):
    rows, runs = [], []
    for day in DATES:
        relative = Path("data/weather_source_check") / f"ecmwf_ifs_{day}_00.json"
        request_relative = relative.with_suffix(".request.json")
        body = (ROOT / relative).read_bytes()
        request_body = (ROOT / request_relative).read_bytes()
        request = json.loads(request_body)
        result = check(day, body, request)
        payload = json.loads(body)
        issue, run = parse(result["calculation_utc"]), parse(result["initialization_utc"])
        for location, grid in zip(payload, result["locations"]):
            turbine = f"turbine_{grid['turbine']}"
            hourly = location["hourly"]
            times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly["time"]]
            for horizon in range(1, 49):
                target = issue + timedelta(hours=horizon)
                i = times.index(target)
                row = {"issue_time_utc": stamp(issue), "weather_run_time_utc": stamp(run),
                       "target_time_utc": stamp(target), "turbine_id": turbine,
                       "forecast_horizon_h": int((target - issue).total_seconds() / 3600)}
                row.update({dest: hourly[src][i] for dest, src in FIELD_MAP.items()})
                rows.append(row)
        runs.append({
            "issue_time_utc": stamp(issue), "weather_run_time_utc": stamp(run),
            "model": request["request_parameters"]["models"],
            "source": "Open-Meteo Single Runs API / ECMWF IFS",
            "request_url": request["request_url"],
            "request_parameters": request["request_parameters"],
            "retrieved_at_utc": request["retrieved_at_utc"],
            "raw_response_path": relative.as_posix(), "raw_response_sha256": request["response_sha256"],
            "request_metadata_path": request_relative.as_posix(),
            "request_metadata_sha256": hashlib.sha256(request_body).hexdigest(),
            "weather_publication_time_utc": None,
            "historical_api_availability_time_utc": None,
            "provenance_status": "unresolved_operational_vs_retrospective",
            "locations": [{"turbine_id": f"turbine_{g['turbine']}",
                           **{k: g[k] for k in ("requested_latitude", "requested_longitude",
                                               "grid_latitude", "grid_longitude", "grid_elevation_m")}}
                          for g in result["locations"]],
            "same_grid_cell": result["same_grid_cell"],
            "terrain_settings": {"cell_selection": "nearest", "elevation": ["nan", "nan"],
                                 "elevation_downscaling": False},
            "availability_assumption": {
                "lag_hours_from_initialization": 12,
                "assumed_available_by_utc": stamp(run + timedelta(hours=12)),
                "verified": False,
                "basis": "Typical 4-6 h processing plus 10 min propagation; 5 h 50 min extra margin.",
                "limitation": "Does not prove original operational provenance or actual publication time.",
            },
        })
    rows.sort(key=lambda r: tuple(r[k] for k in COLUMNS[:4]))
    keys, groups = set(), {}
    for row in rows:
        key = tuple(row[k] for k in COLUMNS[:4])
        if key in keys:
            raise ValueError(f"Duplicate row key: {key}")
        keys.add(key)
        seconds = (parse(row["target_time_utc"]) - parse(row["issue_time_utc"])).total_seconds()
        if seconds != row["forecast_horizon_h"] * 3600 or not 1 <= row["forecast_horizon_h"] <= 48:
            raise ValueError("Invalid issue-relative forecast horizon")
        group = (row["issue_time_utc"], row["weather_run_time_utc"], row["turbine_id"])
        groups.setdefault(group, set()).add(row["forecast_horizon_h"])
    if len(rows) != 192 or len(groups) != 4 or any(h != set(range(1, 49)) for h in groups.values()):
        raise ValueError("Expected 2 runs x 2 turbines x 48 future hours")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = stream.getvalue().encode("utf-8")
    metadata = {
        "schema_version": "1.0",
        "dataset_id": dataset_id,
        "status": "integration_example_provenance_unresolved",
        "csv_file": "weather_forecasts.csv",
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "row_count": len(rows), "columns": COLUMNS,
        "primary_key_within_dataset": COLUMNS[:4],
        "field_mapping": FIELD_MAP,
        "units": {"forecast_horizon_h": "h", "temperature_2m_c": "degC",
                  "wind_speed_10m_ms": "m/s", "wind_speed_100m_ms": "m/s",
                  "wind_speed_200m_ms": "m/s", "wind_direction_100m_deg": "degree"},
        "coordinate_reference_system": "WGS84",
        "weather_height_reference": "above_model_ground",
        "issue_time_semantics": "simulated_project_calculation_time_not_provider_publication",
        "test_period_timezone": None,
        "scada_interval_label_convention": None,
        "transformations": "Select issue+1..48h, rename fields, label UTC; no value conversion or filling.",
        "provenance_review": "docs/weather_archive_provenance.md",
        "attribution": "ECMWF via Open-Meteo; https://open-meteo.com/en/licence (CC BY 4.0)",
        "runs": runs,
    }
    return csv_bytes, (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/weather_examples/v1")
    parser.add_argument("--dataset-id", default="weather_handoff_example_v1")
    args = parser.parse_args()
    if not args.dataset_id.strip():
        parser.error("--dataset-id must not be empty")
    csv_bytes, metadata_bytes = build(args.dataset_id)
    outputs = {args.output_dir / "weather_forecasts.csv": csv_bytes,
               args.output_dir / "weather_forecasts.metadata.json": metadata_bytes}
    # A rerun may verify identical bytes, but never overwrite an older revision.
    for path, content in outputs.items():
        if path.exists() and path.read_bytes() != content:
            raise SystemExit(f"Refusing to overwrite {path}; use a new --output-dir for a new revision.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        if not path.exists():
            with path.open("xb") as file:
                file.write(content)
    print(f"Verified 192 rows, four complete 1..48 h groups; CSV: {args.output_dir / 'weather_forecasts.csv'}")


if __name__ == "__main__":
    main()
