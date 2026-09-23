"""Render an offline February forecast demonstration without merging issues."""

import base64
from datetime import timezone
from html import escape
from io import BytesIO

from agent.weather_adapter import utc


DEMO_ISSUE = "2026-02-14T12:00:00Z"
ALERT_COLUMNS = [
    ("issue_time_utc", "Issue (UTC)"),
    ("weather_run_time_utc", "Weather run (UTC)"),
    ("turbine_id", "Turbine"),
    ("period_start_utc", "Start (UTC)"),
    ("period_end_utc", "End (UTC)"),
    ("initial_power", "Initial power"),
    ("final_power", "Final power"),
    ("power_drop", "Absolute drop"),
    ("threshold", "Threshold"),
    ("threshold_status", "Threshold status"),
]


def _text(value):
    return escape(str(value), quote=True)


def _count(value):
    return len(value) if isinstance(value, (list, tuple, set, dict)) else value


def _plot(rows, issue):
    # FigureCanvasAgg keeps rendering independent of a GUI or browser.
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
    from matplotlib.figure import Figure

    figure = Figure(figsize=(11, 6.5), layout="constrained", facecolor="white")
    FigureCanvasAgg(figure)
    axes = figure.subplots(2, 1, sharex=True, sharey=True)
    colors = ["#176b9f", "#b74d29"]
    for axis, turbine, color in zip(axes, ["turbine_1", "turbine_2"], colors):
        selected = sorted((row for row in rows if row["turbine_id"] == turbine),
                          key=lambda row: utc(row["target_time_utc"]))
        if selected:
            axis.plot([utc(row["target_time_utc"]) for row in selected],
                      [float(row["predicted_normalized_power"]) for row in selected],
                      color=color, linewidth=1.8, marker="o", markersize=2.8)
        else:
            axis.text(0.5, 0.5, "No valid forecast available", ha="center", va="center",
                      transform=axis.transAxes)
        axis.set_title(turbine.replace("_", " ").title(), loc="left", fontsize=11)
        axis.set_ylabel("Normalized power")
        axis.set_ylim(0, 1)
        axis.grid(alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
    locator = AutoDateLocator(minticks=5, maxticks=9, tz=timezone.utc)
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(ConciseDateFormatter(locator, tz=timezone.utc))
    axes[-1].set_xlabel("Target time (UTC); hourly forecasts at horizons 1-48 h")
    runs = sorted({row["weather_run_time_utc"] for row in rows})
    figure.suptitle("Real model forecasts for two turbines\n"
                    f"Issue: {issue or 'unavailable'} | Weather run: {', '.join(runs) or 'unavailable'}",
                    fontsize=12)
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=150,
                   metadata={"Software": "February forecast report"})
    return buffer.getvalue()


def render_report(forecasts: list[dict], alerts: list[dict], coverage: dict) -> dict[str, bytes]:
    """Return an exportable PNG and a self-contained HTML page as file bytes.

    The plot uses exactly one issue and weather run. Every alert remains in the
    HTML table, including alerts belonging to overlapping forecast issues.
    Times on the plot/table are UTC; month coverage uses source_timezone.
    """
    issues = sorted({row["issue_time_utc"] for row in forecasts}, key=utc)
    issue = next((value for value in issues if utc(value) == utc(DEMO_ISSUE)),
                 issues[0] if issues else None)
    selected = [row for row in forecasts if row["issue_time_utc"] == issue]
    if len({row["weather_run_time_utc"] for row in selected}) > 1:
        raise ValueError("Report demo issue contains multiple weather runs; select one version explicitly")
    keys = [(row["turbine_id"], utc(row["target_time_utc"])) for row in selected]
    if len(keys) != len(set(keys)):
        raise ValueError("Report demo issue contains duplicate turbine/target rows")
    png = _plot(selected, issue)
    encoded = base64.b64encode(png).decode("ascii")
    coverage_rows = "".join(
        "<tr>" + "".join(f"<td>{_text(value)}</td>" for value in (
            row["turbine_id"], row.get("expected_hours", 672),
            row.get("covered_hours", 0), _count(row.get("missing_hours", [])))) + "</tr>"
        for row in coverage.get("turbines", [])
    )
    alert_rows = "".join(
        f'<tr data-issue="{_text(row.get("issue_time_utc", ""))}">'
        + "".join(f"<td>{_text(row.get(key, ''))}</td>" for key, _ in ALERT_COLUMNS)
        + "</tr>"
        for row in sorted(alerts, key=lambda row: (
            row.get("issue_time_utc", ""), row.get("turbine_id", ""), row.get("period_start_utc", "")))
    )
    alert_headers = "".join(f"<th>{label}</th>" for _, label in ALERT_COLUMNS)
    alert_issues = sorted({row.get("issue_time_utc", "") for row in alerts})
    options = "".join(f'<option value="{_text(value)}">{_text(value)}</option>' for value in alert_issues)
    counts = {key: _count(coverage.get(key, 0)) for key in (
        "issues_requested", "issues_succeeded", "issues_failed", "full_forecast_rows", "february_forecast_rows")}
    threshold = coverage.get("alert_threshold", 0.20)
    wind_height = coverage.get("wind_height_m", 100)
    observation_delay = coverage.get("observation_delay_hours", 0)
    html = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>February wind power forecast report</title>
