"""Evaluate supplied archival forecast predictions; never generate weather."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from prediction.interface import normalize_id
from training.eda_baseline import ROOT, TARGET, sha256
from backtest.train_january import CUTOFF, MODEL_DIR, select_training

SCHEMA = ['issue_time_utc', 'weather_run_time_utc', 'weather_available_time_utc',
          'target_time_utc', 'turbine_id', 'forecast_horizon_h', 'wind_speed_ms',
          'temperature_c', 'predicted_normalized_power', 'model_version', 'model_sha256']
AVAILABILITY_SCHEMA = ['turbine_id', 'target_time_utc', 'available_time_utc']


def require(frame, columns):
    if not frame.columns.is_unique or not set(columns).issubset(frame.columns):
        raise ValueError(f'Required unique columns: {columns}')


def utc(series):
    if not series.astype(str).str.contains(r'(?:Z|\+00:00)$', regex=True).all():
        raise ValueError('All timestamp fields require explicit UTC (Z or +00:00)')
    parsed = pd.to_datetime(series, format='ISO8601', utc=True, errors='raise')
    if parsed.isna().any():
        raise ValueError('Missing timestamp')
    return parsed


def source_to_utc(timestamps, zone):
    if not zone:
        raise ValueError('Explicit source timezone mapping is required; no UTC default')
    return timestamps.dt.tz_localize(zone, ambiguous='raise', nonexistent='raise').dt.tz_convert('UTC')


def evaluation_window(zone):
    bounds = source_to_utc(pd.Series([CUTOFF, pd.Timestamp('2026-02-01')]), zone)
    return bounds.iloc[0], bounds.iloc[1]


def load_actuals(directory, zone):
    frames = []
    for turbine in ('turbine_1', 'turbine_2'):
        frame = pd.read_csv(Path(directory) / f'{turbine}_hourly.csv')
        timestamp = pd.to_datetime(frame.timestamp, format='%Y-%m-%d %H:%M:%S', errors='raise')
        frame['target_time_source'] = timestamp  # Keep original clock values for audit.
        frame['target_time_utc'] = source_to_utc(timestamp, zone)
        frame['turbine_id'] = turbine
        frame['actual_power'] = pd.to_numeric(frame[TARGET], errors='coerce')
        frame.loc[frame.observations_count.eq(0), 'actual_power'] = np.nan
        frames.append(frame[['turbine_id', 'target_time_source', 'target_time_utc', 'actual_power']])
    result = pd.concat(frames, ignore_index=True)
    if result.duplicated(['turbine_id', 'target_time_utc']).any():
        raise ValueError('Duplicate actual hours')
    return result


def evaluate(forecasts, actuals, availability, metadata, *, source_timezone):
    cutoff_utc, end_utc = evaluation_window(source_timezone)
    require(forecasts, SCHEMA)
    require(availability, AVAILABILITY_SCHEMA)
    f = forecasts.copy().reset_index(drop=True)
    f['input_row_number'] = np.arange(len(f)) + 2
    f['turbine_id_original'] = f.turbine_id
    f['turbine_id'] = f.turbine_id.map(normalize_id)
    for column in ['issue_time_utc', 'weather_run_time_utc', 'weather_available_time_utc', 'target_time_utc']:
        f[column] = utc(f[column])
    if f.empty:
        raise ValueError('Forecast file is empty')
    if f.duplicated(['turbine_id', 'issue_time_utc', 'target_time_utc']).any():
        raise ValueError('Duplicate forecast case: turbine + issue + target; choose one run per case explicitly')
    for column in ['forecast_horizon_h', 'wind_speed_ms', 'temperature_c', 'predicted_normalized_power']:
        f[column] = pd.to_numeric(f[column], errors='raise')
        if not np.isfinite(f[column]).all():
            raise ValueError(f'Non-finite {column}')
    horizon = (f.target_time_utc - f.issue_time_utc).dt.total_seconds() / 3600
    if not (np.isclose(horizon, f.forecast_horizon_h).all() and horizon.between(1, 48).all() and (horizon % 1 == 0).all()):
        raise ValueError('Horizon must equal (target - issue) in integer hours 1..48')
    if not ((f.target_time_utc >= cutoff_utc) & (f.target_time_utc < end_utc)).all():
        raise ValueError('Only January 2026 targets in the configured source clock may be evaluated')
    local_targets = f.target_time_utc.dt.tz_convert(source_timezone).dt.tz_localize(None)
    if not (local_targets == local_targets.dt.floor('h')).all():
        raise ValueError('Target timestamps must correspond to source-clock hourly starts')
    if not (f.issue_time_utc >= cutoff_utc).all():
        raise ValueError('These static models are not available before the mapped source-clock cutoff')
    if not ((f.weather_run_time_utc <= f.weather_available_time_utc) & (f.weather_available_time_utc <= f.issue_time_utc)).all():
        raise ValueError('Weather run must be published by issue_time')
    if not f.predicted_normalized_power.between(0, 1).all() or f.wind_speed_ms.lt(0).any():
        raise ValueError('Power must be in [0,1], wind non-negative')
    if not f.model_version.eq(metadata['model_version']).all():
        raise ValueError('Wrong model version')
    for turbine, group in f.groupby('turbine_id'):
        if not group.model_sha256.eq(metadata['turbines'][turbine]['sha256']).all():
            raise ValueError('Prediction artifact hash does not match January model')
    a = availability.copy()
    a['turbine_id'] = a.turbine_id.map(normalize_id)
    a['target_time_utc'] = utc(a.target_time_utc)
    a['available_time_utc'] = utc(a.available_time_utc)
    if a.duplicated(['turbine_id', 'target_time_utc']).any():
        raise ValueError('Duplicate observation availability records; revisions must be resolved explicitly')
    if not (a.available_time_utc >= a.target_time_utc + pd.Timedelta(hours=1)).all():
        raise ValueError('Hourly power cannot be available before the hour ends')
    history = actuals.merge(a, on=['turbine_id', 'target_time_utc'], how='inner', validate='one_to_one')
    history = history.loc[np.isfinite(history.actual_power)].copy()
    f = f.merge(actuals, on=['turbine_id', 'target_time_utc'], how='left', validate='many_to_one', sort=False)
    cache = {}
    for turbine, issue in f[['turbine_id', 'issue_time_utc']].drop_duplicates().itertuples(index=False, name=None):
        available = history.loc[history.turbine_id.eq(turbine) & history.available_time_utc.le(issue)
                                & (history.target_time_utc + pd.Timedelta(hours=1)).le(issue)]
        if available.empty:
            cache[turbine, issue] = (np.nan, pd.NaT, pd.NaT, 'baseline_unavailable')
        else:
            row = available.sort_values('target_time_utc').iloc[-1]
            stale = issue - (row.target_time_utc + pd.Timedelta(hours=1)) > pd.Timedelta(hours=24)
            cache[turbine, issue] = (np.nan if stale else row.actual_power, row.target_time_utc,
                                     row.available_time_utc, 'baseline_stale' if stale else 'available')
    values = [cache[t, i] for t, i in f[['turbine_id', 'issue_time_utc']].itertuples(index=False, name=None)]
    f[['baseline_prediction', 'baseline_source_time_utc', 'baseline_available_time_utc', 'baseline_status']] = pd.DataFrame(values, index=f.index)
    f['actual_missing'] = ~np.isfinite(f.actual_power)
    f['evaluated'] = ~f.actual_missing & f.baseline_status.eq('available')
    f['horizon_band'] = np.where(f.forecast_horizon_h.le(24), '1-24', '25-48')
    records = []
    for turbine in ('turbine_1', 'turbine_2'):
        for band in ('1-24', '25-48'):
            group = f.loc[f.turbine_id.eq(turbine) & f.horizon_band.eq(band)]
            scored = group.loc[group.evaluated]
            record = dict(turbine_id=turbine, horizon_band=band, forecast_rows=len(group),
                unique_target_hours=int(group.target_time_utc.nunique()), evaluated_rows=len(scored),
                evaluated_unique_hours=int(scored.target_time_utc.nunique()),
                missing_actual_rows=int(group.actual_missing.sum()),
                missing_actual_unique_hours=int(group.loc[group.actual_missing, 'target_time_utc'].nunique()),
                baseline_unavailable_rows=int(group.baseline_status.eq('baseline_unavailable').sum()),
                baseline_stale_rows=int(group.baseline_status.eq('baseline_stale').sum()))
            for name, column in [('ml', 'predicted_normalized_power'), ('baseline', 'baseline_prediction')]:
                error = scored[column].astype(float) - scored.actual_power
                record[name + '_mae'] = float(error.abs().mean()) if len(scored) else None
                record[name + '_rmse'] = float(np.sqrt((error**2).mean())) if len(scored) else None
            records.append(record)
    return f.sort_values('input_row_number'), records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--forecasts', required=True)
    parser.add_argument('--availability', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--source-timezone', required=True, help='Explicit externally established source clock mapping; no default')
    parser.add_argument('--timezone-mapping-reference', required=True, help='Who confirmed the mapping and where it is documented')
    parser.add_argument('--real-archival-forecasts', action='store_true', help='Attest supplied weather is real archival forecast data, not measured weather or synthetic')
    args = parser.parse_args()
    if not args.real_archival_forecasts or not args.timezone_mapping_reference.strip():
        parser.error('Real archival forecast provenance and documented timezone mapping are required')
    cutoff_utc, end_utc = evaluation_window(args.source_timezone)
    metadata = json.loads((MODEL_DIR / 'metadata.json').read_text())
    availability = pd.read_csv(args.availability, dtype=str)
    # Require documentary publication times for ALL training records too.
    require(availability, AVAILABILITY_SCHEMA)
    manifest = availability.copy()
    manifest['turbine_id'] = manifest.turbine_id.map(normalize_id)
    manifest['target_time_utc'] = utc(manifest.target_time_utc)
    manifest['available_time_utc'] = utc(manifest.available_time_utc)
    for turbine in ('turbine_1', 'turbine_2'):
        artifact = MODEL_DIR / metadata['turbines'][turbine]['artifact']
        if sha256(artifact) != metadata['turbines'][turbine]['sha256']:
            raise ValueError('Model checksum mismatch')
        source_path = ROOT / f'data/processed/{turbine}_hourly.csv'
        if sha256(source_path) != metadata['turbines'][turbine]['source_sha256']:
            raise ValueError('Hourly data changed since January training')
        _, source_timestamps, _, _ = select_training(pd.read_csv(source_path))
        timestamps = source_to_utc(source_timestamps, args.source_timezone)
        joined = pd.DataFrame({'target_time_utc': timestamps}).merge(manifest.loc[manifest.turbine_id.eq(turbine)], on='target_time_utc', how='left', validate='one_to_one')
        if joined.available_time_utc.isna().any() or (joined.available_time_utc > cutoff_utc).any():
            raise ValueError('Training publication availability at cutoff is not verified; supply complete manifest or retrain with an earlier availability cutoff')
    forecast = pd.read_csv(args.forecasts, dtype=str)
    actuals = load_actuals(ROOT / 'data/processed', args.source_timezone)
    audit, metrics = evaluate(forecast, actuals, availability, metadata, source_timezone=args.source_timezone)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier evaluation.
    audit.to_csv(output / 'forecast_case_audit.csv', index=False)
    pd.DataFrame(metrics).to_csv(output / 'metrics.csv', index=False)
    (output / 'evaluation_metadata.json').write_text(json.dumps(dict(
        source_forecasts_sha256=sha256(Path(args.forecasts)), availability_sha256=sha256(Path(args.availability)),
        model_version=metadata['model_version'], training_source_timezone_status=metadata['source_timezone_status'],
        evaluation_source_timezone=args.source_timezone, timezone_mapping_reference=args.timezone_mapping_reference,
        evaluation_cutoff_utc=str(cutoff_utc), evaluation_end_exclusive_utc=str(end_utc),
        baseline_rule=metadata['baseline_rule'], case_weighting='Each issue/turbine/target is one case; no deduplication across issues',
        real_archival_forecasts_attested=True, training_publication_availability_verified=True), indent=2))
    print(f'Evaluation saved to {output}')


if __name__ == '__main__':
    main()
