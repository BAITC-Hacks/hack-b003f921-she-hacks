# Turbine data preparation

From the repository root, run with Windows PowerShell 5.1 or later:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_hourly.ps1
```

No third-party dependencies are required. The script accepts either
`data/raw/turbine 1.csv` and `turbine 2.csv` (the inspected filenames), or
their underscore equivalents. It fails if both alternatives exist for a turbine.
The script is UTF-8 with BOM so Windows PowerShell can read the Russian headers.

Outputs in `data/processed/`:

- `turbine_1_hourly.csv`
- `turbine_2_hourly.csv`
- `data_quality_report.json`: source hashes, actual headers and mapping, raw
  statistics, missing/invalid counts, duplicate counts, interval distribution,
  every gap, zero-power counts, and hourly counts.

Hours are left-closed calendar bins: a timestamp at 01:00 belongs to 01:00.
Timestamps contain no timezone, so their original clock values are preserved;
no timezone is inferred. Output covers every hour from the minimum to maximum
valid timestamp. Empty hours have blank means and zero observations. There is
no interpolation, imputation, clipping, or removal of zero-power observations.

Each mean uses the available finite numeric values of that measurement.
`observations_count` counts rows with valid timestamps, including duplicate
timestamps and rows with missing measurements. `is_complete_hour` is exactly
`observations_count == 6`, as requested; it does not certify six unique sampling
times or complete measurements. Duplicate timestamps are reported, not silently
deduplicated. Invalid timestamps cannot be placed in hours and are reported.
Blank cells and NA/N/A/NaN/null/None tokens are classified as missing; other
unparseable or infinite measurements are reported as invalid numeric values.
Raw numeric statistics include all valid measurements, even if their row has an
invalid timestamp. Zero-power percentages use all source rows as denominator.

The interval distribution uses sorted valid timestamps, including zero-length
intervals for duplicates. A gap is an interval greater than the expected ten
minutes. Missing-slot estimates count ten-minute steps strictly between its
endpoints. Out-of-order transitions and off-grid observations are also reported.
"Non-zero wind" means measured wind != 0; "high wind" means >= 5 m/s by default.
This is a descriptive threshold, not a turbine operating limit. Override with
`-HighWindThreshold 6` if needed.

Each run verifies exported counts, observation conservation, completeness flags,
and unchanged raw-file SHA256 hashes. It overwrites only these generated outputs.
Hourly averages become available after the hour ends; no forecasting features or
models are created here.
