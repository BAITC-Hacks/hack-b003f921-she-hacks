# Model training

Place feature preparation, training, and evaluation code here. Suggested modules
to add as the project develops:

- `features.py`: Shared feature transformations for training and inference.
- `train.py`: Fit models using datasets from `data/processed/`.
- `evaluate.py`: Evaluate forecasts on held-out chronological data.

Save trained models, preprocessing artifacts, and metrics in `models/`. Record
the feature schema, forecast horizon, data version, and training configuration
alongside each model so the agent can use it consistently.
