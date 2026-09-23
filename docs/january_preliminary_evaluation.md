# Preliminary January evaluation with time and archive assumptions

This is a retrospective, preliminary evaluation, not a confirmed historical backtest. Weather provenance remains **unverified**. No production model, raw CSV, prior report, or earlier forecast version was overwritten. No timezone was selected by comparing scores.

## Integration and input verification

Merged `origin/data-model` at `7e72522` into `user2-weather-pipeline` with merge commit `76680ac`. The only conflict was independent additions to `.gitignore`; both the cache exclusion and January model exceptions were retained. Safety branch `safety/pre-january-integration-20260923` and the pre-existing stash were retained. `data/processed/pre_january_safety.json` is a local, ignored before/after hash record. The untracked original `Кейс.docx` remains untouched.

Raw inputs are local, ignored `data/raw/turbine 1.csv` and `data/raw/turbine 2.csv`. They contain 142,360 and 149,499 observations, respectively, from March 11, 2023 through January 31, 2026 23:50 in the unconfirmed source clock. The files contain no February measurements. Existing `scripts/prepare_hourly.ps1` produced 25,392 hourly rows per turbine without changing the raw files. Both generated CSV hashes match the training-source hashes in `models/backtest_january/metadata.json` exactly:

| Turbine | Raw SHA-256 | Hourly SHA-256 |
| --- | --- | --- |
| 1 | `c4c341582fb2dd348b7187f0128cff265fe055f469413871ebb5db50eef58b5b` | `a61619e174a892462674e2277526b863aab994df8ac872285b4d8eefffef766e` |
| 2 | `820578cd18bb557cd30c2e102f3ae5a386dfc6c489a5a15743339c2b017305e5` | `fd9d111ed43f7fa0cd6da4c9009e13691c65a2406b35d4ebb1b1d900fc7f9b40` |

Raw checks found zero duplicate timestamps, invalid timestamps, off-grid 10-minute timestamps, missing fields, or invalid numbers. Gaps elsewhere in the history remain gaps; no interpolation was introduced. January has 744 complete six-observation hours per turbine, with no missing hourly power. Full preparation diagnostics remain local in `data/processed/data_quality_report.json`.

## Time and model eligibility assumptions

- Source January timestamps are assumed to be **fixed UTC+05**, configured as `Etc/GMT-5`; this is not an assertion of the historical civil timezone at the site. The same fixed mapping applies to training boundaries. Timestamp labels are assumed to mark interval starts. Hourly facts represent `[target, target+1h)`.
- SCADA availability is assumed to be hour end + `--observation-delay-hours`; **0 hours** was explicitly selected for this preliminary run. Actual historical publication/revision times are unknown. This assumption applies to training eligibility and baseline selection alike.
- The January artifacts (`january-backtest-v1`) contain 23,019 / 24,260 eligible pre-January training hours. Their last training hour starts December 31 at 23:00 source time and ends January 1 at 00:00 source time: **December 31 at 19:00 UTC** under the selected mapping. The first issue is January 1 at 12:00 UTC, 17 hours later. The guard checks the end of the interval plus assumed latency, not just its start. Source/model hashes and reconstructed eligible training counts are verified before downloads.
- Both `models/backtest_january/*.cbm` are used. Production `models/*.cbm` and metadata retain their original hashes. Production models remain rejected for January and January 31 12:00 UTC, including with this explicit timezone mapping.
- These artifacts were physically trained in September. This is a simulation of a pre-January training selection, not evidence of an actual January deployment. Model-family/hyperparameter choices previously involved validation including January; independence of model selection from this evaluation is not established.

## Weather and execution

Requested 30 ECMWF IFS single runs at 00:00 UTC, January 1–30, from Open-Meteo Single Runs API through the existing loader. Each issue is at 12:00 UTC of that day; each forecast selects issue+1 through issue+48. Wind is 100 m above model ground, an explicit technical assumption rather than a confirmed hub/training-sensor height. Temperature is at 2 m. Original 10/100/200 m wind fields, direction, requested coordinates, grid coordinates, terrain settings, request URLs, hashes, and retrieval times are retained in per-run evidence.

`weather_available_time_utc = weather_run_time_utc + 12h` has status **assumed**. Actual historical API publication is unknown. HTTP 200 and the existence of an initialization do not establish operational rather than retrospective origin. `weather_provenance_status=unverified` remains in rows and metadata. There is no measured-weather or reanalysis fallback.

All 30 real responses passed checks for units, timestamps, finite values, full 48-hour coverage, and both turbine locations. Both turbines select the same grid cell for every run. Predictions are turbine-specific. Download retries are bounded to three attempts for network errors / HTTP 429 / HTTP 5xx, with 2s and 4s backoff; invalid content and permanent HTTP errors fail without using a different run. Failed issues are recorded and later issues continue. Any failed issue makes the wrapper exit nonzero, even if partial metrics can be computed.

