#!/usr/bin/env python3
"""Check two archived ECMWF runs; no observations, reanalysis, or model fallback.

Python 3.10+, standard library only. Run from any directory:
    python scripts/check_weather_archive.py
    python scripts/check_weather_archive.py --offline
Raw API response bodies and request provenance are saved separately.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://single-runs-api.open-meteo.com/v1/forecast"
MODEL = "ecmwf_ifs"
DATES = ("2026-01-31", "2026-02-14")
TURBINES = ((43.645150, 78.535604), (43.643198, 78.538828))
UNITS = {
    "temperature_2m": "\u00b0C",
    "wind_speed_10m": "m/s",
    "wind_speed_100m": "m/s",
    "wind_speed_200m": "m/s",
    "wind_direction_100m": "\u00b0",
}


def utc(value):
    return value.isoformat(timespec="minutes").replace("+00:00", "Z")


def query(day):
    return {
        "latitude": ",".join(f"{p[0]:.6f}" for p in TURBINES),
        "longitude": ",".join(f"{p[1]:.6f}" for p in TURBINES),
        "models": MODEL,
        "run": f"{day}T00:00",
        "hourly": ",".join(UNITS),
        "wind_speed_unit": "ms",
        "temperature_unit": "celsius",
        "timezone": "GMT",
        "timeformat": "iso8601",
        # Single Runs rejects start_hour. Fetch init+0 through init+60,
        # then select calculation+1 through calculation+48 by valid time.
        "forecast_hours": 61,
        "cell_selection": "nearest",
        # Disable elevation downscaling to make the grid comparison explicit.
        "elevation": "nan,nan",
    }


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url, raw_path, metadata_path, params):
    requested = utc(datetime.now(timezone.utc))
    request = Request(url, headers={"User-Agent": "SheHacks-WeatherArchiveCheck/1.0"})
    try:
        with urlopen(request, timeout=60) as response:
            status, body = response.status, response.read()
            headers = dict(response.headers)
    except HTTPError as error:
        status, body = error.code, error.read()
        headers = dict(error.headers)
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Network failure for {url}: {error}") from error
    raw_path.write_bytes(body)
    metadata = {
        "request_url": url,
        "request_parameters": params,
        "requested_at_utc": requested,
        "retrieved_at_utc": utc(datetime.now(timezone.utc)),
        "http_status": status,
        "http_date": headers.get("Date"),
        "content_type": headers.get("Content-Type"),
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "raw_file": raw_path.name,
        "historical_publication_time_utc": None,
    }
    save_json(metadata_path, metadata)
    return body, metadata


def check(day, body, metadata):
    params = query(day)
    url = ENDPOINT + "?" + urlencode(params)
    if metadata["request_url"] != url or metadata["request_parameters"] != params:
        raise ValueError("Saved request does not match the required model, run and parameters")
    if hashlib.sha256(body).hexdigest() != metadata["response_sha256"]:
        raise ValueError("Raw response checksum mismatch")
    if metadata["http_status"] != 200:
        raise ValueError(f"HTTP {metadata['http_status']}: {body.decode('utf-8', errors='replace')}")
    payload = json.loads(body)
    if not isinstance(payload, list) or len(payload) != len(TURBINES):
        raise ValueError(f"Expected exactly two location responses: {str(payload)[:500]}")
    init = datetime.fromisoformat(params["run"]).replace(tzinfo=timezone.utc)
    calculation = init + timedelta(hours=12)
    expected_raw = [init + timedelta(hours=i) for i in range(61)]
    expected_target = [calculation + timedelta(hours=i) for i in range(1, 49)]
    result = {
        "date": day,
        "model_requested": MODEL,
        "initialization_utc": utc(init),
        "calculation_utc": utc(calculation),
        "publication_utc": None,
        "assumed_availability_lag_hours": 12,
        "availability_verified": False,
        "target_start_utc": utc(expected_target[0]),
        "target_end_utc": utc(expected_target[-1]),
        "model_lead_hours": [13, 60],
        "locations": [],
    }
    for index, (location, requested) in enumerate(zip(payload, TURBINES)):
        if location.get("location_id", 0) != index:
            raise ValueError("Unexpected location order")
        if location["utc_offset_seconds"] != 0 or location["timezone"] != "GMT":
            raise ValueError("Expected explicit UTC/GMT response")
        hourly = location["hourly"]
        times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly["time"]]
        if times != expected_raw:
            raise ValueError("Missing, duplicated, out-of-order or unexpected raw timestamps")
        selected = [times.index(t) for t in expected_target]
        fields = {}
        for field, unit in UNITS.items():
            if location["hourly_units"].get(field) != unit:
                raise ValueError(f"Unexpected unit for {field}")
            values = hourly.get(field, [])
            if len(values) != len(times):
                raise ValueError(f"Incorrect array length for {field}")
            bad = sum(v is None or isinstance(v, bool) or not isinstance(v, (int, float))
                      or not math.isfinite(v) for v in values)
            if bad:
                raise ValueError(f"{field}: {bad} null/non-finite/non-numeric raw values")
            if field.startswith("wind_speed") and any(v < 0 for v in values):
                raise ValueError(f"Negative {field}")
            if field.startswith("wind_direction") and any(not 0 <= v <= 360 for v in values):
                raise ValueError(f"Invalid {field}")
            window = [values[i] for i in selected]
            fields[field] = {"unit": unit, "count": len(window), "missing": 0,
                             "minimum": min(window), "maximum": max(window)}
        result["locations"].append({
            "turbine": index + 1,
            "requested_latitude": requested[0], "requested_longitude": requested[1],
            "grid_latitude": location["latitude"], "grid_longitude": location["longitude"],
            "grid_elevation_m": location["elevation"],
            "raw_hours": len(times), "target_hours": len(selected),
            "fields": fields,
        })
    result["same_grid_cell"] = all(payload[0][k] == payload[1][k]
                                   for k in ("latitude", "longitude", "elevation"))
    result["identical_hourly_values"] = payload[0]["hourly"] == payload[1]["hourly"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Validate saved responses without network access")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "weather_source_check")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"source": ENDPOINT, "runs": [], "errors": []}
    for day in DATES:
        raw_path = args.output_dir / f"ecmwf_ifs_{day}_00.json"
        meta_path = args.output_dir / f"ecmwf_ifs_{day}_00.request.json"
        try:
            params = query(day)
            if args.offline:
                body = raw_path.read_bytes()
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            else:
                body, metadata = fetch(ENDPOINT + "?" + urlencode(params), raw_path, meta_path, params)
            result = check(day, body, metadata)
            summary["runs"].append(result)
            print(f"{day}: PASS; both turbines: 48/48 hours, no missing values; "
                  f"same grid={result['same_grid_cell']}; publication time UNVERIFIED")
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            summary["errors"].append({"date": day, "reason": str(error)})
            print(f"{day}: FAIL: {error}", file=sys.stderr)
    save_json(args.output_dir / "validation.json", summary)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
