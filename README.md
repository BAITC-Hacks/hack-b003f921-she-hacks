# hack-b003f921-she-hacks
Hackathon team repository for She hacks
Our topic is 
```md
# She Hacks — Agentic AI for Wind Power Forecasting

**Track:** Energy  
**Case provider:** Samruk-Kazyna  
**Status:** In development

## Project Overview

We are developing an automated system to forecast the hourly normalized power output of two wind turbines over the next 24–48 hours.

The system will retrieve weather forecasts, prepare model inputs, generate power predictions, and update the results when new weather forecasts become available. It will also alert operators to expected sharp decreases in power output.

## Team and Responsibilities

| Member | Role | Responsibilities |
|---|---|---|
| User 1 — Saule | Data and Machine Learning | Data quality checks, hourly aggregation, baseline development, model training, historical evaluation, and the prediction interface |
| User 2 — Kamila | Weather Data and Automation | Turbine coordinates, archived weather forecasts, weather data validation, pipeline integration, forecast versioning, alerts, and documentation |

Shared responsibilities include agreeing on data formats, integrating components, checking reproducibility, and preparing the final demonstration.

## Planned Workflow

1. Retrieve a weather forecast available at the prediction issue time.
2. Validate its timestamps, units, coverage, and completeness.
3. Prepare features and pass them to the trained model.
4. Predict hourly normalized power for each turbine over 24–48 hours.
5. Save predictions with weather source information and the model version.
6. Identify expected sharp changes in power output.
7. Recalculate predictions when a new weather forecast becomes available.

## Data

The provided datasets contain 10-minute observations for two turbines from March 2023 through January 31, 2026.

Available variables include:

- Observation timestamp
- Average wind speed
- Normalized active power
- Average ambient temperature

Observations will be aggregated into hourly records, with the number of measurements per hour retained to identify incomplete periods.

Predictions are expressed as normalized power values between **0 and 1**. Conversion to MW requires confirmed turbine capacities and the normalization method.

## Historical Forecasting and Evaluation

The required forecast period is **February 1–28, 2026**.

Each historical prediction must use only information available at its issue time. Archived weather forecasts must be used instead of future observed weather or reanalysis.

Model performance will be evaluated on a chronological holdout period and compared with a baseline. Results will be reported separately for each turbine and forecast horizon.

The provided datasets do not contain actual February power values. February accuracy metrics can therefore only be calculated after those observations become available.

## Collaboration

- Saule develops the data preparation and modeling components.
- Kamila develops the weather and automation components in `user2-weather-pipeline`.
- Both members make meaningful commits and push updates at least once per hour, as required by the hackathon.
- Changes to shared input and output formats are agreed upon before integration.
- The complete workflow is checked before changes are merged.

## Roadmap

- [ ] Inspect the turbine datasets and identify data quality issues
- [ ] Verify access to suitable archived weather forecasts
- [ ] Agree on the model input and output formats
- [ ] Prepare hourly turbine data
- [ ] Implement a baseline and the main forecasting model
- [ ] Evaluate performance using historical forecast runs
- [ ] Integrate the automated forecasting workflow
- [ ] Generate the February forecasts
- [ ] Add operator alerts for sharp power decreases
- [ ] Document installation and reproducible execution

## Setup and Execution

Verified installation instructions, dependencies, and execution commands will be added after the first complete workflow is implemented.
```