First, one issue was downloaded and evaluated. Then all 30 were processed. A complete offline repeat reused all 30 validated forecasts and the existing evaluation without downloads or inference. Cache paths are request hashes under ignored `data/weather_cache/`. Full immutable run folders are local under ignored `data/processed/january_runs/`; their exact paths and run IDs are in `issues.csv`. Code, weather, and model changes create new versions. Older versions are retained.

## Coverage and paired metrics

Local January maps to **[2025-12-31 19:00 UTC, 2026-01-31 19:00 UTC)**. The first predicted target is January 1 at 13:00 UTC / 18:00 assumed local time. Thus the first **18 local-January hours per turbine are not covered** by this schedule. Last evaluated target is January 31 at 18:00 UTC / 23:00 local. This is a schedule gap, not missing SCADA.

All **30/30 issues** succeeded: 2,880 full-horizon predictions; 36 target rows outside local January were excluded only from evaluation, leaving **2,844 paired cases**. Each turbine has 1,422 evaluated cases covering **726 distinct hours out of 744**. Each `(turbine, issue, target)` is one equally weighted case; repeated targets from different issues remain separate. Unique-hour counts across horizon bands must not be added because they overlap.

| Turbine | Horizon | Evaluated cases / unique hours within band | ML MAE | ML RMSE | Persistence MAE | Persistence RMSE |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| turbine_1 | 1–24 h | 720 / 720 | 0.151585 | 0.231329 | 0.302303 | 0.431223 |
| turbine_1 | 25–48 h | 702 / 702 | 0.172892 | 0.256884 | 0.379551 | 0.490082 |
| turbine_2 | 1–24 h | 720 / 720 | 0.155823 | 0.238020 | 0.300620 | 0.432194 |
| turbine_2 | 25–48 h | 702 / 702 | 0.175617 | 0.260669 | 0.379563 | 0.491242 |

Errors are in normalized-power units, not percent relative error or MW. ML and persistence are evaluated on exactly the same rows via User 1's `backtest.evaluate_january.evaluate`. Persistence uses the latest finite completed hourly power assumed available by issue, with maximum age 24h from hour end. Zero rows were excluded for missing actuals, unavailable baseline, or stale baseline. Forecast duplicate keys and missing fields: zero. Power predictions range from 0 to 0.9942843550614546.

The strict `python -m backtest.evaluate_january` CLI requires documentary confirmation of weather, timezone, and observation availability. That CLI was **not** invoked with false attestations. The preliminary wrapper reuses its numerical evaluator and training-selection checks, retaining metadata flags `training_publication_availability_verified=false`, `real_archival_forecasts_attested=false`, `weather_historical_publication_verified=false`, and `scada_source_timezone_confirmed=false`.

## Saved evidence and reproduction

Compact tracked directory: [`results/january_preliminary/3335d4b8ac8bba15/`](../results/january_preliminary/3335d4b8ac8bba15/), about 0.94 MB total.

- `forecasts.csv`: 2,844 January target cases with model version/hash and availability/provenance status.
- `metrics.csv`: turbine/horizon MAE, RMSE, evaluated rows, unique hours, and exclusions.
- `forecast_case_audit.csv.gz`: every scored case, original source timestamp, actual power, baseline value/source/assumed availability, and evaluation flags; readable with `pandas.read_csv` directly.
- `coverage.json`, `uncovered_hours.csv`: measured coverage and the 18 uncovered hours for each turbine.
- `issues.csv`: all 30 issue times, run IDs, local full-result paths, and failures if any.
- `baseline_availability.csv`: baseline selection for each issue/turbine, explicitly assumed.
- `weather_evidence.json`: all 30 request manifests, response hashes, retrieval times, grid/field validation and training-time guard results. Raw weather response bodies remain in the ignored cache.
- `evaluation_metadata.json`: source/code/model hashes, assumptions, environment, and output checksums.

Run from the repository root after installing `scripts/january_requirements.txt` and preparing hourly data as described in README:

```powershell
.\.venv\ml\python.exe -B scripts/run_january_evaluation.py --source-timezone Etc/GMT-5 --observation-delay-hours 0
```

Use `--offline` for exact cache reuse, `--last-day 1 --output-root data/processed/january_pilot_evaluation` for the pilot, `--wind-height-m` to change wind selection, and `--observation-delay-hours` to change the explicitly assumed latency. Do not tune timezone to minimize error. Changing an assumption requires a distinct evaluation version and must not be presented as a confirmation of that assumption.

Verification: 45 software tests passed, including the existing predictor, adapter, cycle, User 1 evaluator, and added January interval/coverage/retry/failure tests. Full-result checksums, paired case counts, horizons, output range, unchanged input hashes, and absence of future baseline access were checked. Raw data, processed tables, environment, and large runtime caches are not staged for Git.

Unresolved: organizer confirmation of timezone/interval labels, SCADA publication and revision timing, operational versus retrospective ECMWF archive origin and historical availability, wind-height comparability, and independence of model selection. No February forecast-accuracy evaluation was run.
