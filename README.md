# Wind power forecasting — She Hacks

User 1 provides turbine-specific CatBoost models and the prediction interface. User 2 provides archived-weather checks, the data contract and the offline integration adapter.

## Setup and real-model integration

Use Python 3.11 with `prediction/requirements.txt`. This workspace uses `.venv/ml/python.exe`; the system Python is 3.14. Recreate the isolated environment with Conda, or use another Python 3.11 virtual environment:

```powershell
conda create --prefix .venv/ml --override-channels --channel conda-forge python=3.11 pip --yes
.\.venv\ml\python.exe -m pip install -r prediction/requirements.txt
.\.venv\ml\python.exe -B scripts/run_weather_integration.py --issue-time 2026-02-14T12:00:00Z --wind-height-m 100
```

Run from the repository root. The adapter selects one issue from saved weather, preserves original fields and UTC times, adds `temperature_c` and `wind_speed_ms`, then invokes the real batch CLI. No download or training occurs. Wind height accepts 10, 100 or 200 m; 100 m here is a technical assumption, not an established hub/sensor height.

Artifacts: [`examples/integration_20260214_100m/`](examples/integration_20260214_100m/) contains `weather_model_input.csv`, `predictions.csv` and `metadata.json`. Different prior results are never overwritten; use a fresh `--output-dir` for another height/model/environment. Identical reruns preserve files.

The actual User 1 batch syntax is:

```powershell
.\.venv\ml\python.exe -m prediction --model-dir models batch --input examples/integration_20260214_100m/weather_model_input.csv --output examples/integration_20260214_100m/batch_reproduction.csv
```

Choose a new output path for direct batch reproduction: that CLI can overwrite its output. It rejects duplicate turbine/target pairs, so overlapping issues must be processed separately and preserved as distinct forecast versions.

## User 1 metrics with measured weather

Earlier comparison fits were trained through July 2025 and validated August 2025–January 2026 using **measured weather at the target hour**. These are power-estimation metrics, not 24–48-hour forecast-weather scores. Comparison outputs were not clipped; the validation set was used for model selection.

| Turbine | CatBoost MAE | RMSE | R² |
| --- | ---: | ---: | ---: |
| turbine_1 | 0.020992 | 0.041434 | 0.986010 |
| turbine_2 | 0.020304 | 0.053243 | 0.976771 |

Source: [model comparison](reports/model_comparison.md). Deployable models were subsequently refitted through January 31; these metrics do not independently evaluate the final refits.

## Integration success

The February 14 example connects ECMWF weather, the adapter and both actual `.cbm` models: **96 rows, 48 per turbine**, targets February 14 13:00 through February 16 12:00 UTC. Checks cover horizons, missing values, duplicate keys, unchanged input fields/time strings and finite `predicted_normalized_power` in [0,1]. The interface clips finite raw predictions to this range; range compliance is not accuracy. The output is normalized power, not MW or energy.

See [integration evidence](docs/ml_weather_integration.md) and output metadata for actual results, hashes and package versions.

## Forecast quality with archived weather — not measured

No February forecast accuracy score has been calculated. Weather provenance remains **`unverified`**; the specific unresolved operational-versus-retrospective status is preserved in source metadata. Hub/sensor heights, historical publication times, SCADA timezone and interval labels remain unconfirmed. Schema compatibility does not establish that forecast wind at 100 m matches measured-wind training inputs. No February power labels were used.

Final models include data through January 31 23:00 in an unspecified source timezone. **Do not use them for an honest January backtest or a January 31 12:00 issue.** Such a forecast needs a separate model trained only on observations available before that issue, accounting for aggregation and publication delays, with cutoff/timezone documented. The adapter rejects early issues, but its conservative cutoff guard is not an as-of training pipeline. Models were physically built in September: this is a historical-input integration simulation, not actual February deployment.

## Documentation and checks

- [Prediction interface](prediction/README.md), [model metadata](models/metadata.json).
- [Data contract and daily schedule](docs/data_contract.md).
- [Provenance evidence](docs/weather_archive_provenance.md), [organizer questions](docs/organizer_questions.md).
- Rebuild weather example offline: `python -B scripts/build_weather_example.py`.
- Tests: `.\.venv\ml\python.exe -B -m unittest prediction.test_interface scripts.test_weather_integration`.

Local environments and production datasets remain ignored. The deployable models and small examples are retained for reproducibility.
