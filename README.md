She Hacks — Agentic AI for Wind Power Forecasting

Track: Energy
Case provider: Samruk-Kazyna
Project status: In development

Project Overview

We are developing an automated system that predicts the hourly normalized power output of two wind turbines for the next 24–48 hours. The system will collect weather forecasts, generate predictions, update them when new weather data becomes available, and warn operators about expected sharp decreases in power output.

Team and Responsibilities

User 1 — Saule: Data and Machine Learning

Saule is responsible for checking and preparing the turbine datasets, converting 10-minute observations into hourly data, developing a baseline, training the forecasting model, and evaluating its performance. She also provides the model interface for integration into the system.

User 2 — Kamila: Weather Data and Automation

Kamila is responsible for verifying turbine coordinates, retrieving archived weather forecasts, checking weather data quality, and integrating the automated workflow. She also handles forecast versioning, operator alerts, and project documentation.

Both team members work together on data formats, integration, reproducibility checks, and the final demonstration.

How the System Will Work

The system retrieves a weather forecast available at the prediction issue time and checks its completeness, timestamps, and units. It then prepares the inputs for the trained model and generates hourly power predictions for each turbine. Predictions are saved with their weather source and model version. When a new weather forecast becomes available, the system updates the predictions.

Data and Evaluation

The provided datasets contain 10-minute observations from March 2023 through January 31, 2026, including wind speed, temperature, and normalized active power.

The required forecasting period is February 1–28, 2026. Historical predictions must use only information available at the time of each calculation, including archived weather forecasts.

Model performance will be compared with a baseline on a chronological holdout period. Actual February power values are not included in the provided datasets, so February accuracy can only be measured once those values become available.

Collaboration

Each team member works in a separate Git branch and makes meaningful commits and pushes at least once per hour, as required by the hackathon. Changes to shared data formats are agreed upon before integration. Installation instructions and verified execution commands will be added as the project develops.
