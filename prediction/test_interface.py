import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from prediction.interface import TurbinePredictor, FEATURES, OUTPUT

ROOT = Path(__file__).resolve().parents[1]


class PredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictor = TurbinePredictor()
        cls.example = pd.read_csv(ROOT / 'examples/synthetic_weather_input.csv', dtype=str)

    def test_load_both_models(self):
        self.assertEqual(set(self.predictor.models), {'turbine_1', 'turbine_2'})
        for model in self.predictor.models.values():
            self.assertEqual(model.feature_names_, FEATURES)
            self.assertEqual(model.tree_count_, 600)

    def test_single_both_turbines_and_aliases(self):
        for turbine in (1, 2):
            result = self.predictor.predict(turbine, 7.5, 5)
            self.assertEqual(set(result), {OUTPUT})
            self.assertTrue(0 <= result[OUTPUT] <= 1)
            self.assertEqual(result, self.predictor.predict(f'turbine_{turbine}', '7.5', '5'))

    def test_batch_preserves_values_order_and_extra_columns(self):
        frame = self.example.copy()
        frame['integration_note'] = ['a', 'b', 'c', 'd']
        frame.index = [7, 7, 3, 1]  # Index labels need not be unique.
        before = frame.copy()
        result = self.predictor.predict_batch(frame)
        pd.testing.assert_frame_equal(frame, before)
        pd.testing.assert_frame_equal(result[frame.columns], frame)
        self.assertTrue(result[OUTPUT].between(0, 1).all())
        for _, row in result.iterrows():
            expected = self.predictor.predict(row.turbine_id, row.wind_speed_ms, row.temperature_c)
            self.assertAlmostEqual(row[OUTPUT], expected[OUTPUT], places=12)

    def test_clipping_both_boundaries(self):
        model = self.predictor.models['turbine_1']
        for raw, expected in [(-.2, 0.), (1.2, 1.)]:
            with patch.object(model, 'predict', return_value=np.array([raw])):
                self.assertEqual(self.predictor.predict(1, 5, 0)[OUTPUT], expected)

    def test_extreme_inputs_finite_range(self):
        for turbine in (1, 2):
            for wind, temp in [(0, -50), (100, 60), (7, 0)]:
                value = self.predictor.predict(turbine, wind, temp)[OUTPUT]
                self.assertTrue(np.isfinite(value) and 0 <= value <= 1)

    def test_invalid_id(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported turbine_id'):
            self.predictor.predict('turbine_3', 7, 5)
        frame = self.example.copy()
        frame.loc[0, 'turbine_id'] = '3'
        with self.assertRaisesRegex(ValueError, 'Unsupported turbine_id'):
            self.predictor.predict_batch(frame)

    def test_missing_columns(self):
        for column in self.example.columns:
            with self.subTest(column=column), self.assertRaisesRegex(ValueError, 'Missing required columns'):
                self.predictor.predict_batch(self.example.drop(columns=column))

    def test_invalid_numeric_values(self):
        for field in FEATURES:
            for bad in ['bad', '', np.nan, np.inf, -np.inf]:
                frame = self.example.copy()
                frame.loc[0, field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaisesRegex(ValueError, 'finite numeric'):
                    self.predictor.predict_batch(frame)
        with self.assertRaisesRegex(ValueError, 'non-negative'):
            self.predictor.predict(1, -1, 5)

    def test_duplicate_id_alias_and_timestamp_instant(self):
        frame = self.example.iloc[[0, 0]].copy().reset_index(drop=True)
        frame.loc[1, 'turbine_id'] = '1'
        frame.loc[1, 'target_time_utc'] = '2026-02-02T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError, 'Duplicate turbine_id'):
            self.predictor.predict_batch(frame)

    def test_utc_and_horizon_validation(self):
        for column, bad in [('target_time_utc', '2026-02-01'), ('issue_time_utc', 'badZ'),
                            ('forecast_horizon_h', '-1')]:
            frame = self.example.copy()
            frame.loc[0, column] = bad
            with self.assertRaises(ValueError):
                self.predictor.predict_batch(frame)

    def test_csv_roundtrip_and_failed_batch_no_write(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.venv') as directory:
            source, target = Path(directory) / 'input.csv', Path(directory) / 'output.csv'
            self.example.to_csv(source, index=False)
            self.predictor.predict_csv(source, target)
            loaded = pd.read_csv(target, dtype=str)
            pd.testing.assert_frame_equal(loaded[self.example.columns], self.example)
            original_bytes = target.read_bytes()
            self.example.drop(columns='temperature_c').to_csv(source, index=False)
            with self.assertRaises(ValueError):
                self.predictor.predict_csv(source, target)
            self.assertEqual(target.read_bytes(), original_bytes)
            with self.assertRaisesRegex(ValueError, 'must differ'):
                self.predictor.predict_csv(source, source)

    def test_cli(self):
        result = subprocess.run([sys.executable, '-m', 'prediction', 'single', '--turbine-id', '1',
                                 '--wind-speed-ms', '7.5', '--temperature-c', '5'], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        self.assertTrue(0 <= json.loads(result.stdout)[OUTPUT] <= 1)

    def test_empty_batch(self):
        result = self.predictor.predict_batch(self.example.iloc[:0])
        self.assertEqual(len(result), 0)
        self.assertIn(OUTPUT, result)


if __name__ == '__main__':
    unittest.main()
