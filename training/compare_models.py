"""Fixed-configuration comparison on the approved chronological split."""
import json
import platform
import sys
from time import perf_counter

import catboost
from catboost import CatBoostRegressor
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from training.eda_baseline import (
    ROOT, PROCESSED, REPORTS, FIGURES, FEATURES, TARGET, SPLIT, END,
    prepare, evaluate, sha256, plt, save_plot,
)

# Fixed before evaluating; no hyperparameter search or holdout early stopping.
CONFIGS = {
    'Linear Regression': {},
    'Random Forest': dict(n_estimators=300, max_depth=12, min_samples_leaf=5,
                          max_features=1.0, random_state=42, n_jobs=2),
    'CatBoost': dict(iterations=600, depth=6, learning_rate=0.05,
                    loss_function='RMSE', random_seed=42, thread_count=2,
                    verbose=False, allow_writing_files=False),
}
CLASSES = {'Linear Regression': LinearRegression,
           'Random Forest': RandomForestRegressor, 'CatBoost': CatBoostRegressor}


def main():
    REPORTS.mkdir(exist_ok=True)
    FIGURES.mkdir(exist_ok=True)
    inputs = list((ROOT / 'data/raw').glob('*.csv')) + list(PROCESSED.glob('*.csv'))
    hashes = {str(p.relative_to(ROOT)): sha256(p) for p in inputs}
    results, monthly, datasets = [], [], {}
    baseline = json.loads((REPORTS / 'baseline_results.json').read_text())
    for turbine in (1, 2):
        key = f'turbine_{turbine}'
        eligible, excluded = prepare(pd.read_csv(PROCESSED / f'{key}_hourly.csv'))
        train = eligible.loc[eligible['split'].eq('train')].copy()
        valid = eligible.loc[eligible['split'].eq('validation')].copy()
        assert len(train) > 2 and len(valid) > 1
        assert train.timestamp.max() < valid.timestamp.min()
        assert valid.timestamp.min() >= SPLIT and valid.timestamp.max() < END
        # Ensure exactly the same prepared rows as the approved baseline.
        for label, frame in [('training', train), ('validation', valid)]:
            saved = pd.read_csv(PROCESSED / f'{key}_baseline_{label}.csv', parse_dates=['timestamp'])
            assert saved.timestamp.tolist() == frame.timestamp.tolist()
            np.testing.assert_allclose(saved[[*FEATURES, TARGET]], frame[[*FEATURES, TARGET]], rtol=1e-12, atol=1e-12)
        datasets[key] = {
            'training_rows': len(train), 'validation_rows': len(valid),
            'excluded_rows': len(excluded), 'excluded_reasons': excluded.exclusion_reason.value_counts().to_dict(),
            'training_period': [str(train.timestamp.min()), str(train.timestamp.max())],
            'validation_period': [str(valid.timestamp.min()), str(valid.timestamp.max())],
            'training_partial_hours': int(train.observations_count.ne(6).sum()),
            'validation_partial_hours': int(valid.observations_count.ne(6).sum()),
        }
        predictions = valid[['timestamp', TARGET, 'observations_count']].copy()
        for name, cls in CLASSES.items():
            model = cls(**CONFIGS[name])
            start = perf_counter()
            model.fit(train[FEATURES], train[TARGET])
            seconds = perf_counter() - start
            predicted = model.predict(valid[FEATURES])
            assert np.isfinite(predicted).all()
            metrics = evaluate(valid[TARGET], predicted)
            error = valid[TARGET].to_numpy() - predicted
            assert np.isclose(metrics['mae'], np.abs(error).mean())
            assert np.isclose(metrics['rmse'], np.sqrt(np.mean(error**2)))
            assert np.isclose(metrics['r2'], 1 - np.sum(error**2) / np.sum((valid[TARGET] - valid[TARGET].mean())**2))
            if name == 'Linear Regression':
                for metric, value in metrics.items():
                    assert np.isclose(value, baseline['turbines'][key]['linear_regression'][metric], atol=1e-12)
            complete = valid.observations_count.eq(6)
            result = dict(turbine=key, model=name, **metrics, fit_seconds=seconds,
                          training_metrics=evaluate(train[TARGET], model.predict(train[FEATURES])),
                          complete_hours_metrics=evaluate(valid.loc[complete, TARGET], predicted[complete]),
                          predictions_outside_0_1=int(((predicted < 0) | (predicted > 1)).sum()))
            results.append(result)
            predictions[name] = predicted
            for month, subset in predictions.groupby(predictions.timestamp.dt.to_period('M')):
                monthly.append(dict(turbine=key, model=name, month=str(month), rows=len(subset),
                                    **evaluate(subset[TARGET], subset[name])))
            print(f'{key} | {name}: MAE={metrics["mae"]:.6f}, RMSE={metrics["rmse"]:.6f}, R2={metrics["r2"]:.6f}', flush=True)
        path = REPORTS / f'{key}_comparison_predictions.csv'
        predictions.to_csv(path, index=False)
        loaded = pd.read_csv(path)
        assert len(loaded) == len(valid)
        for result in results:
            if result['turbine'] == key:
                for metric, value in evaluate(loaded[TARGET], loaded[result['model']]).items():
                    assert np.isclose(value, result[metric], atol=1e-12)
    assert hashes == {str(p.relative_to(ROOT)): sha256(p) for p in inputs}
    table = pd.DataFrame([{k: v for k, v in r.items() if not isinstance(v, dict)} for r in results])
    table.to_csv(REPORTS / 'model_comparison_metrics.csv', index=False)
    pd.DataFrame(monthly).to_csv(REPORTS / 'model_comparison_monthly_metrics.csv', index=False)
    report = dict(features=FEATURES, target=TARGET, configs=CONFIGS, datasets=datasets, results=results,
                  input_sha256=hashes, python_executable=sys.executable,
                  versions=dict(python=platform.python_version(), catboost=catboost.__version__,
                                sklearn=sklearn.__version__, numpy=np.__version__, pandas=pd.__version__),
                  verification='Passed: original split/rows/values, finite predictions, baseline reproduction, independent metrics, prediction export readback, unchanged inputs')
    (REPORTS / 'model_comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    names = list(CLASSES)
    for ax, metric in zip(axes, ['mae', 'rmse', 'r2']):
        for t, color in [(1, '#277da1'), (2, '#f8961e')]:
            values = table.loc[table.turbine.eq(f'turbine_{t}')].set_index('model').loc[names, metric]
            ax.bar(np.arange(3) + (t - 1.5) * .36, values, width=.36, color=color, label=f'Turbine {t}')
        ax.set(xticks=np.arange(3), xticklabels=['Linear', 'Forest', 'CatBoost'], title=metric.upper())
        ax.legend()
    fig.suptitle('Chronological validation: Aug 2025 - Jan 2026 | unmodified predictions')
    save_plot(fig, 'model_comparison.png')
    lines = ['# Linear Regression vs Random Forest vs CatBoost', '',
             'Same two measured-weather features, eligible rows, and chronological split for all models. '
             'Train: 2023-03-11 through 2025-07-31. Validate: 2025-08-01 through 2026-01-31. '
             'Partial hours with finite means are retained; empty/invalid hours are excluded. '
             'No filling, lag features, February data, early stopping, or hyperparameter search. '
             'All configurations were fixed before this comparison. Predictions are not clipped.', '',
             '| Turbine | Model | MAE | RMSE | R2 |', '|---|---|---:|---:|---:|']
    for r in results:
        lines.append(f"| {r['turbine']} | {r['model']} | {r['mae']:.6f} | {r['rmse']:.6f} | {r['r2']:.6f} |")
    for key in datasets:
        subset = table.loc[table.turbine.eq(key)]
        best = subset.sort_values('rmse').iloc[0]
        linear = subset.loc[subset.model.eq('Linear Regression')].iloc[0]
        lines += ['', f"{key}: lowest validation RMSE is {best['model']}; "
                  f"{100 * (1 - best.rmse / linear.rmse):.1f}% lower than Linear Regression.",
                  f"Dataset accounting: {datasets[key]}."]
    lines += ['', '## Interpretation', '',
              'The winner by RMSE is provisional for these fixed configurations and this calendar period. '
              'This validation period was already used for baseline reporting and is now used for model comparison; '
              'it is not an untouched final test set. No claim of an unbiased final test score is made. '
              'Monthly metrics expose variation over the holdout; they are not separately retrained rolling backtests. '
              'Training and complete-hour-only metrics, out-of-range prediction counts, configurations, versions, '
              'and hashes are in model_comparison.json. Turbines have different available hours. '
              'Measured weather at the same hour makes this a power-estimation evaluation, not forecast-weather evaluation.', '',
              'No models are serialized or refitted on validation. No weather or agent code is touched.', '',
              report['verification'] + '.', '', '## Reproduce', '', '```powershell',
              '.\\.venv\\Scripts\\python.exe -m pip install -r training/requirements-comparison.txt',
              '.\\.venv\\Scripts\\python.exe scripts/run_comparison.py', '```', '',
              'Created code: scripts/run_comparison.py, training/compare_models.py, training/requirements-comparison.txt. '
              'Created reports: model_comparison.md, model_comparison.json, model_comparison_metrics.csv, '
              'model_comparison_monthly_metrics.csv, turbine_{1,2}_comparison_predictions.csv, figures/model_comparison.png.', '',
              'CatBoost configuration reference: https://catboost.ai/docs/en/references/training-parameters/', '']
    (REPORTS / 'model_comparison.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
