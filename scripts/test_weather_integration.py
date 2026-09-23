"""Adapter boundary checks using saved weather; no downloads or retraining."""
import csv
import io
import json
import unittest

from scripts.run_weather_integration import ROOT, adapt, read_csv, utc


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "data/weather_examples/v1/weather_forecasts.csv").read_bytes()
        cls.models = json.loads((ROOT / "models/metadata.json").read_bytes())
        cls.issue = utc("2026-02-14T12:00:00Z")

    def changed(self, change):
        fields, rows = read_csv(self.source)
        selected = [r for r in rows if utc(r["issue_time_utc"]) == self.issue]
        change(selected)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
        return stream.getvalue().encode()

    def test_height_selection_and_preservation(self):
        for height in (10, 100, 200):
            _, _, rows = adapt(self.source, self.issue, height, self.models)
            self.assertEqual(len(rows), 96)
            for row in rows:
                self.assertEqual(row["wind_speed_ms"], row[f"wind_speed_{height}m_ms"])
                self.assertEqual(row["temperature_c"], row["temperature_2m_c"])
                self.assertEqual(row["weather_provenance_status"], "unverified")

    def test_january_refit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "as-of-trained"):
            adapt(self.source, utc("2026-01-31T12:00:00Z"), 100, self.models)

    def test_incorrect_horizon_is_rejected(self):
        data = self.changed(lambda rows: rows[0].update(forecast_horizon_h="2"))
        with self.assertRaisesRegex(ValueError, "horizon"):
            adapt(data, self.issue, 100, self.models)

    def test_duplicate_alias_is_rejected(self):
        def duplicate(rows):
            rows.append(dict(rows[0], turbine_id="1"))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            adapt(self.changed(duplicate), self.issue, 100, self.models)

    def test_missing_hour_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "96 rows"):
            adapt(self.changed(lambda rows: rows.pop()), self.issue, 100, self.models)

    def test_nonfinite_weather_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            adapt(self.changed(lambda rows: rows[0].update(wind_speed_100m_ms="nan")),
                  self.issue, 100, self.models)


if __name__ == "__main__":
    unittest.main()
