"""CLI: python -m prediction single|batch."""
import argparse
import json
from .interface import DEFAULT_MODELS, TurbinePredictor


def main():
    parser = argparse.ArgumentParser(description='Offline turbine power prediction; no weather fetching or training.')
    parser.add_argument('--model-dir', default=str(DEFAULT_MODELS))
    commands = parser.add_subparsers(dest='command', required=True)
    single = commands.add_parser('single')
    single.add_argument('--turbine-id', required=True)
    single.add_argument('--wind-speed-ms', required=True, type=float)
    single.add_argument('--temperature-c', required=True, type=float)
    batch = commands.add_parser('batch')
    batch.add_argument('--input', required=True)
    batch.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        predictor = TurbinePredictor(args.model_dir)
        if args.command == 'single':
            print(json.dumps(predictor.predict(args.turbine_id, args.wind_speed_ms, args.temperature_c)))
        else:
            result = predictor.predict_csv(args.input, args.output)
            print(json.dumps({'rows': len(result), 'output': args.output}))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f'Prediction error: {exc}\n')


if __name__ == '__main__':
    main()
