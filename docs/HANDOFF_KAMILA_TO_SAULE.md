# Handoff: Kamila (User 2) to Saule (User 1)

Checkpoint date: 2026-09-23. Branch: **`user2-weather-pipeline`**.
Completed implementation/results were pushed in `e7b2f8d`; the commit adding this document is the handoff checkpoint. User 1's January artifacts/evaluator from `origin/data-model` (`7e72522`) were previously integrated in `76680ac`. No new merge, forecast calculation, download, training, or long test run was performed for this checkpoint.

## Completed and available in Git

- Case extraction: [case.md](case.md), with the original Word document unchanged.
- Exact-run Open-Meteo Single Runs / ECMWF IFS weather loader, response checks, cache reuse, model adapter, actual CatBoost batch inference, immutable forecast versions, and three-hour power-drop alerts. Entry point: `scripts/run_weather_integration.py`. Transient weather errors have at most three attempts with 2s/4s backoff; invalid data cannot silently reuse an older run.
- Adapter preserves issue/run/target times and original weather fields, adds selected-height wind, temperature, assumed weather availability, model version/hash, and provenance status. Wind height is configurable; demonstrated height is 100 m, not a confirmed hub or training-sensor height.
- Separate January models and evaluator in `models/backtest_january/` and `backtest/`. Production models in `models/` are preserved. Model guards account for completion of the last training hour and the configured availability assumption.
- Existing hourly preparation was run on both local raw CSVs. The generated hourly files match the January training-source hashes exactly. Raw CSV and production-model hashes were checked unchanged.
- Preliminary January evaluation: 30 daily issues on January 1–30 at 12:00 UTC, weather initializations at 00:00 UTC, 48 hours per turbine. All 30 succeeded. Full forecasts contain 2,880 rows; 2,844 January target cases were scored against persistence on exactly the same rows.
- Coverage is 726 of 744 source-January hours per turbine, with 1,422 evaluated cases per turbine. The first 18 January hours are outside the issue schedule. Missing actuals/baselines and duplicate forecast cases: zero. Overlapping issues remain separate cases.
- A complete offline repeat reused all 30 validated runs and the evaluation. The previous work session passed 45 software tests. These checks were not rerun during this urgent checkpoint.

### Saved preliminary January metrics

Errors are dimensionless normalized-power errors, not relative percentages or MW.

| Turbine | Horizon | Paired cases | ML MAE / RMSE | Persistence MAE / RMSE |
| --- | --- | ---: | --- | --- |
| turbine_1 | 1–24 h | 720 | 0.151585 / 0.231329 | 0.302303 / 0.431223 |
| turbine_1 | 25–48 h | 702 | 0.172892 / 0.256884 | 0.379551 / 0.490082 |
| turbine_2 | 1–24 h | 720 | 0.155823 / 0.238020 | 0.300620 / 0.432194 |
| turbine_2 | 25–48 h | 702 | 0.175617 / 0.260669 | 0.379563 / 0.491242 |

**Label these results "preliminary January evaluation with time and archive assumptions", never a confirmed historical backtest.** Assumptions: source clock is fixed UTC+05 (`Etc/GMT-5`), timestamps mark interval starts, SCADA is available immediately after hour end (zero extra delay, explicitly selected by Kamila), and weather is available at initialization +12h. Timezone/availability are `assumed`; weather origin remains **`unverified`**. The same source-clock mapping applies to actuals and training boundaries. No timezone was selected by minimizing error. The strict evaluator CLI's documentary attestations were not asserted; the preliminary wrapper reuses its numerical evaluation functions.

## Result paths in Git

