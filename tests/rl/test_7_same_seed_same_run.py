"""The same seed gives the same run: initial weights, sampling and the updates.

Each case builds a run in a fresh process (five agents, seed 7), trains it for
``iterations`` and reports a fingerprint of every agent's weights. These things had
made the same seed give different runs:

- the modules were declared to RLlib as a set, so they were built, and drew their
  initial weights, in an order that changed with every process
  (``core/rl/config.py``: now a list in agent order);
- RLlib keeps agent ids in sets while sampling and batching, so Python's
  per-process hash seed still changes a multi-agent run: the runner's processes fix
  ``PYTHONHASHSEED`` (``core/runner/launch.py``).
"""

import json
import subprocess
import sys

import pytest

from core.runner import launch
from core.runner.spec import REPO

SCRIPT = """
import hashlib, json, sys
import ray
from core.rl.config import build_algo, build_config
from core.rl.envs.probes import ActionProbe
from core.rl.train import learner_modules

algorithm, paradigm, iterations = sys.argv[1], sys.argv[2], int(sys.argv[3])
small = {"train_batch_size_per_learner": 64, "minibatch_size": 32, "num_epochs": 1}
ray.init(num_cpus=1, include_dashboard=False, log_to_driver=False)
config = build_config(algorithm, paradigm, ActionProbe,
                      {"n_agents": 5, "scramble_ids": True}, seed=7, training=small)
algo = build_algo(config)
for _ in range(iterations):
    algo.train()
modules = learner_modules(algo)

def digest(module):
    h = hashlib.sha256()
    for name, tensor in sorted(module.state_dict().items()):
        h.update(name.encode())
        h.update(tensor.detach().cpu().numpy().tobytes())
    return h.hexdigest()[:16]

print(json.dumps({mid: digest(modules[mid]) for mid in sorted(modules.keys())}))
algo.stop()
ray.shutdown()
"""


def fingerprint(algorithm: str, paradigm: str, iterations: int, env: dict) -> dict:
    """Every agent's weights after ``iterations``, run in a process with ``env``."""
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT, algorithm, paradigm, str(iterations)],
        capture_output=True,
        text=True,
        env=env | {"OMP_NUM_THREADS": "1"},
        cwd=REPO,
        timeout=600,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("paradigm", ["dtde", "ctde"])
def test_initial_weights_do_not_depend_on_set_order(paradigm):
    """Two processes whose set order differs (``PYTHONHASHSEED`` 1 and 2) build the
    same five networks: each agent gets the same initial weights."""
    env = launch.job_environment()
    first = fingerprint("ppo", paradigm, 0, env | {"PYTHONHASHSEED": "1"})
    second = fingerprint("ppo", paradigm, 0, env | {"PYTHONHASHSEED": "2"})
    assert len(first) == 5
    assert first == second


@pytest.mark.parametrize("paradigm", ["dtde", "ctde", "ctce"])
def test_the_runners_processes_repeat_a_run(paradigm):
    """Two runs with the same seed, each in a process as the runner starts its jobs,
    end two training iterations with every agent's weights bit for bit the same."""
    env = launch.job_environment()
    first = fingerprint("ppo", paradigm, 2, env)
    second = fingerprint("ppo", paradigm, 2, env)
    assert len(first) == (1 if paradigm == "ctce" else 5)
    assert first == second
