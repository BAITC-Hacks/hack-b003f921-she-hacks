# Archived weather forecast source check

Checked on 2026-09-23 on branch `user2-weather-pipeline`.

## Result

Both requested ECMWF runs returned HTTP 200 without an API key or payment. Both turbines have all 48 requested future hourly timestamps and all five requested variables, with no missing values. This verifies archive retrieval and data completeness today; historical publication timestamps remain unverified.

The source is the [Open-Meteo Single Runs API](https://open-meteo.com/en/docs/single-runs-api), explicitly using `models=ecmwf_ifs` and `run=YYYY-MM-DDT00:00`. The documentation describes ECMWF IFS HRES at approximately 9 km, with individual runs from 2024-03-14. The request never uses `best_match`, a stitched historical series, observations, ERA5, or another reanalysis. No alternative source was needed: both required releases are accessible in the free tier. The [pricing page](https://open-meteo.com/en/pricing) includes Single Runs in free non-commercial access and permits evaluation/prototyping; no commercial entitlement is implied by this check.

## Calculation time, initialization and publication

All times below are UTC. We deliberately choose a calculation at 12:00 and the same day's 00:00 model initialization. The 12:00 run is not eligible at calculation time.

| Calculation time | Selected initialization | First future timestamp | Last future timestamp | Coverage per turbine |
| --- | --- | --- | --- | --- |
| 2026-01-31 12:00 | 2026-01-31 00:00 | 2026-01-31 13:00 | 2026-02-02 12:00 | 48/48 |
| 2026-02-14 12:00 | 2026-02-14 00:00 | 2026-02-14 13:00 | 2026-02-16 12:00 | 48/48 |

“Next 48 hours” means the 48 hourly valid times at calculation +1 through +48 hours, inclusive. These correspond to model leads +13 through +60 hours. This convention excludes the calculation instant. These are instantaneous weather values, not 48 hourly averages of turbine measurements. The first check starts before February because it reproduces a January 31 decision; it is not a complete February evaluation schedule.

**Explicit availability assumption:** accept the selected run at initialization +12 hours. This is an eligibility cutoff, not a measured publication time. Single Runs documentation gives a typical global-model computation/distribution delay of 4–6 hours. The [model updates documentation](https://open-meteo.com/en/docs/model-updates) recommends an additional 10 minutes for server propagation. Our 12-hour cutoff leaves 5 hours 50 minutes beyond 6 hours plus 10 minutes. This conservative allowance is a project assumption, not an outage guarantee.

The [provider's Single Runs announcement](https://openmeteo.substack.com/p/single-runs-api) says archive availability follows publication of the final forecast step. Neither saved response contains historical publication or ingestion timestamps. Current `last_run_availability_time` metadata cannot prove availability for January/February. `generationtime_ms` is response generation duration; the saved HTTP `Date` and retrieval timestamps describe September retrieval, not historical forecast publication. Consequently `publication_utc` is null and `availability_verified` is false in the validation artifact. The run could plausibly have been available by the chosen calculation, under the stated assumption; this is not independently proven.

**Provenance caveat:** the Single Runs documentation calls its early coverage “IFS Cycle 49R1 hindcasts”. The provider's announcement also describes preservation of individual forecasts. [ECMWF's operational cycle history](https://www.ecmwf.int/en/forecasts/documentation-and-support/changes-ecmwf-model) places 49r1 in operation from 2024-11-12 until the May 2026 upgrade, encompassing both selected dates. That supports the model-cycle choice, but the JSON does not independently certify original operational versus retrospectively generated provenance. Strict audit acceptance still requires provider confirmation for these releases. A forecast hindcast must not silently be treated as proof of a forecast published at that historical time. No reanalysis was substituted.

## Locations and spatial treatment

| Location | Requested latitude | Requested longitude | Returned cell latitude | Returned cell longitude | Grid elevation |
| --- | --- | --- | --- | --- | --- |
| Turbine 1 | 43.645150 | 78.535604 | 43.620384 | 78.47891 | 638 m |
| Turbine 2 | 43.643198 | 78.538828 | 43.620384 | 78.47891 | 638 m |

Both runs return the same cell for both turbines, and all requested hourly arrays are identical between turbines. This is one shared weather signal, not two independent local forecasts.

Requests explicitly set `cell_selection=nearest` and `elevation=nan,nan`. According to the [forecast parameter documentation](https://open-meteo.com/en/docs), this selects the nearest cell and disables elevation downscaling. The returned coordinates identify the weather cell, not a changed turbine location. The 638 m value is grid terrain elevation, not wind height or turbine hub height. These choices make the comparison reproducible; default terrain-aware selection/downscaling could yield different results.

## Verified fields and values

Only these five variables were tested; the API's larger variable list is not a guarantee of availability for an individual historical run. Heights are above model ground, not above sea level. [ECMWF API documentation](https://open-meteo.com/en/docs/ecmwf-api) lists wind at 10, 100 and 200 m and temperature at 2 m. These are forecasts, not on-site measurements.

Ranges below use only the selected 48 future timestamps and apply to both turbines.

| API field | Height | Returned unit | January 31 run: min to max | February 14 run: min to max | Missing per 48-hour window |
| --- | --- | --- | --- | --- | --- |
| `temperature_2m` | 2 m | °C | -2.5 to 8.7 | -3.2 to 10.3 | 0 |
| `wind_speed_10m` | 10 m | m/s | 0.07 to 6.56 | 0.32 to 7.10 | 0 |
| `wind_speed_100m` | 100 m | m/s | 0.38 to 9.28 | 0.39 to 9.81 | 0 |
| `wind_speed_200m` | 200 m | m/s | 0.46 to 11.00 | 0.16 to 11.57 | 0 |
| `wind_direction_100m` | 100 m | ° | 23 to 282 | 49 to 310 | 0 |

Returned `hourly.time` uses ISO 8601 strings without a timezone suffix, together with `timezone=GMT` and `utc_offset_seconds=0`; the checker interprets them as UTC. Both raw responses contain 61 consecutive hourly timestamps, initialization +0 through +60. There are no duplicates, out-of-order timestamps, absent hours, nulls, non-numeric or non-finite values. Wind speeds are non-negative and directions are within 0–360 degrees. All five arrays have the expected lengths and units. These are consistency checks, not forecast-accuracy validation.

The API provides hourly output; the [model updates documentation](https://open-meteo.com/en/docs/model-updates) notes that hourly output can be interpolated from coarser model steps. Response cadence alone cannot establish native sampling or interpolation provenance. We perform no additional interpolation, gap filling, wind-height extrapolation or unit conversion.

## Reproduction and saved evidence

Python 3.10+ with only the standard library is required. From the repository root:

```sh
python scripts/check_weather_archive.py
python scripts/check_weather_archive.py --offline
```

The first command performs exactly two successful-case GET requests, one per date with both coordinates, and overwrites the sample files. It requests only 61 hours and five variables. The second revalidates saved bytes and SHA-256 hashes without network access, regenerating `validation.json`. Use `--output-dir PATH` for a fresh capture without replacing this evidence. HTTP/API failures or failed validation return a nonzero exit status; there is no automatic source/model substitution.

Saved under `data/weather_source_check/`:

- `ecmwf_ifs_2026-01-31_00.json` and `ecmwf_ifs_2026-02-14_00.json`: unmodified response bodies, two locations each. The selected 48 timestamps are positions 13 through 60 (zero-based), selected by exact datetime in the script rather than assumed indexing.
- Matching `*.request.json`: exact request URL and parameters, retrieval time, HTTP status/date, content type, raw-body SHA-256 and unknown historical publication time.
- `validation.json`: coverage, grid comparison, missing counts and per-field ranges for each turbine and run.

Data attribution: ECMWF forecasts delivered by Open-Meteo, [CC BY 4.0](https://open-meteo.com/en/licence). Raw bodies are unchanged; validation statistics are our derived summaries.

During discovery, `start_hour` returned HTTP 400 with `Parameter 'start_hour' must not be set`, despite the generic parameter-compatibility statement. The working request uses `forecast_hours=61` and selects the window locally. A single `elevation=nan` for two coordinates also returned HTTP 400 (`Parameter 'elevation' must have the same number of elements as coordinates`); `nan,nan` works. Initial sandbox connection failures were environmental restrictions, not proof that the archive was unavailable; authorized requests outside the sandbox succeeded.

## Remaining questions

- Confirm original operational provenance and actual historical publication/ingestion times with the provider before claiming a fully audited no-look-ahead backtest. No contact was made as part of this check.
- Obtain turbine hub heights and the height/averaging convention of the supplied wind measurements. Do not assume 100 m is the actual hub height.
- Agree on the SCADA timezone and interval-label convention before joining weather and production; this check uses UTC throughout.
- Confirm whether API interpolation and a common 9 km cell are adequate for the case. Distinct turbine power outputs cannot be attributed to different weather inputs here.
- These two successful runs do not establish availability for every February release or the full training period. Documented ECMWF Single Runs coverage does not reach March 2023. No full archive was downloaded.

No User 1 model files, existing case documentation, or Word source were modified. No interface was created.