| Path | Contents |
| --- | --- |
| `results/january_preliminary/3335d4b8ac8bba15/forecasts.csv` | 2,844 real-model forecast cases with January targets and provenance fields |
| Same directory: `metrics.csv`, `coverage.json`, `uncovered_hours.csv` | Scores, row/hour coverage, and the missing schedule hours |
| Same directory: `forecast_case_audit.csv.gz` | All cases with actual power, baseline selection and evaluation flags; readable by `pandas.read_csv` |
| Same directory: `issues.csv`, `baseline_availability.csv` | All 30 issues, local full-result paths/run IDs, and assumed baseline availability |
| Same directory: `weather_evidence.json`, `evaluation_metadata.json` | Request manifests, response hashes, grids, validation, model/source/code hashes and assumptions |
| `results/forecast_runs/20260214T120000Z/20260214T000000Z/64248dfb5e925d39/` | Completed February technical cycle: weather, model input, 96 predictions, 7 alerts, metadata |
| Same February parent: `c08050f69d1162f8/` | Retained earlier forecast version |
| `examples/integration_20260214_100m/` | Original real-model integration example |
| `data/weather_source_check/` | Small original API responses/request metadata for January 31 and February 14 |
| `data/weather_examples/v1/` | Original 192-row weather handoff example and metadata |
| `models/backtest_january/` | Two January `.cbm` artifacts and metadata; use for the preliminary January schedule |
| `models/` | Two production `.cbm` artifacts and metadata, fitted through January 31 |

See [January report](january_preliminary_evaluation.md), [data contract](data_contract.md), [archive provenance](weather_archive_provenance.md), and [README](../README.md). Historical reports describe their original checkpoint; this handoff and the January report describe the current scope.

## February status and remaining work

February 14 **integration** succeeded: 96 rows, targets February 14 13:00 through February 16 12:00 UTC, and 7 demonstration alert windows (4 for turbine 1, 3 for turbine 2). This does not measure forecast accuracy. The 0.20 drop threshold means 20 percentage points of normalized power over three hours and is not calibrated on history.

**A full February schedule has not been executed. February forecast accuracy has not been evaluated.** The local raw inputs end January 31 at 23:50 in the source clock; there are no February power labels in those files. Do not assume that files uploaded to a separate ChatGPT conversation exist here. No dashboard has been built.

Before claiming confirmed evaluation or extending to February:

1. Obtain organizer confirmation of SCADA timezone, test-period timezone, start/end meaning of 10-minute timestamps, and access/publication delays for February measurements. [Organizer questions](organizer_questions.md) are drafted, not sent.
2. Resolve operational versus retrospective origin of the ECMWF hindcasts and historical publication/ingestion times. HTTP 200, a run identifier, and a 12-hour margin do not prove these facts.
3. Confirm whether 100 m forecast wind is suitable for the hub/training-sensor height and how hourly forecast weather should represent hourly mean power. Both turbine locations currently use one weather grid cell.
4. Preserve the January preliminary results; create a new version if assumptions or data change. Historical SCADA revisions/publication and independence of model selection from January remain unverified.
5. Implement a February schedule wrapper around the existing single-issue cycle after resolving scope/time boundaries. `scripts/run_january_evaluation.py` is deliberately restricted to January 1–30; it is not a February runner. If a January 31 12:00 UTC issue is needed to cover early February, use a model eligible at that issue, not the production refit trained through January 31. With the provisional UTC+05 mapping, the production training boundary is January 31 19:00 UTC; January 31 12:00 UTC is too early.
6. Obtain actual February measurements before computing February accuracy. Decide whether they may feed an online persistence baseline and at what latency. Keep measured-weather User 1 metrics, integration checks, and archived-weather accuracy separate.

## Commands for Saule to run later

Run from the repository root. This workspace uses Python 3.11 at `.venv/ml/python.exe`; use the equivalent Python 3.11 environment path on another machine. The system Python here is 3.14 and is not the ML runtime. These commands are instructions only; none were executed during this checkpoint.

```powershell
# Install dependencies into the chosen Python 3.11 environment, if needed.
.\.venv\ml\python.exe -m pip install -r scripts/january_requirements.txt

# Only if both hourly inputs are absent; requires the two local raw CSVs.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_hourly.ps1

# One January pilot with the explicit provisional assumptions.
.\.venv\ml\python.exe -B scripts/run_january_evaluation.py --source-timezone Etc/GMT-5 --observation-delay-hours 0 --last-day 1 --output-root data/processed/january_pilot_evaluation

# Resume/repeat January: reuses exact caches and completed immutable runs;
# missing runs are downloaded with bounded retries; failed issues are reported.
.\.venv\ml\python.exe -B scripts/run_january_evaluation.py --source-timezone Etc/GMT-5 --observation-delay-hours 0

# Fully offline January repeat requires the local cache listed below.
.\.venv\ml\python.exe -B scripts/run_january_evaluation.py --source-timezone Etc/GMT-5 --observation-delay-hours 0 --offline

# February 14 technical example; tracked saved API evidence can seed its cache.
.\.venv\ml\python.exe -B scripts/run_weather_integration.py --issue-time 2026-02-14T12:00:00Z --wind-height-m 100 --model-dir models --drop-threshold 0.20 --offline
```

