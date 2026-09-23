# Weather forecast data contract

Version: 1.0. Owner: Kamila / User 2. Consumer: User 1. Status: integration example; historical provenance and SCADA time conventions remain unresolved.

## Files and row meaning

Example: [`data/weather_examples/v1/weather_forecasts.csv`](../data/weather_examples/v1/weather_forecasts.csv), with [`weather_forecasts.metadata.json`](../data/weather_examples/v1/weather_forecasts.metadata.json) in the same directory. Both are required for interpretation.

One row represents one simulated project issue, one selected weather initialization, one future hourly valid time and one turbine. The sample has 192 rows: two issues x 48 hours x two turbines. Only already saved responses are used. Identical values across turbines are valid and do not make rows duplicates.

CSV encoding is UTF-8 without BOM, comma delimiter, decimal point, one header, LF line endings. Timestamps use `YYYY-MM-DDTHH:MM:SSZ` in UTC. No naive timestamps or implicit local-time conversions are allowed. Rows sort by issue, weather run, target, turbine.

| Column | Type | Meaning / constraints |
| --- | --- | --- |
| `issue_time_utc` | UTC timestamp | Simulated time our system computes/issues the power forecast; here daily 12:00 UTC. NOT weather publication, model initialization, or September download time. |
| `weather_run_time_utc` | UTC timestamp | Weather model initialization selected by `run`; here same day 00:00 UTC. Does not assert when it was computed or published. |
| `target_time_utc` | UTC timestamp | Valid time of instantaneous weather features, strictly after issue; on the UTC hour. Mapping to a SCADA hour is pending interval-label confirmation. |
| `turbine_id` | string enum | `turbine_1` or `turbine_2`; stable site identifiers, even if weather cell is shared. |
| `forecast_horizon_h` | integer | Exactly `(target_time_utc - issue_time_utc) / 3600 seconds`, range 1..48 inclusive. This is NOT target minus weather initialization. |
| `temperature_2m_c` | finite number | Forecast air temperature at 2 m above model ground, degrees Celsius; source `temperature_2m`. |
| `wind_speed_10m_ms` | finite number >= 0 | Forecast speed at 10 m above model ground, m/s; source `wind_speed_10m`. |
| `wind_speed_100m_ms` | finite number >= 0 | Forecast speed at 100 m above model ground, m/s; source `wind_speed_100m`. |
| `wind_speed_200m_ms` | finite number >= 0 | Forecast speed at 200 m above model ground, m/s; source `wind_speed_200m`. |
| `wind_direction_100m_deg` | finite number, 0..360 | Forecast meteorological wind direction at 100 m above model ground, degrees; source `wind_direction_100m`. North 0/360 are equivalent; preserve source value. |

These heights are not confirmed turbine hub heights. No vertical extrapolation, value conversion, filling or additional interpolation is performed in the example. Weather values are instantaneous rather than hourly SCADA averages.

## Keys, validation and metadata

Within a dataset version, the primary key is `(issue_time_utc, weather_run_time_utc, target_time_utc, turbine_id)`. Across datasets, prepend `dataset_id`; a model/source/terrain-policy change requires a new dataset version. Never deduplicate on `(target_time_utc, turbine_id)` alone.

Required validation: unique primary keys; all 48 integer horizons exactly once per issue/run/turbine; target minus issue equals the horizon exactly; finite non-null features; stated units and domains; source checksum and HTTP status; correct location mapping. Missing source hours/features are errors, not zeros or forward-filled values. Emit a separate failure record for an unavailable issue and preserve existing successful versions. Validate model lead separately: this sample uses target minus weather run = 13..60 hours. A 12-hour eligibility lag is only the recorded assumption, not verified publication evidence.

The companion metadata contains:

- Schema/dataset identifiers, CSV columns, units, primary key, row count and SHA-256.
- Per issue/run: explicit model `ecmwf_ifs`, source/endpoint, full request parameters/URL, raw response and request-metadata paths and hashes, retrieval time, and provenance status.
- Per turbine within each issue/run: requested WGS84 latitude/longitude, returned cell latitude/longitude and model grid terrain elevation in metres. Join metadata by `(issue_time_utc, weather_run_time_utc, turbine_id)`.
- Terrain settings: `cell_selection=nearest`, per-location `elevation=nan`, elevation downscaling disabled. Grid elevation is not wind height.
- Availability policy: assumed lag of 12 hours after initialization, assumed cutoff, rationale and `verified=false`. Actual weather publication and historical API availability are separate nullable fields, currently null.
- Unknown test-period timezone and SCADA label convention explicitly set to null; height reference and transformations; source attribution.

