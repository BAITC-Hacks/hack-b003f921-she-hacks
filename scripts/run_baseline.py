"""Run the baseline or its checks using the active project Python environment."""
from pathlib import Path
import os
import runpy
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ.setdefault('MPLCONFIGDIR', str(root / '.venv' / 'matplotlib'))
if sys.argv[1:] == ['--test']:
    sys.argv = ['unittest', 'training.test_eda_baseline']
    runpy.run_module('unittest', run_name='__main__')
elif not sys.argv[1:]:
    runpy.run_module('training.eda_baseline', run_name='__main__')
else:
    raise SystemExit('Usage: python scripts/run_baseline.py [--test]')