The January wrapper defaults to 100 m wind and `models/backtest_january/`. A failed issue produces an incomplete report and a nonzero exit code; rerunning resumes using valid cached successes. Corrupt evidence fails explicitly and is not silently repaired. Changed code/settings/environment can create a new version even for the same issue, retaining existing versions. The February command above may create a new version under the current adapter code; it does not overwrite the saved earlier demonstration.

## Important local-only material and required inputs

**A Git clone/pull does not restore these files.** Arrange a separate local transfer if Saule needs offline reproduction. Do not commit raw datasets, environments or runtime caches. Existing tracked compact reports can be read without these inputs.

| Local path | Role and transfer/rebuild requirement |
| --- | --- |
| `data/raw/turbine 1.csv`, `data/raw/turbine 2.csv` | Original SCADA, unchanged and ignored. Required to rebuild hourly data; end at January 31, not February 28. Raw hashes are in the January report. |
| `data/processed/turbine_1_hourly.csv`, `turbine_2_hourly.csv` | Exact training/evaluation inputs, ignored. Needed to rerun January evaluation; can be rebuilt with the existing preparation script. Wrapper verifies hashes against model metadata. |
| `data/processed/data_quality_report.json` | Complete raw/hourly preparation diagnostics; local only and reproducible from the raw inputs. |
| `data/weather_cache/<request_hash>/response.json` and `request.json` | 31 cache entries at checkpoint: 30 January issues and the February 14 example. Original downloaded January response bodies are only here; their manifests/hashes are in tracked compact evidence. Needed for offline January repetition. Online retrieval might return a changed response later, so preserve these originals for exact audit. |
| `data/processed/january_runs/` | Full 48-hour weather/model inputs/predictions/alerts and metadata; 31 successful version folders at checkpoint, including the retained early pilot version. The 36 targets outside local January remain here. Full runs are not in the compact scored CSV. |
| `data/processed/january_runs/failures/20260923T114751_175ecdd6.json` | Initial sandbox network-permission failure; later authorized API request succeeded. This is not an upstream archive outage or an unresolved failed final issue. |
| `data/processed/january_pilot_evaluation/3cc479a4f65eeb31/` | Completed one-issue preliminary pilot evaluation; retained locally. Full January scored results are already in Git. |
| `data/processed/pre_january_safety.json` | Local before/after hashes for raw CSVs, production artifacts and the Word document. |
| `.venv/` | Ignored local environment; reconstruct from requirements rather than committing it. `.matplotlib` under processed data is a disposable cache. |
| `Кейс.docx` | Untracked original case document, unchanged; extracted content is tracked in `docs/case.md`. Also present in the safety stash. |

No incomplete calculation needs to be represented as a successful result. Completed full runs, the pilot, cache, and safety files are left in place.

## Stash and local Git safety references

Retained stash: **`bc6017aeb6bec46cfe6a0a5d1fbf9fafd1df8eb0`**, currently `stash@{0}`, message `Safety snapshot before integrating origin/data-model`. Stashes are local Git references and are **not** transferred by pushing this branch. Local safety branch `safety/pre-january-integration-20260923` also remains; it was not pushed as part of this handoff.

The stash was inspected without applying or dropping it. Its tracked change is the two-line provenance follow-up in `docs/weather_source_check.md`, already present in the current branch. Its untracked snapshot contains the original weather example CSV/metadata, `docs/data_contract.md`, `docs/organizer_questions.md`, `docs/weather_archive_provenance.md`, `scripts/build_weather_example.py`, and `Кейс.docx`. All code/document/weather-example work is already tracked in the current branch; the contract and builder now have intentional later extensions. No unique unfinished code was found only in the stash. The Word original remains local/untracked. Do not blindly apply this old snapshot over the newer implementation.

At checkpoint start, tracked files were clean and `user2-weather-pipeline` matched its remote; the only untracked root file was `Кейс.docx`. This checkpoint adds the handoff document and its README link, preserving all existing calculation results and local-only material.
