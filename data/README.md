# Data

- `raw/`: Original weather measurements, forecasts, and historical wind power output.
- `processed/`: Cleaned observations, engineered features, and training splits.

Keep raw inputs unchanged so preprocessing can be reproduced. Document data
sources, timestamp time zones, measurement units, and turbine or site identifiers
when adding a dataset. Split time series chronologically to avoid using future
observations during training.

Dataset contents are ignored by Git; the directory placeholders are tracked.
