# EDA and baseline reproduction

Run from the repository root with a normal Python 3.11 or 3.12 installation
and the pinned dependencies. Create the project environment once:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r training/requirements-baseline.txt
```

Run checks and analysis from the project environment:

```powershell
.\.venv\Scripts\python.exe scripts/run_baseline.py --test
.\.venv\Scripts\python.exe scripts/run_baseline.py
```

The launcher adds the repository to the module search path and uses dependencies
installed in the active project environment. It does not load the unused
`.venv/baseline-packages` directory from the initial setup attempt. No PostgreSQL
or pgAdmin interpreter is used or modified by this workflow.

The script consumes only `data/processed/turbine_{1,2}_hourly.csv` for analysis.
It hashes raw CSVs solely to verify they remain unchanged. It neither modifies
the raw/hourly inputs nor calls a weather service or the agent pipeline.

The common, fixed validation window is August 1, 2025 through January 31, 2026,
inclusive. Training uses all earlier eligible hours. Nothing from February 2026
or later is used for fitting, validation, or EDA. Input timestamps remain in their
unspecified source timezone.

Each included row must contain finite power, wind speed, and temperature means
and a valid timestamp. Empty hours are excluded. Partial hours remain eligible
when all three means are valid; they receive the same weight as complete hours.
Their counts are reported by split, and complete-hour-only validation metrics
are also reported using the same fitted model. No imputation, interpolation,
deduplication, physical-bound clipping, or zero-power removal is performed.
Duplicate timestamps or inconsistent observation-count flags fail explicitly.
Exclusion CSVs record one prioritized reason per excluded row.

The baseline is `LinearRegression` with an intercept and exactly two features:
`mean_measured_wind_speed` and `mean_measured_temperature`. The target is
`mean_normalized_power`. No hyperparameters are selected using validation.
The training-mean constant reference supplies context for the regression scores.
Predictions are unbounded; counts outside [0, 1] are reported rather than clipped.
Coefficients in the result JSON are audit information; no model.pkl or other
serialized model is created.

Feature and target EDA is restricted to training rows. For each turbine, five
PNG figures contain the three distributions, two scatter plots, hour-of-day and
month-of-year power averages, power time series, and full-period coverage.
The coverage plot uses observation counts only and shades the validation period.
Companion CSVs contain descriptive statistics, correlations, wind-bin summaries,
hour/month means and counts, and calendar-month means and counts. Monthly curves
pool different years and reflect uneven coverage; no causal claims follow.
Time-series plots preserve missing periods as breaks. Displayed daily means use
available hours and are not used for training.

Outputs:

- `data/processed/turbine_{1,2}_baseline_training.csv`
- `data/processed/turbine_{1,2}_baseline_validation.csv`
- `data/processed/turbine_{1,2}_baseline_excluded.csv`
- `reports/baseline_summary.md` and `reports/baseline_results.json`
- `reports/turbine_{1,2}_validation_predictions.csv`
- `reports/turbine_{1,2}_training_descriptive_statistics.csv`
- `reports/turbine_{1,2}_training_correlations.csv`
- `reports/turbine_{1,2}_power_by_{hour,month,calendar_month,wind_bin}.csv`
- `reports/figures/turbine_{1,2}_{distributions,scatter,seasonality,power_timeseries,coverage}.png`

Each run checks chronological separation, the date cutoff, row accounting,
exported datasets, independently solved least squares, independently calculated
metrics, reloaded prediction metrics, and unchanged input hashes. Boundary tests
cover the exact split and cutoff, zero/partial/empty hours, invalid data,
duplicates, and large gaps. Re-running overwrites only generated baseline/EDA
outputs.

These metrics assess power estimated from measured weather in the same hour.
They do not establish future forecast accuracy: measured future wind and
temperature are unavailable at forecast issue time. The two turbines have the
same validation calendar window but differing available hours.
