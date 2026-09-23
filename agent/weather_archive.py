"""Exact-run cache; invalid/missing data never silently fall back to another run."""
from datetime import timedelta
import json
from pathlib import Path
import tempfile
from urllib.parse import urlencode

from agent.weather_adapter import digest
from agent.artifact_store import publish
from scripts.check_weather_archive import ENDPOINT, query, check, fetch


def select_run(issue, requested=None):
    if issue.minute or issue.second or issue.microsecond:
        raise ValueError("issue_time must be on a UTC hour for the hourly 1..48 contract")
    latest = issue - timedelta(hours=12)
    latest = latest.replace(hour=(latest.hour // 6) * 6)
    run = latest if requested is None else requested
    if run.minute or run.second or run.microsecond or run.hour % 6 or run > latest:
        raise ValueError("Weather run must be a 00/06/12/18 UTC cycle at least 12 hours before issue")
    if (issue - run).total_seconds() > 7 * 86400:
        raise ValueError("Requested run is more than 7 days old; refusing a stale weather selection")
    return run


def obtain(issue, run, cache_dir, seed_dir, offline=False):
    count = int((issue - run).total_seconds() / 3600) + 49
    params = query(run.date().isoformat(), run_time=run.strftime("%Y-%m-%dT%H:%M"), forecast_hours=count)
    url = ENDPOINT + "?" + urlencode(params)
    cache = Path(cache_dir) / digest(url.encode())

    def validate(body, metadata):
        return check(run.date().isoformat(), body, metadata, params=params, calculation=issue)

    if cache.exists():
        body = (cache / "response.json").read_bytes()
        metadata = json.loads((cache / "request.json").read_bytes())
        result = validate(body, metadata)  # Fail closed on corrupted or incomplete cache.
        return body, metadata, result, "cache", cache
    # Import the already captured evidence only if every request parameter matches.
    seed = None
    for path in sorted(Path(seed_dir).glob("*.request.json")):
        metadata = json.loads(path.read_bytes())
        if metadata.get("request_parameters") == params and metadata.get("request_url") == url:
            seed = ((path.parent / metadata["raw_file"]).read_bytes(), metadata)
            break
    if seed is None and offline:
        raise ValueError("Weather cache miss for the exact selected run/request in offline mode; no forecast produced")
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".weather-", dir=cache.parent) as temporary:
        staging = Path(temporary)
        if seed is None:
            body, metadata = fetch(url, staging / "response.json", staging / "request.json", params)
            origin = "api"
        else:
            body, metadata = seed
            origin = "saved_evidence"
            (staging / "response.json").write_bytes(body)
            (staging / "request.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        result = validate(body, metadata)
        # Publish new files with workspace-inherited permissions, not temporary ACLs.
        if cache.exists():  # Concurrent writer: only accept matching, valid evidence.
            existing = (cache / "response.json").read_bytes()
            existing_metadata = json.loads((cache / "request.json").read_bytes())
            validate(existing, existing_metadata)
            if existing != body:
                raise ValueError("Concurrent weather cache revision differs; use a new cache directory")
        else:
            publish(cache, {"response.json": body, "request.json": (staging / "request.json").read_bytes()})
    return body, metadata, result, origin, cache
