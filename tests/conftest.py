"""Make the source checkout importable in tests and notebook subprocesses."""
import sys
import os
from pathlib import Path

os.environ.setdefault('MPLBACKEND', 'Agg')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest


@pytest.fixture(scope='session')
def trained_case(request):
    """Build a real short PPO checkpoint once per requested learning mode."""
    from scripts.validate_learning import config, run
    evidence = run('ppo', request.param, iterations=2, batch=32)
    return config(), evidence
