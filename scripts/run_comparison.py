"""Run the three-model comparison in the project Python environment."""
from pathlib import Path
import os
import runpy
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ.setdefault('MPLCONFIGDIR', str(root / '.venv' / 'matplotlib'))
runpy.run_module('training.compare_models', run_name='__main__')
