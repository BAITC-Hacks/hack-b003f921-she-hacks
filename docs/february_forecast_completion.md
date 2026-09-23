# User 2 February forecast completion

Branch: `user2-weather-pipeline`. All work was completed on this branch; no new merge or pull request was made. January accuracy evaluation was not rerun, and its saved output checksums are unchanged. Raw CSVs, production models, January models, the Word source, and the safety stash were preserved.

## Completed schedule and coverage

29 daily power issues from **2026-01-31 through 2026-02-28 at 12:00 UTC**, each with targets issue+1 through issue+48 for two turbines. All **29 succeeded**, with **zero failures**, missing prediction fields, or duplicate `(issue_time_utc, turbine_id, target_time_utc)` keys.

The source/test clock assumption remains fixed **UTC+05 (`Etc/GMT-5`)**. February is `[2026-01-31T19:00:00Z, 2026-02-28T19:00:00Z)`, comprising hourly starts through February 28 at 18:00 UTC. Each target represents the start of its following hourly production interval under the existing assumption.

| Turbine | Expected February hours | Covered hours | Missing hours | February forecast cases |
| --- | ---: | ---: | ---: | ---: |
| turbine_1 | 672 | 672 | 0 | 1,326 |
| turbine_2 | 672 | 672 | 0 | 1,326 |

The all-issue table contains **2,784 rows** (29 × 48 × 2). The February subset contains **2,652 rows**; 132 targets outside the selected month remain in the full table. The first 18 February hours have one issue per turbine; the remaining 654 have two. No averaging or deduplication across issues was performed. `missing_hours.csv` is correctly header-only.

## Existing results and model selection

Before this task, only the February 14 issue was complete within the requested schedule. Two immutable versions existed; the latest compatible one, `results/forecast_runs/20260214T120000Z/20260214T000000Z/64248dfb5e925d39/`, was selected. All file hashes, the identity hash, original weather revision, model hashes, unchanged prediction code, all input fields and times, finite [0,1] outputs, and saved alerts were checked. Its **96 power values and original artifacts remain unchanged**; ML inference was not repeated.

The aggregate adds four audit fields to that older schema (`weather_available_time_utc`, `weather_availability_status`, `model_version`, `model_sha256`) using the current adapter. Original metadata and the current assumed-time guard are both recorded in `weather_evidence.json`; the new assumptions are not attributed retrospectively to the old run.

January 31 had saved weather but no power forecast. It was first checked individually using that saved evidence: 96 rows and 6 alerts. The schedule then reused it and February 14, computing the remaining 27 issues. In total this task produced 28 previously missing forecasts, not another January evaluation.

| Issues | Model directory | Latest training interval completion under UTC+05 / zero extra delay |
| --- | --- | --- |
| January 31 12:00 UTC | `models/backtest_january/` (`january-backtest-v1`) | December 31 19:00 UTC |
| February 1–28 12:00 UTC | `models/` (`1.0.0`) | January 31 19:00 UTC |

The existing `validate_model_time` guard checks the end of the final training hour, not just its starting timestamp. Production models remain ineligible at January 31 12:00 UTC. Model artifacts were neither overwritten nor retrained. Model creation in September is a retrospective simulation, not evidence of an actual February deployment.

## Weather, automation and immutable reuse

Source: Open-Meteo **Single Runs API**, requested model `ecmwf_ifs`, daily initialization at 00:00 UTC. The existing loader requests the same five weather fields and exact coordinates, GMT, Celsius, m/s, nearest grid cell and disabled elevation downscaling. It validates raw units/times/values and selects the following 48 power horizons. Both turbines use a shared grid cell; their separate ML models produce distinct power estimates.

The wrapper `scripts/run_february_forecasts.py` reuses `agent.weather_pipeline.run`; it does not duplicate weather fetching, model invocation, or alert logic. `agent/forecast_reuse.py` validates compatible completed versions and performs the explicit older-schema enrichment without changing power values. Only absent compatible forecasts invoke the existing cycle. Weather bodies use the ignored request-hash cache; transient failures are limited to three attempts (2s/4s backoff). Corrupt artifacts fail explicitly rather than silently selecting a stale successful result. Failed issues are reported and later issues continue; an incomplete schedule exits nonzero.

Monthly output identity includes selected source run IDs, settings, forecast/alert hashes and report code hashes. The output directory is immutable. A completed schedule can be checked again without network or model calls; this exact behavior was verified with both calls forbidden. Earlier run and monthly versions are retained.

