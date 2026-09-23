# January 2026 backtest: User 1 / Data & ML

No weather fetching, agent execution, or February loop is implemented here.
No January forecast-weather performance has been calculated. The only forecast
fixture, `fixtures/synthetic_forecasts.csv`, is **invented SOFTWARE TEST DATA**;
its values and test assertions are not model performance results.

## Separate models

```powershell
.\.venv\Scripts\python.exe -m backtest.train_january
.\.venv\Scripts\python.exe -m unittest backtest.test_january -v
```

Artifacts: `models/backtest_january/turbine_1_catboost.cbm`,
`models/backtest_january/turbine_2_catboost.cbm`, and
`models/backtest_january/metadata.json`. These use the approved 600 iterations,
depth 6, learning rate 0.05, seed 42. Features are exactly `wind_speed_ms` and
`temperature_c`; predictions are clipped by the existing prediction interface.
Final deployable models directly under `models/` are never overwritten. Existing
models, reports, and data are protected by before/after hashes. The new backtest
directory remains ignored by the existing Git rules; no ignore rules are changed.

Only eligible hours starting BEFORE 2026-01-01 00:00:00 in the ORIGINAL,
timezone-naive source clock and ending by that source-clock cutoff enter training.
Training has no timezone argument and performs no localization, conversion, or
timestamp shift. January rows are filtered out before examining feature or
power validity. Partial hours with finite means remain eligible; empty hours
are excluded; no interpolation or power lags. Metadata records the exact latest
training timestamp in the source clock for each turbine. It does not invent a
UTC equivalent. `source_timezone` is null, `source_timezone_status` is
`unknown/unconfirmed`, and `source_timezone_confirmed` is false. The UTC creation
time of an artifact describes the training run, not the timezone of its data.

**Timezone is unknown; UTC is NOT assumed.** Source timestamps denote starts
of the existing [t, t+1h) aggregation bins. The future evaluator requires an
explicit `--source-timezone` mapping and `--timezone-mapping-reference` recording
who confirmed it and where. There is no default zone. Only the evaluator maps
source-clock values to UTC for joining archival forecasts; the original files,
training timestamps, and model metadata remain unchanged. It preserves source
actual timestamps in the evaluation audit. Ambiguous/nonexistent local times
raise errors instead of being silently resolved.

January evaluation boundaries and simulated model availability are derived from
January 1 / February 1 in that configured SOURCE clock, then mapped to UTC.
Issues earlier than the mapped training cutoff are rejected: they need an earlier
training cutoff. Thus full January 1 target-day 24-48h coverage is not supported
by these static artifacts. Confirm the mapping with the organizers before real
evaluation; configuring a zone does not itself establish its correctness.

Retrospective training cannot prove publication/revision timing. Before real
evaluation, the script requires a manifest proving every training observation
was available by the cutoff. If late-arriving training observations are found,
evaluation fails; resolve them and retrain with an appropriate earlier cutoff
or availability-based selection. Never invent availability times merely to pass
this check. Observation values must be the versions available at the declared
times; a final corrected archive must not be assigned an earlier publication time.

## Producing prediction rows without retraining

Use these backtest artifacts, **not** the final models trained on January:

```python
from prediction import TurbinePredictor
p = TurbinePredictor("models/backtest_january")
result = p.predict(turbine_id, wind_speed_ms, temperature_c)
```

Kamila supplies real archival forecast weather and its provenance. Call the
single interface for each forecast case, preserve issue/run/target timestamps,
and attach the backtest version/hash from metadata. The existing general batch
interface rejects repeated turbine/target pairs, so do not feed mixed issues
to that interface: process one issue per batch, or use the single interface.
The evaluator below explicitly retains different issues for the same target.

## Exact forecast CSV schema

```text
issue_time_utc,weather_run_time_utc,weather_available_time_utc,target_time_utc,turbine_id,forecast_horizon_h,wind_speed_ms,temperature_c,predicted_normalized_power,model_version,model_sha256
```

