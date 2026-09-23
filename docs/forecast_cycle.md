# Single-issue weather forecast cycle

The completed initial integration was committed as `689ed7b` and pushed to `origin/user2-weather-pipeline`. Safety stash `bc6017aeb6bec46cfe6a0a5d1fbf9fafd1df8eb0` remains intact. The Word document and local environment are excluded from commits.

## Automatic steps

1. Parse an explicit UTC issue on an hour; validate the selected ML model's training cutoff and artifact hashes.
2. Select the latest six-hour ECMWF cycle no later than issue minus 12 hours, or validate an explicit `--weather-run-time`. The 12-hour delay remains an unverified availability assumption. Explicit runs more than seven days old are rejected.
3. Find weather by exact URL/parameters, including initialization, coordinates, fields, units, terrain settings and requested horizon. Reuse only a checksum- and content-validated response. Import matching original evidence on first use; otherwise fetch exactly one run unless `--offline` is set.
4. Check model response, units, UTC hourly sequence, null/non-finite values and 48 future hours for each turbine. Convert to the shared contract, then map the selected wind height and temperature using the existing adapter.
5. Call User 1's unchanged batch CLI and verify 96 complete predictions, original field/time preservation and normalized-power range.
6. Check 90 same-turbine three-hour forecast pairs, using an absolute demonstration threshold. Save alerts, including a header-only file if none qualify.
7. Publish a complete result directory atomically. A repeated identity revalidates all result hashes and prediction/alert content, then returns `status=reused`; it does not rerun the model or change existing bytes/timestamps.

The implementation reuses `scripts/check_weather_archive.py` for requests, HTTP retrieval and validation, `scripts/build_weather_example.py` for contract mapping, the extracted `agent/weather_adapter.py`, and User 1's `prediction` module. `scripts/run_weather_integration.py` is the small CLI entry point. Models, training and User 1 prediction code are unchanged.

## Versioning and failures

Path: `results/forecast_runs/<issue UTC>/<weather initialization UTC>/<identity hash prefix>/`. Metadata retains the full identity hash. Identity includes issue/run, weather model/request/response hash, selected height, adapted input, ML artifacts/metadata, runtime/code versions and alert threshold. New weather initialization always has a distinct directory. Changing any material input creates a new version; no older outputs are deleted.

Weather cache keys include exact request parameters, not just coordinates or dates. Corrupt cache entries fail closed rather than being silently replaced. A changed source response can be captured in a fresh cache directory; its content hash creates a distinct output revision. There is no automatic “latest successful forecast” substitution. A requested new run missing from cache cannot reuse the preceding weather run.

HTTP errors, unavailable runs, invalid units, missing values/hours, checksum mismatches or inference failures exit nonzero. `failures/*.json` records `status=failed`, the requested issue and reason, and `forecast_produced=false`. Valid prior versions remain untouched. No incomplete result directory is published. Temporary files are not forecast versions. Invalid CLI syntax is rejected by argparse before running the cycle.

## February verification

Command (from the repository root):

```powershell
.\.venv\ml\python.exe -B scripts/run_weather_integration.py --issue-time 2026-02-14T12:00:00Z --wind-height-m 100 --model-dir models --drop-threshold 0.20 --offline
```

The first execution used the original saved HTTP response, validated it and populated the runtime cache. It selected weather initialization February 14 00:00 UTC and produced 48 targets per turbine, February 14 13:00 through February 16 12:00 UTC. A repeat returned `status=reused`, `weather_origin=cache`, 96 rows and 7 alerts. Tests additionally forbid network and inference calls during an identical repeat and check unchanged file bytes/mtimes.

Current output directory: [`../results/forecast_runs/20260214T120000Z/20260214T000000Z/64248dfb5e925d39/`](../results/forecast_runs/20260214T120000Z/20260214T000000Z/64248dfb5e925d39/). The earlier `c08050f69d1162f8` version is retained. Updating atomic publication to inherit workspace permissions on Windows changed the implementation hash and created the new version; both contain identical predictions and alerts.

The directory contains `weather.csv`, `weather_model_input.csv`, `predictions.csv`, `alerts.csv`, and `metadata.json`. Predictions equal the previous real integration example. Four alerts belong to turbine 1 and three to turbine 2. Example: turbine 1 drops from 0.8047818690 at February 15 07:00 UTC to 0.5689907117 at 10:00 UTC, a decrease of 0.2357911573. This is an absolute normalized-power change, not a relative percentage. Alert windows can overlap and are not distinct-event counts.

Verified failure cases include an offline exact-cache miss, a simulated HTTP 400 with no cache publication, and a null weather value despite a recomputed matching hash. The latter still fails semantic validation even if an old successful prediction exists. A changed selected cycle with missing weather fails rather than reusing old weather; a changed threshold creates another version preserving the first. A threshold of 1 produces a valid empty alert file. HTTP failure is simulated in tests; no claim of a real upstream outage is made.

All 30 tests passed: `python -B -m unittest prediction.test_interface scripts.test_weather_integration agent.test_weather_pipeline`. A synthetic timing fixture verifies separate versions for different weather initializations; it exists only in a temporary test directory and is not real forecast evidence. A real offline-miss CLI check produced [this failure report](../results/forecast_runs/failures/20260923T112359_8ddcc941.json) with exit code 1 and left the successful version intact. The new predictions were independently compared with the earlier integration CSV and matched all rows and values exactly.

## Limits

Only this February issue was exercised against real saved weather; no whole-month download, dashboard, historical accuracy scoring or retraining was performed. Status remains `unverified`. Neither the 12-hour allowance nor successful caching proves original operational provenance. Wind at 100 m remains a technical assumption. Final models are blocked before their conservative eligible time; a January backtest requires separately trained as-of models. Unknown SCADA timezone/interval labels and February observation access remain open. The 0.20 alert threshold is demonstration-only and has not been validated on historical events.