<style>
body {{ margin: 0 auto; max-width: 1150px; padding: 30px 22px; color: #20303c;
        background: #f9fbfc; font: 16px/1.55 system-ui, sans-serif; }}
h1, h2 {{ line-height: 1.2; }} h1 {{ margin-bottom: 8px; }}
section {{ margin-top: 28px; }} .note {{ padding: 14px 18px; background: #fff5df;
        border-left: 4px solid #ba871c; }}
img {{ width: 100%; height: auto; background: white; border: 1px solid #d7e1e7; }}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }}
th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #d7e1e7; }}
th {{ background: #e9f0f4; white-space: nowrap; }}
.scroll {{ overflow-x: auto; }} #alerts td {{ white-space: nowrap; font-size: 13px; }}
select, input {{ padding: 8px; max-width: 100%; margin: 5px 12px 5px 0; }}
a {{ color: #126197; }} code {{ overflow-wrap: anywhere; }}
</style></head>
<body>
<h1>February wind power forecast report</h1>
<p>Real predictions from ECMWF IFS archive weather and the saved CatBoost models.
This report demonstrates forecast generation and coverage. February forecast accuracy has not been evaluated.</p>
<p class="note"><strong>Provisional assumptions.</strong>
Archive provenance: <strong>unverified</strong>. Weather availability is assumed to be model
initialization + 12 hours; historical publication time is unconfirmed. Wind at
{_text(wind_height)} m is a technical input assumption, not a confirmed hub height.
The SCADA source clock mapping is assumed:
<code>{_text(coverage.get('source_timezone', 'Etc/GMT-5'))}</code>
(the default Etc/GMT-5 means UTC+05), with timestamps at interval start and observations
assumed available {_text(observation_delay)} hours after interval end. These time
assumptions also apply to model training eligibility. No observed power is plotted.</p>
<section><h2>February coverage</h2>
<p>Month boundaries: <code>{_text(coverage.get('month_start_utc', 'unknown'))}</code> inclusive
to <code>{_text(coverage.get('month_end_exclusive_utc', 'unknown'))}</code> exclusive.
Expected coverage: 672 unique hourly targets per turbine in the chosen source timezone.</p>
<p>Issues requested: <strong>{_text(counts['issues_requested'])}</strong>;
successful: <strong>{_text(counts['issues_succeeded'])}</strong>;
failed: <strong>{_text(counts['issues_failed'])}</strong>.
All forecast rows: <strong>{_text(counts['full_forecast_rows'])}</strong>;
targets inside February: <strong>{_text(counts['february_forecast_rows'])}</strong>.
Forecasts from different issues are retained separately, so row counts exceed unique-hour coverage.</p>
<table><thead><tr><th>Turbine</th><th>Expected hours</th><th>Covered hours</th><th>Missing hours</th></tr></thead>
<tbody>{coverage_rows}</tbody></table>
<p><a href="coverage.json">Coverage and assumptions (JSON)</a> ·
<a href="issues.csv">Per-issue outcomes (CSV)</a> ·
<a href="forecasts.csv">All forecast versions (CSV)</a></p></section>
<section><h2>One forecast issue, two turbines</h2>
<p>Shown issue: <code>{_text(issue or 'unavailable')}</code>. The two panels use only this
issue and preserve its 48 future hours; overlapping issues are not combined into a single curve.
Plot and alert timestamps are UTC.</p>
<img src="data:image/png;base64,{encoded}" alt="Two panels showing predicted normalized power for turbine 1 and turbine 2 from one forecast issue">
<p><a href="forecast.png">Download standalone plot (PNG)</a></p></section>
<section><h2>Three-hour power-drop warnings</h2>
<p>Within each turbine and issue, compare the forecast at a target hour with the forecast
three hours later. A warning means an absolute normalized-power drop of at least
<strong>{_text(threshold)}</strong> (0.20 means 20 percentage points, not a relative 20% drop).
The threshold is for demonstration and has not been calibrated on history. The final three
targets of an issue have no endpoint at +3 hours and are not extrapolated. All forecast
warnings are retained, including targets outside February and overlapping issues.</p>
<label for="issue-filter">Issue (UTC)</label>
<select id="issue-filter"><option value="">All issues</option>{options}</select>
<label for="alert-search">Search</label><input id="alert-search" type="search" placeholder="Turbine or time">
<p><span id="alert-count">{len(alerts)}</span> of {len(alerts)} warnings shown.
{'No warnings met the demonstration threshold.' if not alerts else ''}
<a href="alerts.csv">Download all warnings (CSV)</a>.</p>
<div class="scroll"><table id="alerts"><thead><tr>{alert_headers}</tr></thead>
<tbody>{alert_rows}</tbody></table></div></section>
<script>
const issueFilter = document.getElementById('issue-filter');
const search = document.getElementById('alert-search');
function filterAlerts() {{
  const needle = search.value.toLowerCase().trim();
  let count = 0;
  document.querySelectorAll('#alerts tbody tr').forEach(row => {{
    const visible = (!issueFilter.value || row.dataset.issue === issueFilter.value)
      && (!needle || row.textContent.toLowerCase().includes(needle));
    row.hidden = !visible;
    if (visible) count += 1;
  }});
  document.getElementById('alert-count').textContent = count;
}}
issueFilter.addEventListener('change', filterAlerts);
search.addEventListener('input', filterAlerts);
</script></body></html>
"""
    return {"forecast.png": png, "report.html": html.encode("utf-8")}
