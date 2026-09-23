#!/usr/bin/env python3
"""Run one full weather-to-power cycle; see agent.weather_pipeline."""
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep the adapter imports available to existing callers/tests.
from agent.weather_adapter import ROOT, adapt, read_csv, utc
from agent.weather_pipeline import main

if __name__ == "__main__":
    sys.exit(main())
