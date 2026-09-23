# Agent pipeline

Place forecast orchestration code here. The intended pipeline is:

1. Ingest recent weather and turbine or site observations.
2. Validate timestamps, required fields, and measurement units.
3. Apply the same feature transformations used during training.
4. Load a trained model and preprocessing artifacts from `models/`.
5. Generate forecasts with timestamps, site identifiers, and power units.

Suggested modules to add are `ingest.py`, `predict.py`, and `pipeline.py`.
Keep model fitting in `training/` so forecasts can run without retraining.
