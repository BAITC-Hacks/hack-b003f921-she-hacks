"""Reproducible training-only EDA and fixed chronological OLS baseline."""
from pathlib import Path
import hashlib
import json
import platform
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / 'data' / 'processed'
REPORTS = ROOT / 'reports'
FIGURES = REPORTS / 'figures'
FEATURES = ['mean_measured_wind_speed', 'mean_measured_temperature']
TARGET = 'mean_normalized_power'
REQUIRED = [TARGET, *FEATURES]
SPLIT = pd.Timestamp('2025-08-01')
END = pd.Timestamp('2026-02-01')  # Exclusive: January 31 is included in full.
LABELS = {TARGET: 'Normalized power', FEATURES[0]: 'Wind speed (m/s)',
          FEATURES[1]: 'Ambient temperature (degrees C)'}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(frame):
    """Return eligible rows and an exclusive reason for every excluded row."""
    frame = frame.copy()
    required_columns = ['timestamp', *REQUIRED, 'observations_count', 'is_complete_hour']
    if not set(required_columns).issubset(frame.columns):
        raise ValueError('Missing hourly input columns')
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
    for column in REQUIRED + ['observations_count']:
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    if frame['timestamp'].dropna().duplicated().any():
        raise ValueError('Duplicate hourly timestamps require explicit resolution')
    counts = frame['observations_count']
    if (~np.isfinite(counts) | (counts < 0) | (counts % 1 != 0)).any():
        raise ValueError('Invalid observation counts')
    flags = frame['is_complete_hour'].astype(str).str.lower()
    if not flags.isin(['true', 'false']).all() or not (flags.eq('true') == counts.eq(6)).all():
        raise ValueError('Completeness flag inconsistent with observation count')
    reason = pd.Series('', index=frame.index)
    conditions = [
        ('invalid_timestamp', frame['timestamp'].isna()),
        ('after_2026_01_31', frame['timestamp'].ge(END)),
        ('empty_hour', counts.eq(0)),
        ('missing_or_nonfinite_required_value', ~np.isfinite(frame[REQUIRED]).all(axis=1)),
    ]
    for label, mask in conditions:
        reason.loc[reason.eq('') & mask] = label
    excluded = frame.loc[reason.ne('')].copy()
    excluded['exclusion_reason'] = reason.loc[excluded.index]
    eligible = frame.loc[reason.eq('')].sort_values('timestamp').copy()
    eligible['split'] = np.where(eligible['timestamp'] < SPLIT, 'train', 'validation')
    return eligible, excluded


def evaluate(actual, predicted):
    return {'mae': float(mean_absolute_error(actual, predicted)),
            'rmse': float(np.sqrt(mean_squared_error(actual, predicted))),
            'r2': float(r2_score(actual, predicted))}


def save_plot(fig, name):
    fig.tight_layout()
    fig.savefig(FIGURES / name, dpi=150)
    plt.close(fig)


