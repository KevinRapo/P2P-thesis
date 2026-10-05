"""From the ``learning`` section to the arguments of MARLEM's trainer.

Why: the original hard-coded the PPO, APPO and SAC settings in ``marl/train.py`` and
always switched PBT on (I-62). Taking the run's settings from the file's
``learning`` section makes every hyperparameter visible, editable, stored in
``resolved.json`` and equal across cells when it should be (I-49, I-50).

This module only translates (decision D-16): the experiment file and one run
cell become the arguments of ``marl.train.RLTrainer``, with the local energy
market as its environment. The RL testbench calls the same ``RLTrainer`` with
external environments, so the code that trains the market is the code that was
shown to learn there.

Status: interface only; implemented with the RL stage (validation stage D)
after the environment is validated.
"""

from __future__ import annotations

from typing import Any

from src_thesis.platform.experiments.models.records import ExperimentFile, RunCell


def trainer_arguments(resolved: ExperimentFile, cell: RunCell) -> dict[str, Any]:
    """Keyword arguments of ``RLTrainer`` for one run: the market's
    ``env_config`` (from ``factory.environment``), ``cell.algorithm`` ×
    ``cell.paradigm``, the budget, checkpoint and evaluation settings.

    Checked: mutation domains contain the initial values (I-49); the budget
    unit is the same for every cell (I-50).
    """
    raise NotImplementedError("Trainer arguments are built in validation stage D")
