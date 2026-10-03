"""From the ``learning`` section to an RLlib configuration (05 §3.8).

Replaces the hard-coded blocks of ``marl/train.py`` (``RLTrainer``): algorithm
hyperparameters, paradigm module, tuning, rollouts, checkpoints and evaluation
all come from the resolved file (02 §3.8–3.9).

Status: interface only; implemented with the RL stage (validation stage D)
after the environment is validated. Ray is imported inside the functions.
"""

from __future__ import annotations

from typing import Any

from src_thesis.experiments.models.records import ExperimentFile, RunCell


def build_algorithm_config(resolved: ExperimentFile, cell: RunCell) -> Any:
    """An RLlib ``AlgorithmConfig`` for ``cell.algorithm`` × ``cell.paradigm``.

    Environment: registered with ``factory.environment.build_env`` and ``factory.build_env_config``.
    Checked: mutation domains contain the initial values (I-49); the budget
    unit is the same for every cell (I-50).
    """
    raise NotImplementedError("RL configuration is built in validation stage D")


def build_tuner_settings(resolved: ExperimentFile) -> dict[str, Any]:
    """Tune settings: scheduler (``none`` or PBT), stop criterion, checkpoints."""
    raise NotImplementedError("RL configuration is built in validation stage D")
