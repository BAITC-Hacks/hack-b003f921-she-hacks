# Use the saved turbine models without retraining

Copy the `prediction/` package and these three files, preserving their layout:

```text
models/metadata.json
models/turbine_1_catboost.cbm
models/turbine_2_catboost.cbm
```

Models are ignored by the repository's existing Git rules. Transfer these files
separately to your teammate; a source checkout alone does not include them.
No Git ignore rules have been changed. The loader checks SHA256 hashes and
feature order. Model version and training details are in `models/metadata.json`.

With a normal Python 3.11 environment, install inference dependencies only:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r prediction/requirements.txt
```

The current project's `.venv` already has these packages. Run from the repository
root; none of the following commands retrains a model or fetches weather.

## Single prediction

```powershell
.\.venv\Scripts\python.exe -m prediction single --turbine-id turbine_1 --wind-speed-ms 7.5 --temperature-c 5
```

Output is a JSON object with `predicted_normalized_power`.

```python
from prediction import TurbinePredictor

predictor = TurbinePredictor()  # Load both saved models once and reuse.
result = predictor.predict(turbine_id="turbine_1", wind_speed_ms=7.5, temperature_c=5)
power = result["predicted_normalized_power"]
```

Supported IDs are `turbine_1`, `turbine_2`, or aliases `1` and `2` (integers or
strings). Wind speed is in m/s, temperature in degrees Celsius. Values must be
finite numbers and wind speed must be non-negative. Inputs outside the observed
training ranges are accepted, but output bounds do not guarantee accuracy there.

## Batch prediction

```powershell
.\.venv\Scripts\python.exe -m prediction batch --input examples/synthetic_weather_input.csv --output examples/synthetic_weather_output.csv
```

Required input columns:

```text
issue_time_utc,weather_run_time_utc,target_time_utc,turbine_id,forecast_horizon_h,wind_speed_ms,temperature_c
```

Output preserves the input columns, values, row order, and any extra columns,
and appends `predicted_normalized_power`. CSV formatting/quoting may be normalized.
The three timestamps must be valid ISO-8601 UTC strings ending in `Z` or `+00:00`.
Horizon must be numeric, finite, and non-negative. These timing fields are
preserved metadata; they are not model features. The interface does not infer
whether horizon was calculated from issue time or weather-run time.

Duplicate turbine/target pairs are rejected, even across ID aliases or equivalent
UTC timestamp spellings. This applies across weather runs: submit different runs
in separate batches if they contain the same turbine and target time. Missing
columns, duplicate column names, unsupported IDs, invalid weather values, and an
existing prediction column are rejected. The entire batch is validated before
writing; input and output paths must differ. A valid run overwrites the chosen
output file. CLI input errors exit with code 2. Python methods raise exceptions.

For pandas callers:

```python
output_frame = predictor.predict_batch(input_frame)
# Or read/write CSV while preserving input values as strings:
predictor.predict_csv("forecast.csv", "predictions.csv")
```

For artifacts elsewhere, use `TurbinePredictor(model_dir=...)` or the CLI global
option `--model-dir PATH` before `single` or `batch`.

Both interfaces clip final predictions to [0, 1]. Power is dimensionless
normalized active power, not MW. The only learned features are `wind_speed_ms`
and `temperature_c`. No power lags, rolling features, or future power are used.

## Training provenance and tests

Deployable models use every eligible hourly row through January 31, 2026,
including the old validation period. Partial hours with all three finite means
are retained at equal weight; empty hours are excluded. Zero-power rows remain.
There is no interpolation. Metadata records counts, exclusions, units, source
hashes, artifact hashes, training ranges, and the approved fixed configuration.

The earlier comparison reports describe earlier models evaluated with measured
same-hour weather. They are not validation scores for these full-history refits
and do not establish 24-48 hour forecast accuracy. The synthetic example contains
invented weather and is strictly an integration fixture, never training data.

Run integration tests against the already-trained artifacts:

```powershell
.\.venv\Scripts\python.exe -m unittest prediction.test_interface -v
```

For the Data & ML owner only, intentional retraining is a separate command:

```powershell
.\.venv\Scripts\python.exe -m training.train_deployable
```

Training requires `training/requirements-comparison.txt`. It overwrites the two
CBM files and metadata, verifies save/load equivalence, and hashes existing data
and reports to ensure they are unchanged. It does not write evaluation reports.
