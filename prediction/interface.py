"""Validated, offline single and batch turbine inference."""
from pathlib import Path
import hashlib
import json

from catboost import CatBoostRegressor
import numpy as np
import pandas as pd

FEATURES = ['wind_speed_ms', 'temperature_c']
REQUIRED_COLUMNS = ['issue_time_utc', 'weather_run_time_utc', 'target_time_utc',
                    'turbine_id', 'forecast_horizon_h', *FEATURES]
OUTPUT = 'predicted_normalized_power'
DEFAULT_MODELS = Path(__file__).resolve().parents[1] / 'models'
ALIASES = {'1': 'turbine_1', '2': 'turbine_2',
           'turbine_1': 'turbine_1', 'turbine_2': 'turbine_2'}


def normalize_id(value):
    key = str(value).strip()
    if key not in ALIASES:
        raise ValueError(f'Unsupported turbine_id {value!r}; use turbine_1 or turbine_2 (aliases: 1, 2).')
    return ALIASES[key]


def numeric_features(frame):
    values = frame[FEATURES].apply(pd.to_numeric, errors='coerce')
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError('wind_speed_ms and temperature_c must be finite numeric values.')
    if values.wind_speed_ms.lt(0).any():
        raise ValueError('wind_speed_ms must be non-negative.')
    return values


class TurbinePredictor:
    """Load both CBM artifacts once and reuse for offline predictions."""

    def __init__(self, model_dir=DEFAULT_MODELS):
        self.model_dir = Path(model_dir)
        self.metadata = json.loads((self.model_dir / 'metadata.json').read_text(encoding='utf-8'))
        if self.metadata['features'] != FEATURES:
            raise ValueError('Model metadata feature schema does not match the interface.')
        self.models = {}
        for turbine in ('turbine_1', 'turbine_2'):
            entry = self.metadata['turbines'][turbine]
            path = self.model_dir / entry['artifact']
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError(f'Artifact checksum mismatch for {turbine}.')
            model = CatBoostRegressor()
            model.load_model(str(path))
            if model.feature_names_ != FEATURES:
                raise ValueError(f'Unexpected model feature order for {turbine}.')
            self.models[turbine] = model

    def _predict(self, turbine, features):
        predictions = np.asarray(self.models[turbine].predict(features), dtype=float)
        if not np.isfinite(predictions).all():
            raise ValueError('Model returned non-finite predictions.')
        return np.clip(predictions, 0.0, 1.0)

    def predict(self, turbine_id, wind_speed_ms, temperature_c):
        turbine = normalize_id(turbine_id)
        features = numeric_features(pd.DataFrame([[wind_speed_ms, temperature_c]], columns=FEATURES))
        return {OUTPUT: float(self._predict(turbine, features)[0])}

    def predict_batch(self, frame):
        """Preserve input rows, order, columns and values; append one prediction."""
        if not frame.columns.is_unique:
            raise ValueError('Duplicate input column names are not supported.')
        missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
        if missing:
            raise ValueError(f'Missing required columns: {", ".join(missing)}')
        if OUTPUT in frame.columns:
            raise ValueError(f'Input already contains {OUTPUT}; refusing to overwrite it.')
        output = frame.copy()
        ids = frame.turbine_id.map(normalize_id)
        features = numeric_features(frame)
        # Canonical UTC parsing catches duplicate instants with different spellings.
        times = {}
        for column in REQUIRED_COLUMNS[:3]:
            text = frame[column].astype(str)
            if not text.str.contains(r'(?:Z|\+00:00)$', regex=True).all():
                raise ValueError(f'{column} must be explicit UTC ISO-8601 (Z or +00:00).')
            times[column] = pd.to_datetime(text, utc=True, errors='coerce', format='ISO8601')
            if times[column].isna().any():
                raise ValueError(f'Invalid timestamp in {column}.')
        horizon = pd.to_numeric(frame.forecast_horizon_h, errors='coerce')
        if not np.isfinite(horizon).all() or horizon.lt(0).any():
            raise ValueError('forecast_horizon_h must be finite, numeric, and non-negative.')
        keys = pd.DataFrame({'turbine': ids.to_numpy(), 'target': times['target_time_utc'].to_numpy()})
        if keys.duplicated().any():
            raise ValueError('Duplicate turbine_id + target_time_utc rows (including ID aliases).')
        predicted = np.empty(len(frame), dtype=float)
        for turbine in self.models:
            positions = np.flatnonzero(ids.to_numpy() == turbine)
            if len(positions):
                predicted[positions] = self._predict(turbine, features.iloc[positions])
        output[OUTPUT] = predicted
        return output

    def predict_csv(self, input_path, output_path):
        source, target = Path(input_path), Path(output_path)
        if source.resolve() == target.resolve():
            raise ValueError('Input and output paths must differ.')
        # Reject duplicate headers before pandas can silently rename them.
        import csv
        with source.open(encoding='utf-8-sig', newline='') as stream:
            header = next(csv.reader(stream), [])
        if len(header) != len(set(header)):
            raise ValueError('Duplicate input column names are not supported.')
        frame = pd.read_csv(source, dtype=str, keep_default_na=False)
        output = self.predict_batch(frame)  # Validate the whole batch before writing.
        target.parent.mkdir(parents=True, exist_ok=True)
        output.to_csv(target, index=False)
        return output