- All four times: explicit ISO-8601 UTC ending in `Z` or `+00:00`.
- `issue_time_utc`: time the power prediction was issued, retained as case identity.
- `weather_run_time_utc`: archive weather model initialization time.
- `weather_available_time_utc`: documented time that weather run was published;
  must be between run time and issue time. Run initialization alone does not
  establish availability.
- `target_time_utc`: UTC instant corresponding to an hour START in January in
  the configured source clock; actual power is the [target,target+1h) mean.
  Do not shift timestamps silently. A source-January boundary can fall in a
  different UTC calendar date depending on the eventual confirmed mapping.
- `turbine_id`: turbine_1/turbine_2 (aliases 1/2 accepted).
- `forecast_horizon_h`: integer `(target_time_utc - issue_time_utc)` in hours,
  1..48. This is lead time from POWER issue time, not weather-run initialization.
- `wind_speed_ms`, `temperature_c`: finite archival FORECAST weather values.
  Never substitute measured weather. Wind must be non-negative.
- `predicted_normalized_power`: finite [0,1] output of the January model.
- `model_version`: `january-backtest-v1`.
- `model_sha256`: exact matching turbine artifact SHA256 from January metadata.

Case key is `(turbine_id, issue_time_utc, target_time_utc)`. Exact duplicate cases
fail, including different weather runs for one case: choose the run explicitly
upstream. Different issues for a target remain separate rows. No deduplication
or averaging across issues occurs. Hash/version fields are provenance supplied
by the producer; the evaluator cannot independently authenticate the weather
source or how predictions were originally computed.

## Baseline and availability manifest

Baseline is persistence: most recent valid hourly actual power whose hour has
ended and whose documented publication time is <= issue_time. It is reused for
all horizons in that issue. Maximum age measured from the source hour END is
24h. Older values are `baseline_stale`; absent values are `baseline_unavailable`.
There is no interpolation, fallback to a future value, or full-January mean.

Required availability CSV (one record per turbine/observed hour):

```text
turbine_id,target_time_utc,available_time_utc
```

It must cover all eligible training hours and any observation used by the online
baseline. Times are explicit UTC; publication cannot precede the hour end.
Duplicate observation keys fail. A missing manifest record means unavailable,
not zero latency. January observations can feed the baseline only after their
recorded availability; they never enter these models' training.

## Real evaluation command (do not run until real inputs exist)

```powershell
.\.venv\Scripts\python.exe -m backtest.evaluate_january --forecasts PATH_TO_REAL_ARCHIVAL_PREDICTIONS.csv --availability PATH_TO_VERIFIED_OBSERVATION_AVAILABILITY.csv --output-dir reports/january_forecast_evaluation_run_01 --source-timezone CONFIRMED_IANA_TIMEZONE --timezone-mapping-reference "ORGANIZER_CONFIRMATION_REFERENCE" --real-archival-forecasts
```

The placeholders must be replaced only when the mapping is established. No zone
is currently selected for real data. Flags are explicit attestations, not
automatic verification of real-world provenance. Verify timezone and publication
timing with the data owner first. Synthetic test fixtures explicitly select their
own invented timezone mapping; that is not a claim about the turbine CSVs.
The output directory must not already exist; prior reports cannot be overwritten.

Outputs: `forecast_case_audit.csv`, `metrics.csv`, `evaluation_metadata.json`.
MAE/RMSE are reported separately for each turbine and horizons 1-24 / 25-48h.
Both ML and persistence are scored on EXACTLY the same rows with valid actual
and an available, non-stale baseline. Every forecast case remains in the audit,
including excluded cases with flags, actual availability, baseline source hour,
and publication time. Summary reports forecast rows, unique target hours,
evaluated rows/unique hours, missing-actual rows/unique hours, and baseline
unavailable/stale counts. Missing-actual and baseline exclusion counts can overlap.
Empty groups have null metrics, never invented zero scores. Each forecast case
has equal weight; repeated target hours from different issues contribute more
than once by design. Counts are per turbine/band and are not additive unique
hours across bands. Partial actual hours with finite power are accepted.