Current mapping: turbine 1 `(43.645150, 78.535604)`, turbine 2 `(43.643198, 78.538828)`; both return cell `(43.620384, 78.47891)`, terrain elevation 638 m. The sample's `provenance_status` is `unresolved_operational_vs_retrospective`; see [evidence and excerpts](weather_archive_provenance.md).

## Proposed daily schedule and February coverage

This is a schedule specification, not a claim that unqueried releases exist. On each UTC date D from **2026-01-31 through 2026-02-28 inclusive**:

1. At D 12:00 UTC, use the D 00:00 weather initialization, subject to the provisional 12-hour availability policy.
2. Preserve a 48-hour version with targets D 13:00 through D+2 12:00 inclusive (horizons 1..48).
3. Add the new issue to history. Retain all older issues, raw responses, metadata and model prediction versions. If a weather run is unavailable, report the gap; do not silently choose a later run, a reanalysis or fabricate values.

Adjacent issues are 24 hours apart and overlap at 24 targets. For example, target `2026-02-02T00:00:00Z` belongs to the January 31 issue at horizon 36 and the February 1 issue at horizon 12; their weather initializations also differ. Both rows per turbine must remain in history.

Assuming all planned releases are available, the union of targets is the continuous UTC hourly sequence **January 31 13:00 through March 2 12:00**, 720 distinct timestamps per turbine. There are 29 x 48 x 2 = 2,784 versioned rows, not 2,784 distinct target hours. This covers all 672 hourly timestamps in February if February is defined in UTC; it also covers the illustrative UTC+05:00 February window below. Only January 31 and February 14 have actually been retrieved; no intermediate weather is synthesized in the example.

The final test window is **[2026-02-01 00:00, 2026-03-01 00:00) in the organizer-confirmed timezone**, converted to UTC using that timezone. Do not infer it from turbine location or the developer machine. Illustrations, not decisions:

| Assumed test timezone | February interval in UTC (start inclusive, end exclusive) |
| --- | --- |
| UTC | 2026-02-01 00:00 to 2026-03-01 00:00 |
| Fixed UTC+05:00 | 2026-01-31 19:00 to 2026-02-28 19:00 |

The half-open window specifies physical interval boundaries. Hour-start labels would range from the start through one hour before the end; hour-end labels would range from one hour after the start through the end. The 10-minute label convention determines assignment before hourly aggregation. Verify coverage after these choices; if the confirmed zone/labels place a required target outside the proposed sequence, add an earlier/later issue rather than silently dropping it. For example, a UTC+14 hour-start window would need earlier coverage than January 31 13:00 UTC. No February boundary filtering is applied to the sample.

For evaluation by horizon, retain every eligible issue/target pair. If a single operational series is needed, derive a view with an explicit rule (e.g. latest issue strictly before target, among eligible rows); retain the full history and record that rule. A fixed day-ahead rule is a different view and must be agreed with organizers. Never select the best forecast retrospectively using observed power. Group temporal train/test splits by target time so overlapping versions of one target do not leak across splits.

## Version retention and reproduction

```sh
python -B scripts/build_weather_example.py
```

The builder uses only saved JSON, rechecks source hashes/fields, and writes the CSV plus metadata. Identical reruns leave existing files untouched. Different content at an existing output path is rejected; use `--output-dir data/weather_examples/v2 --dataset-id weather_handoff_example_v2` if creating a new revision. Never overwrite a prior published artifact or change its issue time. The version directory and metadata together identify a delivery; original CSV identities must remain unique across distinct deliveries.

For future bulk collection, use immutable paths containing dataset/model, issue, weather initialization and revision/content hash. The existing `check_weather_archive.py` is a small probe that overwrites its chosen sample directory in online mode; it is not a history-preserving bulk loader. Preserve current raw samples and choose a fresh capture directory for any further probes.

## Power observations and acceptance

No power observations are included here. Until organizers confirm February observations and their release delay, User 1 must not assume measured February power is available for lag features, online updates or retraining. If allowed later, use only records actually received by `issue_time_utc`, not merely records whose measurement timestamp is earlier. Holdout labels may be used after forecast creation for scoring under the agreed protocol.

The CSV is ready for integration checks. Final archive acceptance, February boundaries, SCADA aggregation and any power-feedback policy remain open; see [organizer questions](organizer_questions.md).
