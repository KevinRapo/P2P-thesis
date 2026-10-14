"""The runner: start training experiments and watch them, from files only.

The one place that knows both ``core.env`` (the market as an environment) and
``core.rl`` (the training); both are imported only when a job trains, so reading
status stays fast. An experiment is a JSON file in ``experiments/``; everything
it produces is under ``runs/<experiment>/`` and survives closing the terminal,
the Studio or the Claude session.

    spec.py       ``Experiment``: the JSON file, validated, expanded to ``RunSpec``s
    launch.py     ``start`` (detached worker), ``work``, ``job``, ``stop``
    registry.py   read-only view of ``runs/``: ``experiments``, ``runs``, ``RunState``
    __main__.py   ``python -m core.runner start | status | stop``
"""

from core.runner.launch import job, start, stop, work
from core.runner.registry import RunState, experiments, runs, summary
from core.runner.spec import Experiment, RunSpec, SpecError

__all__ = [
    "Experiment",
    "RunSpec",
    "RunState",
    "SpecError",
    "experiments",
    "job",
    "runs",
    "start",
    "stop",
    "summary",
    "work",
]
