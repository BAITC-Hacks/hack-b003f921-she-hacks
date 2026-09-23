"""Separate pre-January CatBoost artifacts; never touch deployable models."""
import argparse
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from training.train_deployable import PARAMETERS
from training.eda_baseline import ROOT, FEATURES as SOURCE_FEATURES, TARGET, prepare, sha256
from prediction.interface import FEATURES, ALIASES

CUTOFF = pd.Timestamp('2026-01-01')  # Original source clock, timezone unknown.
MODEL_DIR = ROOT / 'models/backtest_january'


def select_training(source):
    # Filter by time BEFORE applying any measurement eligibility rules.
    timestamps = pd.to_datetime(source.timestamp, format='%Y-%m-%d %H:%M:%S', errors='raise')
    if timestamps.dt.tz is not None:
        raise ValueError('Training timestamps must remain timezone-naive source clock values')
    pre = source.loc[(timestamps < CUTOFF) & (timestamps + pd.Timedelta(hours=1) <= CUTOFF)].copy()
    eligible, excluded = prepare(pre)
    assert eligible.timestamp.dt.tz is None and (eligible.timestamp < CUTOFF).all()
    return eligible, eligible.timestamp.copy(), len(excluded), len(source) - len(pre)


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()  # No timezone argument: training never localizes or shifts time.
    protected = [p for folder in ('models', 'reports', 'data') for p in (ROOT / folder).rglob('*')
                 if p.is_file() and MODEL_DIR not in p.parents]
    hashes = {str(p): sha256(p) for p in protected}
    MODEL_DIR.mkdir(exist_ok=True)
    metadata = dict(model_type='CatBoostRegressor', model_version='january-backtest-v1',
        created_at_utc=datetime.now(timezone.utc).isoformat(), features=FEATURES,
        feature_units={'wind_speed_ms': 'm/s', 'temperature_c': 'degrees Celsius'},
        target='Hourly mean normalized active power; dimensionless', output_range=[0, 1],
        hyperparameters=PARAMETERS, turbine_mapping=ALIASES, training_cutoff_exclusive_source=str(CUTOFF),
        source_timezone=None, source_timezone_status='unknown/unconfirmed', source_timezone_confirmed=False,
        timestamp_interpretation='Original timezone-naive/local source clock, hour starts. No timezone assigned and no conversion or shift during training.',
        evaluation_timezone_mapping='Required separately at evaluation; no default mapping to UTC.',
        model_simulation_available_from_source=str(CUTOFF),
        training_availability_assumption='Retrospective fit assumes all eligible pre-cutoff hourly records were available by cutoff. Historical publication/revision timing is not established; evaluator verifies publication timestamps against a supplied availability manifest.',
        baseline_rule='Latest finite power with documented available_time <= issue_time, hour end <= issue_time, and age from hour end <=24h. No interpolation or fallback. Same paired cases for ML and baseline.',
        evaluation_note='No January forecast metrics computed; January targets never enter training.', turbines={})
    for turbine in ('turbine_1', 'turbine_2'):
        path = ROOT / f'data/processed/{turbine}_hourly.csv'
        eligible, source_times, invalid, outside = select_training(pd.read_csv(path))
        if eligible.empty:
            raise ValueError('No eligible pre-January training rows')
        features = eligible[SOURCE_FEATURES].set_axis(FEATURES, axis=1)
        model = CatBoostRegressor(**PARAMETERS).fit(features, eligible[TARGET])
        artifact = MODEL_DIR / f'{turbine}_catboost.cbm'
        model.save_model(str(artifact))
        loaded = CatBoostRegressor().load_model(str(artifact))
        np.testing.assert_allclose(model.predict(features), loaded.predict(features), atol=1e-12, rtol=0)
        metadata['turbines'][turbine] = dict(artifact=artifact.name, sha256=sha256(artifact),
            artifact_bytes=artifact.stat().st_size, training_rows=len(eligible),
            training_first_timestamp_source=str(eligible.timestamp.min()),
            training_last_timestamp_source=str(eligible.timestamp.max()),
            latest_training_hour_end_source=str(source_times.max() + pd.Timedelta(hours=1)),
            excluded_pre_cutoff_rows=invalid, excluded_at_or_after_cutoff_rows=outside,
            partial_hours_retained=int(eligible.observations_count.ne(6).sum()), source_sha256=sha256(path))
        print(f'{turbine}: rows={len(eligible)}, last_source={eligible.timestamp.max()}, timezone=unknown/unconfirmed', flush=True)
    assert hashes == {str(p): sha256(p) for p in protected}
    metadata['protected_files_verification'] = 'Existing models, reports and data SHA256 unchanged.'
    (MODEL_DIR / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