def eda(train, full, turbine):
    """Fit-period EDA only; full timeline is a labelled coverage diagnostic."""
    prefix = f'turbine_{turbine}'
    title = f'Turbine {turbine} | training only, before 2025-08-01'
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, column in zip(axes, REQUIRED):
        ax.hist(train[column], bins=40, color='#277da1', edgecolor='white', linewidth=.3)
        ax.set(xlabel=LABELS[column], ylabel='Hourly observations')
    fig.suptitle(title + '\nMeasurement distributions')
    save_plot(fig, prefix + '_distributions.png')

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, feature in zip(axes, FEATURES):
        ax.scatter(train[feature], train[TARGET], s=3, alpha=.13, rasterized=True)
        ax.set(xlabel=LABELS[feature], ylabel=LABELS[TARGET])
    fig.suptitle(title + '\nAll eligible training hours; no sampling')
    save_plot(fig, prefix + '_scatter.png')

    by_hour = train.groupby(train['timestamp'].dt.hour)[TARGET].agg(['mean', 'count']).reindex(range(24))
    by_month = train.groupby(train['timestamp'].dt.month)[TARGET].agg(['mean', 'count']).reindex(range(1, 13))
    calendar = train.groupby(train['timestamp'].dt.to_period('M'))[TARGET].agg(['mean', 'count'])
    by_hour.to_csv(REPORTS / (prefix + '_power_by_hour.csv'), index_label='hour')
    by_month.to_csv(REPORTS / (prefix + '_power_by_month.csv'), index_label='month')
    calendar.to_csv(REPORTS / (prefix + '_power_by_calendar_month.csv'), index_label='month')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].bar(by_hour.index, by_hour['mean'], color='#277da1')
    axes[0].set(xlabel='Hour of day (source clock)', ylabel='Mean normalized power', xticks=range(0, 24, 2))
    axes[1].bar(by_month.index, by_month['mean'], color='#43aa8b')
    axes[1].set(xlabel='Month of year (pooled across training years)', ylabel='Mean normalized power', xticks=range(1, 13))
    fig.suptitle(title + '\nUnweighted means of available hourly rows; counts in companion CSVs')
    save_plot(fig, prefix + '_seasonality.png')

    # Reindex explicitly so lines cannot bridge missing hours or entire missing days.
    grid = pd.date_range(train['timestamp'].min(), SPLIT - pd.Timedelta(hours=1), freq='h')
    power = train.set_index('timestamp')[TARGET].reindex(grid)
    daily = power.resample('D').mean()
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.plot(power.index, power, color='#90bed0', linewidth=.35, label='Hourly power (gaps preserved)')
    ax.plot(daily.index, daily, color='#163d57', linewidth=.8, label='Daily mean of available hours')
    ax.set(xlabel='Date', ylabel='Normalized power', title=title + '\nPower time series')
    ax.legend(loc='upper right')
    save_plot(fig, prefix + '_power_timeseries.png')

    coverage = full.set_index('timestamp')['observations_count'].sort_index()
    fig, ax = plt.subplots(figsize=(14, 2.8))
    ax.plot(coverage.index, coverage, linewidth=.5, color='#277da1')
    ax.axvspan(SPLIT, END, color='#f9c74f', alpha=.25, label='Held-out validation period')
    ax.set(xlabel='Date', ylabel='10-minute observations/hour', title=f'Turbine {turbine} | full-period coverage (no target values)')
    ax.legend()
    save_plot(fig, prefix + '_coverage.png')

    stats = train[REQUIRED].describe(percentiles=[.05, .25, .5, .75, .95])
    stats.to_csv(REPORTS / (prefix + '_training_descriptive_statistics.csv'))
    corr = train[REQUIRED].corr()
    corr.to_csv(REPORTS / (prefix + '_training_correlations.csv'))
    # Numeric wind-bin summaries substantiate shape observations in the report.
    edges = [-np.inf, 3, 5, 8, 12, np.inf]
    bins = pd.cut(train[FEATURES[0]], edges, right=False)
    wind_bins = train.groupby(bins, observed=True)[TARGET].agg(['mean', 'count'])
    wind_bins.to_csv(REPORTS / (prefix + '_power_by_wind_bin.csv'), index_label='wind_m_s')
    return {
        'training_means': train[REQUIRED].mean().to_dict(),
        'power_wind_correlation': float(corr.loc[TARGET, FEATURES[0]]),
        'power_temperature_correlation': float(corr.loc[TARGET, FEATURES[1]]),
        'highest_power_hour': int(by_hour['mean'].idxmax()),
        'lowest_power_hour': int(by_hour['mean'].idxmin()),
        'hourly_mean_range': [float(by_hour['mean'].min()), float(by_hour['mean'].max())],
        'highest_power_month': int(by_month['mean'].idxmax()),
        'lowest_power_month': int(by_month['mean'].idxmin()),
        'monthly_mean_range': [float(by_month['mean'].min()), float(by_month['mean'].max())],
        'zero_power_training_hours': int(train[TARGET].eq(0).sum()),
        'wind_bins': {str(k): {'mean': float(v['mean']), 'count': int(v['count'])}
                      for k, v in wind_bins.iterrows()},
    }


