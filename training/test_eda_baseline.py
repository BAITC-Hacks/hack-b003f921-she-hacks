"""Boundary tests for leakage prevention and missing-hour policy."""
import unittest
import numpy as np
import pandas as pd
from training.eda_baseline import FEATURES, TARGET, prepare, evaluate


def row(timestamp, count=6, power=.4, wind=6., temperature=15.):
    return {'timestamp': timestamp, TARGET: power, FEATURES[0]: wind,
            FEATURES[1]: temperature, 'observations_count': count,
            'is_complete_hour': count == 6}


class PreparationTests(unittest.TestCase):
    def test_cutoff_split_and_missing_policy(self):
        source = pd.DataFrame([
            row('2025-07-31 23:00:00', count=3, power=0.),
            row('2025-08-01 00:00:00'),
            row('2026-01-31 23:00:00'),
            row('2026-02-01 00:00:00'),
            row('2025-06-01 00:00:00', count=0, power=np.nan, wind=np.nan, temperature=np.nan),
            row('2025-06-02 00:00:00', wind=np.inf),
            row('invalid'),
        ])
        eligible, excluded = prepare(source)
        self.assertEqual(eligible['split'].tolist(), ['train', 'validation', 'validation'])
        self.assertEqual(eligible[TARGET].iloc[0], 0.)
        self.assertEqual(eligible['observations_count'].iloc[0], 3)
        self.assertEqual(excluded['exclusion_reason'].value_counts().to_dict(), {
            'after_2026_01_31': 1, 'empty_hour': 1,
            'missing_or_nonfinite_required_value': 1, 'invalid_timestamp': 1})
        self.assertEqual(len(eligible) + len(excluded), len(source))

    def test_duplicates_and_inconsistent_counts_fail(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            prepare(pd.DataFrame([row('2025-01-01 00:00:00')] * 2))
        record = row('2025-01-01 00:00:00')
        record['is_complete_hour'] = False
        with self.assertRaisesRegex(ValueError, 'Completeness'):
            prepare(pd.DataFrame([record]))

    def test_gaps_not_filled_and_nonfinite_target_excluded(self):
        eligible, excluded = prepare(pd.DataFrame([
            row('2023-01-01 00:00:00'), row('2025-01-01 00:00:00'),
            row('2025-02-01 00:00:00', power=-np.inf)]))
        self.assertEqual(len(eligible), 2)
        self.assertEqual(len(excluded), 1)

    def test_known_metrics(self):
        values = evaluate([0., 1., 2.], [0., 1., 1.])
        self.assertAlmostEqual(values['mae'], 1/3)
        self.assertAlmostEqual(values['rmse'], np.sqrt(1/3))
        self.assertAlmostEqual(values['r2'], .5)


if __name__ == '__main__':
    unittest.main()
