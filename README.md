# hack-b003f921-she-hacks
Hackathon team repository for She hacks

## Wind power forecasting agent

Starter structure for developing a wind power forecasting agent in Python.

```text
data/
  raw/           Original weather and wind power observations
  processed/     Cleaned datasets and engineered features
training/        Model training and evaluation code
models/          Saved models and evaluation artifacts
agent/           Forecasting pipeline and orchestration code
```

### Development setup

Create a virtual environment with `python -m venv .venv` and activate it:

- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- macOS/Linux: `source .venv/bin/activate`

No third-party dependencies are required for this scaffold. Add dependencies
when implementing data processing, training, and forecasting.

### Intended workflow

1. Store original weather and power observations in `data/raw/`.
2. Clean observations and build features in `data/processed/`.
3. Implement training and evaluation in `training/`, saving outputs to `models/`.
4. Implement the agent pipeline in `agent/` to prepare new inputs, load a model,
   and produce wind power forecasts.

This scaffold contains no trained model or executable forecasting pipeline yet.
Datasets and generated model artifacts are excluded from Git by default.
