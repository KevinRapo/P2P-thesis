"""The runner: start, inspect, stop and sync local or Slurm experiments.

The one place that knows both ``core.env`` (the market as an environment) and
``core.rl`` (the training); both are imported only when a job trains, so reading
status stays fast. An experiment is a JSON file in ``config/experiments/``; everything
it produces is under ``runs/<experiment>/`` and survives closing the terminal,
the Studio or the Claude session.

    spec.py       ``Experiment``: the JSON file, validated, expanded to ``RunSpec``s
    launch.py     ``start`` (detached worker), ``prepare``, ``work``, ``job``, ``stop``
    slurm.py      the same runs as a SLURM job array (``slurm.start``, ``slurm.stop``,
                  ``slurm.states``); import it where it is used, it loads submitit
    registry.py   read-only view of ``runs/``: ``experiments``, ``runs``, ``RunState``
    targets.py    where an experiment runs (``hpc/targets.toml``): ``targets.get``
    remote.py     the cluster over SSH from another machine (``Remote``); import it
                  where it is used, it loads asyncssh
    __main__.py   ``python -m core.runner start | status | stop | sync | check``
"""

from core.runner import targets
from core.runner.launch import job, prepare, start, stop, work
from core.runner.registry import RunState, experiments, runs, summary
from core.runner.spec import Experiment, RunSpec, SpecError
from core.runner.targets import Target

__all__ = [
    "Experiment",
    "RunSpec",
    "RunState",
    "SpecError",
    "Target",
    "experiments",
    "job",
    "prepare",
    "runs",
    "start",
    "stop",
    "summary",
    "targets",
    "work",
]
