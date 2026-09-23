"""Refit approved CatBoost on all eligible history; never overwrite evaluation reports."""
from datetime import datetime, timezone
import json
import platform
import sys

import catboost
from catboost import CatBoostRegressor
import numpy as np
import pandas as pd

from training.eda_baseline import ROOT, PROCESSED, FEATURES as SOURCE_FEATURES, TARGET, END, prepare, sha256
from prediction.interface import FEATURES, ALIASES

PARAMETERS = dict(iterations=600, depth=6, learning_rate=0.05, loss_function='RMSE',
                  random_seed=42, thread_count=2, verbose=False, allow_writing_files=False)


def main():
    protected = list((ROOT / 'reports').rglob('*')) + list((ROOT / 'data').rglob('*.csv'))
    protected = [p for p in protected if p.is_file()]
    hashes = {str(p.relative_to(ROOT)): sha256(p) for p in protected}
    folder = ROOT / 'models'
    folder.mkdir(exist_ok=True)
    metadata = {
        'model_type': 'CatBoostRegressor', 'model_version': '1.0.0',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'training_end_date': '2026-01-31', 'training_cutoff_exclusive': str(END),
        'source_timestamp_timezone': 'Unspecified in source; no timezone conversion performed',
        'features': FEATURES, 'feature_units': {'wind_speed_ms': 'm/s', 'temperature_c': 'degrees Celsius'},
        'source_feature_mapping': dict(zip(FEATURES, SOURCE_FEATURES)),
        'target': {'name': 'predicted_normalized_power', 'source': TARGET,
                   'definition': 'Hourly mean of source normalized active power; dimensionless, not MW.'},
        'hyperparameters': PARAMETERS, 'output_range': [0, 1],
        'postprocessing': 'Clip finite model predictions to [0, 1] in the prediction interface.',
        'turbine_mapping': ALIASES,
        'eligibility': 'Finite power/wind/temperature means and valid timestamp before 2026-02-01; empty hours excluded; partial hours retained equally; zero power retained; no filling.',
        'evaluation_note': 'Refitted on all eligible history, including former validation rows. Existing comparison metrics describe earlier fits with measured weather, not these refits or 24-48h forecast accuracy.',
        'versions': {'python': platform.python_version(), 'catboost': catboost.__version__, 'pandas': pd.__version__, 'numpy': np.__version__},
        'python_executable': sys.executable, 'turbines': {},
    }
    for turbine in ('turbine_1', 'turbine_2'):
        source = PROCESSED / f'{turbine}_hourly.csv'
        eligible, excluded = prepare(pd.read_csv(source))
        assert len(eligible) and eligible.timestamp.max() < END
        features = eligible[SOURCE_FEATURES].rename(columns=dict(zip(SOURCE_FEATURES, FEATURES)))
        model = CatBoostRegressor(**PARAMETERS)
        model.fit(features, eligible[TARGET])
        path = folder / f'{turbine}_catboost.cbm'
        model.save_model(str(path), format='cbm')
        loaded = CatBoostRegressor()
        loaded.load_model(str(path))
        assert loaded.feature_names_ == FEATURES
        np.testing.assert_allclose(loaded.predict(features), model.predict(features), rtol=0, atol=1e-12)
        metadata['turbines'][turbine] = {
            'artifact': path.name, 'sha256': sha256(path), 'artifact_bytes': path.stat().st_size,
            'source': str(source.relative_to(ROOT)), 'source_sha256': sha256(source),
            'training_rows': len(eligible), 'training_start': str(eligible.timestamp.min()),
            'training_end': str(eligible.timestamp.max()), 'excluded_rows': len(excluded),
            'excluded_reasons': excluded.exclusion_reason.value_counts().to_dict(),
            'partial_hours_retained': int(eligible.observations_count.ne(6).sum()),
            'training_feature_ranges': {f: {'min': float(features[f].min()), 'max': float(features[f].max())} for f in FEATURES},
        }
        print(f'{turbine}: {len(eligible)} training rows; {path.stat().st_size} bytes', flush=True)
    assert hashes == {str(p.relative_to(ROOT)): sha256(p) for p in protected}
    metadata['verification'] = 'Saved/reloaded predictions match; raw/processed inputs and existing reports unchanged.'
    (folder / 'metadata.json').write_text(json.dumps(metadata, indent=2, allow_nan=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
