"""Synthetic SOFTWARE tests only. Values and errors are not model performance."""
import json
import unittest

import numpy as np
import pandas as pd

from backtest.train_january import select_training, CUTOFF, MODEL_DIR
from backtest.evaluate_january import evaluate as evaluate_cases, source_to_utc, evaluation_window
from prediction.interface import TurbinePredictor
from training.eda_baseline import TARGET, FEATURES as SOURCE_FEATURES


def evaluate(forecasts, actuals, availability, metadata):
    # UTC belongs ONLY to this invented test fixture, never to real source data.
    return evaluate_cases(forecasts, actuals, availability, metadata, source_timezone='UTC')


class JanuaryTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {'model_version': 'SYNTHETIC_TEST_ONLY', 'turbines': {
            'turbine_1': {'sha256': 'SYNTHETIC_TEST_ONLY'}, 'turbine_2': {'sha256': 'SYNTHETIC_TEST_ONLY'}}}
        self.forecast = pd.read_csv(MODEL_DIR.parents[1] / 'backtest/fixtures/synthetic_forecasts.csv', dtype=str)
        self.actuals = pd.DataFrame({
            'turbine_id': ['turbine_1'] * 4,
            'target_time_utc': pd.to_datetime(['2025-12-31T22:00:00Z', '2025-12-31T23:00:00Z', '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z']),
            'actual_power': [.2, .9, .5, np.nan]})
        self.availability = pd.DataFrame({
            'turbine_id': ['turbine_1', 'turbine_1'],
            'target_time_utc': ['2025-12-31T22:00:00Z', '2025-12-31T23:00:00Z'],
            'available_time_utc': ['2025-12-31T23:00:00Z', '2026-01-01T02:00:00Z']})

    def test_issue_cases_preserved_and_paired(self):
        audit, metrics = evaluate(self.forecast, self.actuals, self.availability, self.metadata)
        self.assertEqual(len(audit), 3)
        self.assertEqual(audit.issue_time_utc.nunique(), 2)
        self.assertEqual(audit.baseline_prediction.tolist(), [.2, .2, .2])
        record = metrics[0]
        self.assertEqual(record['evaluated_rows'], 2)
        self.assertEqual(record['evaluated_unique_hours'], 1)
        self.assertAlmostEqual(record['ml_mae'], .1)
        self.assertAlmostEqual(record['baseline_mae'], .3)
        self.assertEqual(metrics[1]['missing_actual_rows'], 1)
        self.assertIsNone(metrics[1]['ml_rmse'])

    def test_missing_baseline_excludes_both_models(self):
        self.availability.available_time_utc = '2026-01-02T00:00:00Z'
        audit, metrics = evaluate(self.forecast, self.actuals, self.availability, self.metadata)
        self.assertFalse(audit.evaluated.any())
        self.assertIsNone(metrics[0]['ml_mae'])
        self.assertIsNone(metrics[0]['baseline_mae'])

    def test_stale_baseline_excluded(self):
        self.actuals.loc[:1, 'target_time_utc'] -= pd.Timedelta(days=2)
        self.availability.target_time_utc = ['2025-12-29T22:00:00Z', '2025-12-29T23:00:00Z']
        self.availability.available_time_utc = ['2025-12-29T23:00:00Z', '2025-12-30T00:00:00Z']
        audit, _ = evaluate(self.forecast, self.actuals, self.availability, self.metadata)
        self.assertTrue(audit.baseline_status.eq('baseline_stale').all())

    def test_duplicate_same_issue_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate forecast case'):
            evaluate(pd.concat([self.forecast, self.forecast.iloc[:1]]), self.actuals, self.availability, self.metadata)

    def test_invalid_forecasts_rejected(self):
        for column, value in [('forecast_horizon_h', '25'), ('model_sha256', 'wrong'),
                              ('weather_available_time_utc', '2026-01-02T00:00:00Z'),
                              ('predicted_normalized_power', '1.5'), ('turbine_id', '3')]:
            f = self.forecast.copy()
            f.loc[0, column] = value
            with self.subTest(column=column), self.assertRaises(ValueError):
                evaluate(f, self.actuals, self.availability, self.metadata)
        with self.assertRaises(ValueError):
            evaluate(self.forecast.drop(columns='issue_time_utc'), self.actuals, self.availability, self.metadata)

    def test_availability_before_hour_end_rejected(self):
        self.availability.loc[0, 'available_time_utc'] = '2025-12-31T22:30:00Z'
        with self.assertRaisesRegex(ValueError, 'before the hour ends'):
            evaluate(self.forecast, self.actuals, self.availability, self.metadata)

    def test_no_january_training_and_no_timestamp_shift(self):
        source = pd.DataFrame({'timestamp': ['2025-12-31 23:00:00', '2026-01-01 00:00:00'],
                               TARGET: [.3, 999], SOURCE_FEATURES[0]: [5, 999],
                               SOURCE_FEATURES[1]: [2, 999], 'observations_count': [6, 6],
                               'is_complete_hour': [True, True]})
        chosen, timestamps, _, _ = select_training(source)
        self.assertEqual(len(chosen), 1)
        self.assertIsNone(timestamps.dt.tz)
        self.assertEqual(timestamps.iloc[0], pd.Timestamp('2025-12-31 23:00:00'))
        self.assertLess(timestamps.max(), CUTOFF)
        source.loc[1, TARGET] = -999
        chosen2, _, _, _ = select_training(source)
        pd.testing.assert_frame_equal(chosen, chosen2)

    def test_evaluator_mapping_is_explicit_and_does_not_mutate_source(self):
        original = pd.Series(pd.to_datetime(['2025-12-31 23:00:00']))
        before = original.copy()
        with self.assertRaisesRegex(ValueError, 'Explicit source timezone'):
            source_to_utc(original, None)
        mapped = source_to_utc(original, 'Etc/GMT-5')  # Synthetic UTC+5 example only.
        self.assertEqual(mapped.iloc[0], pd.Timestamp('2025-12-31 18:00:00Z'))
        pd.testing.assert_series_equal(original, before)
        start, end = evaluation_window('Etc/GMT-5')
        self.assertEqual(start, pd.Timestamp('2025-12-31 19:00:00Z'))
        self.assertEqual(end, pd.Timestamp('2026-01-31 19:00:00Z'))
        with self.assertRaises(TypeError):
            evaluate_cases(self.forecast, self.actuals, self.availability, self.metadata)

    def test_saved_models_pre_january(self):
        metadata = json.loads((MODEL_DIR / 'metadata.json').read_text())
        self.assertFalse(metadata['source_timezone_confirmed'])
        self.assertIsNone(metadata['source_timezone'])
        self.assertEqual(metadata['source_timezone_status'], 'unknown/unconfirmed')
        predictor = TurbinePredictor(MODEL_DIR)
        for turbine in ('turbine_1', 'turbine_2'):
            last = pd.Timestamp(metadata['turbines'][turbine]['training_last_timestamp_source'])
            self.assertIsNone(last.tz)
            self.assertLess(last, CUTOFF)
            self.assertNotIn('training_last_timestamp_utc', metadata['turbines'][turbine])
            self.assertTrue(0 <= predictor.predict(turbine, 7, 5)['predicted_normalized_power'] <= 1)


if __name__ == '__main__':
    unittest.main()
