"""Absolute, per-turbine three-hour forecast drops (demonstration threshold)."""
from datetime import timedelta
from decimal import Decimal

from agent.weather_adapter import utc

FIELDS = ["turbine_id", "period_start_utc", "period_end_utc", "initial_power",
          "final_power", "power_drop", "threshold", "threshold_status"]


def analyze(rows, threshold=0.20):
    threshold = Decimal(str(threshold))
    if not threshold.is_finite() or not 0 < threshold <= 1:
        raise ValueError("Drop threshold must be finite and in (0, 1]")
    groups = {}
    for row in rows:
        # Never compare different issues or weather runs.
        key = (row["turbine_id"], row["issue_time_utc"], row["weather_run_time_utc"])
        groups.setdefault(key, {})[utc(row["target_time_utc"])] = row
    alerts, pairs = [], 0
    for key, timeline in sorted(groups.items()):
        for start, row in sorted(timeline.items()):
            end = start + timedelta(hours=3)
            if end not in timeline:
                continue  # Last three targets have no endpoint, not an extrapolated value.
            pairs += 1
            final = timeline[end]
            initial_value = Decimal(row["predicted_normalized_power"])
            final_value = Decimal(final["predicted_normalized_power"])
            drop = initial_value - final_value
            if drop >= threshold:
                alerts.append(dict(zip(FIELDS, [key[0], row["target_time_utc"], final["target_time_utc"],
                                               str(initial_value), str(final_value), str(drop), str(threshold),
                                               "demonstration_not_history_calibrated"])))
    return alerts, pairs
