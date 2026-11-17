"""The held-out evaluation of an experiment's runs at a shorter budget (RP-7c).

Every run of ``runs/<experiment>`` whose ``checkpoints/<steps>`` exists plays the
held-out days with that policy (``launch.heldout_at``), into
``runs/<experiment>_at<steps>/<run>``, which the results read as an experiment of its own.
Runs in parallel processes; meant for the cluster, where the checkpoints are.

    python analysis/heldout_at.py <experiment> <steps> [processes] [runs ...]
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONHASHSEED", "0")

from core.runner.launch import heldout_at  # noqa: E402
from core.runner.spec import runs_root  # noqa: E402


def one(args: tuple) -> str:
    run_dir, steps, dest = args

    try:
        heldout_at(run_dir, steps, dest)
    except Exception as error:  # report and go on with the others
        return f"{run_dir.name}: FAILED {error!r}"

    return f"{run_dir.name}: done"


if __name__ == "__main__":
    experiment, steps = sys.argv[1], int(sys.argv[2])
    processes = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    only = set(sys.argv[4:])
    source = runs_root() / experiment
    target = runs_root() / f"{experiment}_at{steps}"
    work = [
        (run, steps, target / run.name)
        for run in sorted(source.iterdir())
        if (run / "checkpoints" / str(steps)).is_dir() and (not only or run.name in only)
    ]
    print(f"{len(work)} runs of {experiment} at {steps} steps -> {target}", flush=True)

    with ProcessPoolExecutor(processes) as pool:
        for line in pool.map(one, work):
            print(line, flush=True)
