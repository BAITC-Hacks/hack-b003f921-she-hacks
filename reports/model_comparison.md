# Linear Regression vs Random Forest vs CatBoost

Same two measured-weather features, eligible rows, and chronological split for all models. Train: 2023-03-11 through 2025-07-31. Validate: 2025-08-01 through 2026-01-31. Partial hours with finite means are retained; empty/invalid hours are excluded. No filling, lag features, February data, early stopping, or hyperparameter search. All configurations were fixed before this comparison. Predictions are not clipped.

| Turbine | Model | MAE | RMSE | R2 |
|---|---|---:|---:|---:|
| turbine_1 | Linear Regression | 0.086166 | 0.103520 | 0.912673 |
| turbine_1 | Random Forest | 0.021486 | 0.042787 | 0.985081 |
| turbine_1 | CatBoost | 0.020992 | 0.041434 | 0.986010 |
| turbine_2 | Linear Regression | 0.088824 | 0.110381 | 0.900161 |
| turbine_2 | Random Forest | 0.020879 | 0.053691 | 0.976378 |
| turbine_2 | CatBoost | 0.020304 | 0.053243 | 0.976771 |

turbine_1: lowest validation RMSE is CatBoost; 60.0% lower than Linear Regression.
Dataset accounting: {'training_rows': 19403, 'validation_rows': 4360, 'excluded_rows': 1629, 'excluded_reasons': {'empty_hour': 1629}, 'training_period': ['2023-03-11 00:00:00', '2025-07-31 23:00:00'], 'validation_period': ['2025-08-01 00:00:00', '2026-01-31 23:00:00'], 'training_partial_hours': 83, 'validation_partial_hours': 13}.

turbine_2: lowest validation RMSE is CatBoost; 51.8% lower than Linear Regression.
Dataset accounting: {'training_rows': 20647, 'validation_rows': 4357, 'excluded_rows': 388, 'excluded_reasons': {'empty_hour': 388}, 'training_period': ['2023-03-11 00:00:00', '2025-07-31 23:00:00'], 'validation_period': ['2025-08-01 00:00:00', '2026-01-31 23:00:00'], 'training_partial_hours': 203, 'validation_partial_hours': 16}.

## Interpretation

The winner by RMSE is provisional for these fixed configurations and this calendar period. This validation period was already used for baseline reporting and is now used for model comparison; it is not an untouched final test set. No claim of an unbiased final test score is made. Monthly metrics expose variation over the holdout; they are not separately retrained rolling backtests. Training and complete-hour-only metrics, out-of-range prediction counts, configurations, versions, and hashes are in model_comparison.json. Turbines have different available hours. Measured weather at the same hour makes this a power-estimation evaluation, not forecast-weather evaluation.

No models are serialized or refitted on validation. No weather or agent code is touched.

Passed: original split/rows/values, finite predictions, baseline reproduction, independent metrics, prediction export readback, unchanged inputs.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m pip install -r training/requirements-comparison.txt
.\.venv\Scripts\python.exe scripts/run_comparison.py
```

Created code: scripts/run_comparison.py, training/compare_models.py, training/requirements-comparison.txt. Created reports: model_comparison.md, model_comparison.json, model_comparison_metrics.csv, model_comparison_monthly_metrics.csv, turbine_{1,2}_comparison_predictions.csv, figures/model_comparison.png.

CatBoost configuration reference: https://catboost.ai/docs/en/references/training-parameters/
