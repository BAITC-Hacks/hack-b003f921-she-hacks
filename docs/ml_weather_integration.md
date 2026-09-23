# Weather-to-model integration check

Completed 2026-09-23 on `user2-weather-pipeline`. This is real inference with the saved CatBoost models, not a February accuracy evaluation.

## Git integration and preservation

Pre-existing work was saved using `git stash push --include-untracked`, including the untracked Word document. Safety snapshot: `bc6017aeb6bec46cfe6a0a5d1fbf9fafd1df8eb0`. It remains in the stash list; it was applied, not popped or deleted.

After `git fetch origin`, User 1's `origin/data-model` at `3d85296` was merged with the normal merge strategy. Merge commit: `a317675`. There were no merge conflicts. Pre-existing weather work was restored. No push was performed. New integration code and documentation are working-tree changes following the merge.

`models/` and `prediction/` are unchanged from User 1's branch. Both required artifacts exist, load successfully, and match the checksums in `models/metadata.json`:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `models/turbine_1_catboost.cbm` | 672960 | `b3ad5c95580a49b2260b1ff6ab649242c717638b569451db5f2f6be5bcf54aee` |
| `models/turbine_2_catboost.cbm` | 672360 | `8fe049cee2dbb83c819c3ad1ab9e327e982b3408b6617f11599b4115d67eb141` |

The inference environment uses Python 3.11.16, CatBoost 1.2.8, NumPy 2.2.6 and pandas 2.2.3. Runtime packages match `prediction/requirements.txt`; User 1 trained under Python 3.11.9. Local dependencies are isolated under `.venv/`, not committed.

## Adapter and actual CLI

```powershell
.\.venv\ml\python.exe -B scripts/run_weather_integration.py --issue-time 2026-02-14T12:00:00Z --wind-height-m 100
```

The wrapper invokes `python -m prediction --model-dir models batch --input INPUT.csv --output OUTPUT.csv` using the same interpreter. The `--model-dir` global option precedes `batch`. It uses temporary intermediate files, validates the full result, then saves immutable evidence. Different existing outputs are rejected; use `--output-dir` for a new version. Direct use of User 1's CLI does not provide that overwrite protection.

Mappings:

- `temperature_2m_c` -> `temperature_c`.
- `wind_speed_{height}m_ms` -> `wind_speed_ms`, with `--wind-height-m` restricted to 10, 100 or 200.
- IDs `1`/`2` or already canonical IDs -> `turbine_1`/`turbine_2`.

All original weather columns remain in model input and output. `wind_height_m` and `weather_provenance_status=unverified` are added. The metadata embeds original requested/cell coordinates, terrain settings, availability assumption, request/source hashes, source provenance status, selected height, field mapping and complete model metadata. No wind-height extrapolation or weather-value conversion is performed. The 100 m selection is a technical assumption, not a known hub height or known height of the measured training wind.

The batch interface rejects duplicates on turbine plus target, even across different issues. Therefore the adapter selects one issue and one weather run before calling it. Future overlapping issues must be run independently and preserved using the contract's versioned keys; do not concatenate them into one batch or discard older versions.

## Saved real results

Directory: [`examples/integration_20260214_100m/`](../examples/integration_20260214_100m/).

- `weather_model_input.csv`: 96 adapted rows retaining all original weather fields.
- `predictions.csv`: the actual batch output, including `predicted_normalized_power`.
- `metadata.json`: hashes, package versions, assumptions, mappings and validation results.

Issue: `2026-02-14T12:00:00Z`; weather initialization: `2026-02-14T00:00:00Z`. Targets: `2026-02-14T13:00:00Z` through `2026-02-16T12:00:00Z`. Horizons are exactly target minus issue: 1..48, separately for each turbine.

| Turbine | Rows | Minimum prediction | Maximum prediction |
| --- | ---: | ---: | ---: |
| turbine_1 | 48 | 0.007703379534718668 | 0.8047818690382259 |
| turbine_2 | 48 | 0.0072241105774226155 | 0.7822535377446289 |

Validated: 96 rows; no missing/non-finite features or predictions; no duplicate keys; complete hourly horizons; exact preservation of all adapted input strings, including the three times and row order. Both models receive identical weather for the common cell, but their learned power responses differ. User 1's interface clips raw finite predictions to [0,1]; this range check is not an accuracy claim. Power is dimensionless normalized power, not MW/MWh.

Tests: `python -B -m unittest prediction.test_interface scripts.test_weather_integration` passed all 19 tests. Adapter checks cover alternate heights, incorrect horizon, alias duplicates, missing hours, non-finite weather and rejection of January 31 with final refits. `.gitattributes` preserves byte-level hashes of CSV/JSON evidence across checkouts.

## Training cutoff and unresolved scientific questions

Final model metadata states training through `2026-01-31 23:00:00`, exclusive cutoff `2026-02-01 00:00:00`, in an unspecified source timezone. These models cannot support a fair January backtest or the January 31 12:00 issue. That requires separate models fitted only on data actually available before each issue, considering timezone, aggregation completion and observation arrival delay. Do not truncate only the evaluation inputs while reusing the final fit.

The adapter conservatively refuses issues earlier than the naive exclusive cutoff plus one UTC day when the source timezone is unknown. This blocks January 31 and is only a technical guard; it cannot prove historical training availability. The February 14 integration is well beyond the data cutoff, but the artifacts were physically created in September. No assertion of actual February deployment is made.

Weather origin remains `unverified` (`unresolved_operational_vs_retrospective` in source metadata), with unknown historical publication time and a provisional 12-hour availability lag. [Provenance review](weather_archive_provenance.md) remains applicable. The measured-weather validation scores are not archived-weather forecast scores, and no actual February power was loaded or evaluated. Confirm SCADA timezone, interval labels, hub/sensor heights, permitted access to February observations and archive acceptance before a scientific forecast backtest.