No previous assumptions were silently changed:

- Source clock UTC+05 and interval-start labels: **assumed**.
- SCADA availability after the end of the hourly interval plus zero extra delay: **assumed**, applied to the training guard. No February SCADA values are consumed by this forecast run.
- Weather availability at initialization +12h: **assumed**; actual historical publication/ingestion is not known.
- Wind at 100 m: technical choice; hub/sensor-height compatibility is not established.
- ECMWF archive origin: **unverified**, including operational versus retrospective hindcasts. HTTP 200 and correct timing do not resolve provenance.

## Alerts and demonstration

The full schedule has **350 warning windows**, 179 for turbine 1 and 171 for turbine 2. Each compares forecast `P(t)` against `P(t+3h)` within one turbine and one issue. A drop of at least **0.20 normalized power is 20 percentage points**, not a relative 20% reduction. The threshold is demonstration-only. Final three horizons have no +3h endpoint and are not extrapolated.

All warning windows retain `issue_time_utc` and `weather_run_time_utc`; they can overlap across periods/issues and are not counts of independently verified physical events. Alerts outside the February target boundary are retained because each issue keeps its full 48-hour horizon. The HTML table can filter by issue or search turbine/time. No alert accuracy claim is made.

The standalone PNG and HTML plot use only the real February 14 issue (96 points, two turbine panels), preserving its 48-hour timeline in UTC. They do not blend different issues into a single curve or plot fabricated measurements. The HTML is self-contained and opens offline; CSV/JSON downloads are adjacent relative links.

## Tracked deliverables and local-only data

Tracked directory: [`results/february_forecasts/ba114e109ecee099/`](../results/february_forecasts/ba114e109ecee099/), approximately 1.97 MB total.

- `forecasts.csv`: all 2,784 cases with original weather columns, explicit times, model and provenance fields.
- `february_forecasts.csv`: 2,652 cases within the chosen month.
- `alerts.csv`: 350 issue-preserving warning windows.
- `coverage.json`, `missing_hours.csv`, `issues.csv`: actual hour coverage and every issue outcome.
- `weather_evidence.json`, `metadata.json`: exact original result references, weather request/response hashes, units/grids/checks, artifact/eligibility evidence, assumptions, code/environment and output checksums.
- `forecast.png`, `report.html`: standalone plot and offline report with all warnings.

Ignored local full-run folders: `data/processed/february_runs/<issue>/<weather-run>/<version>/`. February 14 remains in its previously tracked folder. Downloaded weather bodies remain in `data/weather_cache/`; their hashes and request evidence are tracked in the compact report. Local raw CSVs, processed SCADA, `.venv`, and runtime caches are not added to Git.

## Commands and verification

Run from the repository root with the existing Python 3.11 environment and `prediction/requirements.txt` dependencies (CatBoost includes matplotlib). Open the saved demonstration without calculations:

```powershell
Start-Process .\results\february_forecasts\ba114e109ecee099\report.html
```

Resume missing forecasts or validate completed ones:

```powershell
.\.venv\ml\python.exe -B scripts/run_february_forecasts.py --source-timezone Etc/GMT-5 --observation-delay-hours 0 --wind-height-m 100
# Exact offline repeat in the workspace with its retained full results and cache:
.\.venv\ml\python.exe -B scripts/run_february_forecasts.py --source-timezone Etc/GMT-5 --observation-delay-hours 0 --wind-height-m 100 --offline
```

Seven focused tests passed: `python -B -m unittest scripts.test_february_pipeline`. These cover the schedule/model switch, complete coverage, missing first issue and its actual 18-hour gap, duplicate cases, corrupt results, no-inference/no-network reuse of the real February 14 example, and continuation after a failed issue. Independent checks confirmed all output hashes, 48-hour turbine/issue groups, horizon arithmetic, no missing fields/duplicates, model roles and [0,1] power range (observed range 0.004738701981187421–0.9910506976586742). The full offline repeat reused all 29 forecasts with network and inference explicitly forbidden. The plot was visually inspected.

## What remains unresolved

Forecast generation, coverage, warning export and demonstration are complete for the requested schedule. **February accuracy and warning effectiveness remain unmeasured:** local actual power stops January 31, and no February truth was invented. Organizer/provider confirmation of time conventions, observation availability, historical weather origin/publication and wind-height suitability is still needed. This is not a confirmed historical backtest. Saule's model description/measured-weather metrics and the preliminary January evaluation remain separate and unchanged.
