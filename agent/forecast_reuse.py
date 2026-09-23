"""Validate existing forecast versions without rerunning ML, including older schemas."""
import json

from agent.weather_adapter import ROOT, OUTPUT, adapt, digest, read_csv, utc, validate_model_time
from agent.weather_archive import obtain, select_run
from agent.weather_pipeline import csv_bytes, json_bytes, validate_predictions
from agent.power_alerts import analyze, FIELDS as ALERT_FIELDS
from scripts.build_weather_example import COLUMNS, forecast_rows


def compatible_versions(args, roots):
    """Return exact-issue/model/height candidates; never use another issue or run."""
    issue = utc(args.issue_time)
    selected = select_run(issue)
    model_bytes = (args.model_dir / "metadata.json").read_bytes()
    model_metadata = json.loads(model_bytes)
    validate_model_time(issue, model_metadata, args.source_timezone, args.observation_delay_hours)
    candidates = []
    for root in roots:
        folder = root / issue.strftime("%Y%m%dT%H%M%SZ") / selected.strftime("%Y%m%dT%H%M%SZ")
        for path in folder.glob("*/metadata.json"):
            metadata = json.loads(path.read_bytes())
            identity = metadata.get("identity", {})
            if (metadata.get("status") == "success" and identity.get("issue_time_utc") == args.issue_time
                    and identity.get("wind_height_m") == args.wind_height_m
                    and identity.get("model_metadata_sha256") == digest(model_bytes)
                    and identity.get("drop_threshold") == args.drop_threshold):
                candidates.append((path, metadata))
    # The latest compatible existing version is selected explicitly. If it is
    # corrupt, fail rather than silently falling back to a different version.
    return sorted(candidates, key=lambda item: (item[1].get("created_at_utc", ""), str(item[0])), reverse=True)


def reuse_version(args, path):
    """Check hashes, weather and inputs; append new audit fields to old predictions.

    Original files and power values remain unchanged. This is a schema migration
    in the aggregate only, not new inference or a claim of original UTC knowledge.
    """
    directory = path.parent
    metadata = json.loads(path.read_bytes())
    identity = metadata["identity"]
    if metadata["status"] != "success" or digest(json_bytes(identity)) != metadata["run_id"]:
        raise ValueError("Saved forecast identity checksum/status mismatch")
    expected = {"weather.csv", "weather_model_input.csv", "predictions.csv", "alerts.csv"}
    if set(metadata["file_sha256"]) != expected:
        raise ValueError("Incomplete forecast manifest")
    files = {name: (directory / name).read_bytes() for name in expected}
    if any(digest(files[name]) != value for name, value in metadata["file_sha256"].items()):
        raise ValueError("Saved forecast file checksum mismatch; no fallback or overwrite")
    model_bytes = (args.model_dir / "metadata.json").read_bytes()
    model_metadata = json.loads(model_bytes)
    if identity["model_metadata_sha256"] != digest(model_bytes):
        raise ValueError("Different model metadata")
    for turbine, entry in model_metadata["turbines"].items():
        if digest((args.model_dir / entry["artifact"]).read_bytes()) != entry["sha256"]:
            raise ValueError(f"Model artifact checksum mismatch: {turbine}")
        if identity["models"][turbine]["sha256"] != entry["sha256"]:
            raise ValueError("Saved inference used a different model")
    for name in ("prediction/interface.py", "prediction/__main__.py"):
        if identity["code_sha256"][name] != digest((ROOT / name).read_bytes().replace(b"\r\n", b"\n")):
            raise ValueError("Saved inference code changed; explicit new run needed")
    issue = utc(args.issue_time)
    selected = select_run(issue)
    if utc(identity["issue_time_utc"]) != issue or utc(identity["weather_run_time_utc"]) != selected:
        raise ValueError("Saved issue/weather run differs")
    # A saved result must have matching weather evidence locally. This path never
    # downloads weather to disguise a stale or unverifiable result as successful.
    body, request, weather_check, _, _ = obtain(issue, selected, args.cache_dir, args.seed_dir, offline=True)
    if digest(body) != identity["weather_sha256"] or request["request_parameters"] != identity["weather_request"]:
        raise ValueError("Saved weather revision differs from exact cache")
    weather = csv_bytes(COLUMNS, forecast_rows(json.loads(body), weather_check))
    if weather != files["weather.csv"]:
        raise ValueError("Saved weather table differs from checked API evidence")
    _, fields, current_rows = adapt(weather, issue, args.wind_height_m, model_metadata,
                                     args.source_timezone, args.observation_delay_hours)
    input_fields, input_rows = read_csv(files["weather_model_input.csv"])
    if digest(files["weather_model_input.csv"]) != identity["input_sha256"]:
        raise ValueError("Saved model input identity differs")
    predicted = validate_predictions(files["predictions.csv"], input_fields, input_rows)
    if len(predicted) != len(current_rows) or set(input_fields) - set(fields):
        raise ValueError("Unsupported old input schema")
    for old, current in zip(predicted, current_rows):
        if any(old[field] != current[field] for field in input_fields):
            raise ValueError("Saved inputs differ; refusing to reuse predictions")
        current[OUTPUT] = old[OUTPUT]
    alerts, pairs = analyze(current_rows, args.drop_threshold)
    if csv_bytes(ALERT_FIELDS, alerts) != files["alerts.csv"]:
        raise ValueError("Saved alerts differ from checked predictions")
    guard = validate_model_time(issue, model_metadata, args.source_timezone, args.observation_delay_hours)
    return current_rows, alerts, {
        "issue_time_utc": args.issue_time, "run_id": metadata["run_id"],
        "original_metadata_path": str(path.relative_to(ROOT)), "original_metadata_sha256": digest(path.read_bytes()),
        "original_file_sha256": metadata["file_sha256"], "weather_request_metadata": request,
        "weather_validation": weather_check, "model_time_check_for_this_schedule": guard,
        "original_model_time_check": metadata.get("model_time_check"),
        "added_audit_columns": sorted(set(fields) - set(input_fields)),
        "reuse_validation": "Hashes, exact weather revision, unchanged ML code/models/features, all 96 rows and alerts checked",
        "prediction_values_preserved": True, "pairs_checked": pairs,
    }
