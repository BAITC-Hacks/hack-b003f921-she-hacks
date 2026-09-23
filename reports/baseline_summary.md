# EDA and chronological linear baseline

Training ends before 2025-08-01; validation is 2025-08-01 through 2026-01-31. The common calendar split and ordinary least-squares model were fixed before evaluation. There is no random split, tuning, imputation, lag feature, or serialized model.

EDA target/feature plots use training data only to keep validation untouched by exploratory model selection. Coverage plots alone span the full allowed period, without plotting validation targets. Means by month of year pool training years; companion calendar-month tables and counts expose unequal coverage.

Rows need a valid timestamp and finite power, wind speed, and temperature. Empty hours are excluded; partial hours with all required means are retained with equal row weight. Zero-power rows are retained. No missing periods are filled. Exclusion reasons use priority: invalid timestamp, after cutoff, empty hour, invalid required measurement.

This measures contemporaneous power estimation using measured weather for the same hour. It does not measure advance forecasting performance: future measured weather would not be available at forecast issue time. Source timestamps have no known timezone and retain their original clock.

| Turbine | Train rows | Validation rows | Excluded | MAE | RMSE | R2 |
|---|---:|---:|---:|---:|---:|---:|
| turbine_1 | 19403 | 4360 | 1629 | 0.086166 | 0.103520 | 0.912673 |
| turbine_2 | 20647 | 4357 | 388 | 0.088824 | 0.110381 | 0.900161 |

## turbine_1

- Training: ['2023-03-11 00:00:00', '2025-07-31 23:00:00']; validation: ['2025-08-01 00:00:00', '2026-01-31 23:00:00'].
- Exclusions: {'empty_hour': 1629}; retained incomplete hours: 83 training, 13 validation.
- Training-mean reference: {'mae': 0.311471015766738, 'rmse': 0.3514172377383151, 'r2': -0.006347645314665806}.
- Complete validation hours only (same fitted model): {'mae': 0.08617006509250247, 'rmse': 0.10350743189250805, 'r2': 0.9126292976921235}.
- Unclipped predictions outside [0, 1]: 968. OLS does not enforce physical bounds.
- Training power correlation: wind 0.9470; temperature -0.1764. These are associations, not causal effects.
- Mean power by hour ranges 0.3415 to 0.4099; lowest hour 7, highest 12.
- Mean power by month ranges 0.2431 to 0.5003; lowest month 8, highest 12.
- Wind-bin power means/counts: {'[-inf, 3.0)': {'mean': 0.014659649122806996, 'count': 4275}, '[3.0, 5.0)': {'mean': 0.07407443820224716, 'count': 3204}, '[5.0, 8.0)': {'mean': 0.2932825298568123, 'count': 5331}, '[8.0, 12.0)': {'mean': 0.7805693945442448, 'count': 5010}, '[12.0, inf)': {'mean': 0.9611776163402821, 'count': 1583}}.
- Training hourly power exactly zero: 0.

## turbine_2

- Training: ['2023-03-11 00:00:00', '2025-07-31 23:00:00']; validation: ['2025-08-01 00:00:00', '2026-01-31 23:00:00'].
- Exclusions: {'empty_hour': 388}; retained incomplete hours: 203 training, 16 validation.
- Training-mean reference: {'mae': 0.3111261831517674, 'rmse': 0.350389213056482, 'r2': -0.006028416063930786}.
- Complete validation hours only (same fitted model): {'mae': 0.08866091781203912, 'rmse': 0.1097339053365586, 'r2': 0.9011945118268417}.
- Unclipped predictions outside [0, 1]: 978. OLS does not enforce physical bounds.
- Training power correlation: wind 0.9553; temperature -0.1547. These are associations, not causal effects.
- Mean power by hour ranges 0.3270 to 0.4098; lowest hour 5, highest 11.
- Mean power by month ranges 0.2450 to 0.4951; lowest month 8, highest 12.
- Wind-bin power means/counts: {'[-inf, 3.0)': {'mean': 0.013997510822510797, 'count': 4620}, '[3.0, 5.0)': {'mean': 0.07055287256603042, 'count': 3458}, '[5.0, 8.0)': {'mean': 0.28347870553656046, 'count': 5557}, '[8.0, 12.0)': {'mean': 0.7734045701502077, 'count': 5215}, '[12.0, inf)': {'mean': 0.9611893897236132, 'count': 1797}}.
- Training hourly power exactly zero: 7.

## Interpretation and verification

The turbines share a calendar holdout but have different available timestamps, so their metrics are not a perfectly paired comparison. Monthly and hourly patterns reflect available observations and missing periods; they are descriptive, not proof of a causal seasonal effect. The curved wind-power relationship and saturation visible in the scatter plots limit a two-feature linear model. No model choice was adjusted after viewing validation results.

Passed: chronological split, cutoff, row accounting, export readback, independent least squares and metrics, unchanged source hashes.

Created artifacts: `scripts/run_baseline.py`, `training/eda_baseline.py`, `training/test_eda_baseline.py`, `training/requirements-baseline.txt`, `training/BASELINE.md`; `data/processed/turbine_{1,2}_baseline_{training,validation,excluded}.csv`; `reports/baseline_results.json`, this report, per-turbine validation predictions, training descriptive statistics/correlations and grouped power tables; five PNG figures per turbine in `reports/figures/`. The complete result JSON records coefficients, package versions, and input hashes. No final model artifact is saved.