def period(frame):
    return [str(frame['timestamp'].min()), str(frame['timestamp'].max())]


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    # Verify both raw inputs and hourly inputs stay byte-for-byte unchanged.
    sources = list((ROOT / 'data' / 'raw').glob('*.csv')) + [PROCESSED / f'turbine_{t}_hourly.csv' for t in (1, 2)]
    hashes = {str(p.relative_to(ROOT)): sha256(p) for p in sources}
    results = {}
    for turbine in (1, 2):
        prefix = f'turbine_{turbine}'
        source = pd.read_csv(PROCESSED / (prefix + '_hourly.csv'))
        eligible, excluded = prepare(source)
        train = eligible.loc[eligible['split'].eq('train')].copy()
        valid = eligible.loc[eligible['split'].eq('validation')].copy()
        if len(train) < 3 or len(valid) < 2:
            raise ValueError('Insufficient train/validation observations')
        assert train['timestamp'].max() < valid['timestamp'].min()
        assert eligible['timestamp'].max() < END
        assert len(eligible) + len(excluded) == len(source)
        for name, frame in [('training', train), ('validation', valid), ('excluded', excluded)]:
            path = PROCESSED / f'{prefix}_baseline_{name}.csv'
            frame.to_csv(path, index=False, date_format='%Y-%m-%d %H:%M:%S')
            assert len(pd.read_csv(path)) == len(frame)

        # Ordinary least squares: fit only on the earlier training partition.
        # No scaling, tuning, clipping, target transforms, or model serialization.
        model = LinearRegression().fit(train[FEATURES], train[TARGET])
        predicted = model.predict(valid[FEATURES])
        metrics = evaluate(valid[TARGET], predicted)
        reference = evaluate(valid[TARGET], np.full(len(valid), train[TARGET].mean()))
        # Independent least-squares implementation verifies fitted predictions.
        design = np.column_stack([np.ones(len(train)), train[FEATURES].to_numpy()])
        coefficients = np.linalg.lstsq(design, train[TARGET].to_numpy(), rcond=None)[0]
        independent = np.column_stack([np.ones(len(valid)), valid[FEATURES].to_numpy()]) @ coefficients
        np.testing.assert_allclose(predicted, independent, rtol=1e-10, atol=1e-10)
        error = valid[TARGET].to_numpy() - predicted
        assert np.isclose(metrics['mae'], np.abs(error).mean())
        assert np.isclose(metrics['rmse'], np.sqrt(np.mean(error**2)))
        assert np.isclose(metrics['r2'], 1 - np.sum(error**2) / np.sum((valid[TARGET] - valid[TARGET].mean())**2))
        predictions = valid[['timestamp', TARGET, 'observations_count', 'is_complete_hour']].copy()
        predictions['predicted_normalized_power'] = predicted
        predictions['training_mean_prediction'] = train[TARGET].mean()
        predictions.to_csv(REPORTS / (prefix + '_validation_predictions.csv'), index=False)
        reread = pd.read_csv(REPORTS / (prefix + '_validation_predictions.csv'))
        for key, value in evaluate(reread[TARGET], reread['predicted_normalized_power']).items():
            assert np.isclose(value, metrics[key])
        complete = valid['observations_count'].eq(6)
        complete_metrics = evaluate(valid.loc[complete, TARGET], predicted[complete]) if complete.sum() > 1 else None
        # EDA never inspects validation targets; only coverage uses the full period.
        coverage = source.copy()
        coverage['timestamp'] = pd.to_datetime(coverage['timestamp'], errors='coerce')
        coverage = coverage.loc[coverage['timestamp'].notna() & coverage['timestamp'].lt(END)]
        patterns = eda(train, coverage, turbine)
        results[prefix] = {
            'input_rows': len(source), 'eligible_rows': len(eligible),
            'excluded_rows': len(excluded), 'excluded_reasons': excluded['exclusion_reason'].value_counts().to_dict(),
            'training_rows': len(train), 'validation_rows': len(valid),
            'training_period': period(train), 'validation_period': period(valid),
            'training_incomplete_retained': int(train['observations_count'].ne(6).sum()),
            'validation_incomplete_retained': int(valid['observations_count'].ne(6).sum()),
            'linear_regression': metrics, 'training_mean_reference': reference,
            'complete_validation_hours_only': complete_metrics,
            'intercept': float(model.intercept_), 'coefficients': dict(zip(FEATURES, model.coef_.tolist())),
            'predictions_outside_0_1': int(((predicted < 0) | (predicted > 1)).sum()),
            'eda': patterns,
        }
    assert hashes == {str(p.relative_to(ROOT)): sha256(p) for p in sources}
    report = {'model': 'Ordinary least squares with intercept; predictions not clipped',
              'features': FEATURES, 'target': TARGET, 'validation_start': str(SPLIT),
              'data_end_exclusive': str(END), 'input_sha256': hashes,
              'python_environment': {'executable': sys.executable, 'prefix': sys.prefix, 'base_prefix': sys.base_prefix},
              'versions': {'python': platform.python_version(), 'numpy': np.__version__,
                           'pandas': pd.__version__, 'matplotlib': matplotlib.__version__, 'sklearn': sklearn.__version__},
              'verification': 'Passed: chronological split, cutoff, row accounting, export readback, independent least squares and metrics, unchanged source hashes',
              'turbines': results}
    (REPORTS / 'baseline_results.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    write_summary(report)
    print(json.dumps(results, indent=2))


def write_summary(report):
    lines = ['# EDA and chronological linear baseline', '',
        'Training ends before 2025-08-01; validation is 2025-08-01 through 2026-01-31. '
        'The common calendar split and ordinary least-squares model were fixed before evaluation. '
        'There is no random split, tuning, imputation, lag feature, or serialized model.', '',
        'EDA target/feature plots use training data only to keep validation untouched by exploratory model selection. '
        'Coverage plots alone span the full allowed period, without plotting validation targets. '
        'Means by month of year pool training years; companion calendar-month tables and counts expose unequal coverage.', '',
        'Rows need a valid timestamp and finite power, wind speed, and temperature. '
        'Empty hours are excluded; partial hours with all required means are retained with equal row weight. '
        'Zero-power rows are retained. No missing periods are filled. '
        'Exclusion reasons use priority: invalid timestamp, after cutoff, empty hour, invalid required measurement.', '',
        'This measures contemporaneous power estimation using measured weather for the same hour. '
        'It does not measure advance forecasting performance: future measured weather would not be available at forecast issue time. '
        'Source timestamps have no known timezone and retain their original clock.', '',
        '| Turbine | Train rows | Validation rows | Excluded | MAE | RMSE | R2 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name, result in report['turbines'].items():
        m = result['linear_regression']
        lines.append(f"| {name} | {result['training_rows']} | {result['validation_rows']} | {result['excluded_rows']} | {m['mae']:.6f} | {m['rmse']:.6f} | {m['r2']:.6f} |")
    for name, r in report['turbines'].items():
        e = r['eda']
        lines += ['', f'## {name}', '',
            f"- Training: {r['training_period']}; validation: {r['validation_period']}.",
            f"- Exclusions: {r['excluded_reasons']}; retained incomplete hours: {r['training_incomplete_retained']} training, {r['validation_incomplete_retained']} validation.",
            f"- Training-mean reference: {r['training_mean_reference']}.",
            f"- Complete validation hours only (same fitted model): {r['complete_validation_hours_only']}.",
            f"- Unclipped predictions outside [0, 1]: {r['predictions_outside_0_1']}. OLS does not enforce physical bounds.",
            f"- Training power correlation: wind {e['power_wind_correlation']:.4f}; temperature {e['power_temperature_correlation']:.4f}. These are associations, not causal effects.",
            f"- Mean power by hour ranges {e['hourly_mean_range'][0]:.4f} to {e['hourly_mean_range'][1]:.4f}; lowest hour {e['lowest_power_hour']}, highest {e['highest_power_hour']}.",
            f"- Mean power by month ranges {e['monthly_mean_range'][0]:.4f} to {e['monthly_mean_range'][1]:.4f}; lowest month {e['lowest_power_month']}, highest {e['highest_power_month']}.",
            f"- Wind-bin power means/counts: {e['wind_bins']}.",
            f"- Training hourly power exactly zero: {e['zero_power_training_hours']}."]
    lines += ['', '## Interpretation and verification', '',
        'The turbines share a calendar holdout but have different available timestamps, so their metrics are not a perfectly paired comparison. '
        'Monthly and hourly patterns reflect available observations and missing periods; they are descriptive, not proof of a causal seasonal effect. '
        'The curved wind-power relationship and saturation visible in the scatter plots limit a two-feature linear model. '
        'No model choice was adjusted after viewing validation results.', '', report['verification'] + '.', '',
        'Created artifacts: `scripts/run_baseline.py`, `training/eda_baseline.py`, `training/test_eda_baseline.py`, '
        '`training/requirements-baseline.txt`, `training/BASELINE.md`; '
        '`data/processed/turbine_{1,2}_baseline_{training,validation,excluded}.csv`; '
        '`reports/baseline_results.json`, this report, per-turbine validation predictions, '
        'training descriptive statistics/correlations and grouped power tables; '
        'five PNG figures per turbine in `reports/figures/`. '
        'The complete result JSON records coefficients, package versions, and input hashes. '
        'No final model artifact is saved.', '']
    (REPORTS / 'baseline_summary.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
