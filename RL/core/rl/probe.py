"""Query a trained algorithm in given states and compare it with a probe's checks.

Not part of the original code. Reads the learner's RL modules directly (not the
samplers' copies, which leave out the value function), so it shows what training
produced, network by network:

- DTDE: one module per agent; its value and action mean for the agent's own
  observation.
- CTCE and CTDE: one module for the group. It sees every agent's observation, in
  the environment's agent order (as RLlib's grouping sends them); its value is
  the group's (the sum of the agents' rewards), its action output is cut into
  one ``[mean, log_std]`` block per agent, in the same order.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from ray.rllib.algorithms.algorithm import Algorithm
from ray.rllib.core.columns import Columns

from RL.core.envs.probes import Check
from RL.core.rl.base import TrainingMode
from RL.core.rl.train import RLTrainer

GROUP = "grouped_agents"


def query(
    algo: Algorithm, trainer: RLTrainer, obs: dict[str, np.ndarray]
) -> tuple[dict[str, float], dict[str, float], float | None]:
    """The learner's outputs in one state.

    Args:
        algo: A built (and trained) algorithm, e.g. from ``build_local``.
        trainer: The trainer it was built from.
        obs: Each agent's observation.

    Returns:
        Each agent's action mean, each agent's value (DTDE; empty otherwise),
        and the group's value (CTCE and CTDE; ``None`` for DTDE).
    """
    modules = algo.learner_group._learner.module
    actions, values = {}, {}
    with torch.no_grad():
        if trainer.training == TrainingMode.DTDE:
            for agent, o in obs.items():
                module = modules[agent]
                batch = {Columns.OBS: torch.as_tensor(o).reshape(1, -1)}
                inputs = module.forward_inference(batch)[Columns.ACTION_DIST_INPUTS][0]
                actions[agent] = float(inputs[0])
                values[agent] = float(module.compute_values(batch)[0])
            return actions, values, None
        module = modules["default_policy"]
        order = trainer.env.original_agents_id
        batch = {
            Columns.OBS: {
                GROUP: tuple(torch.as_tensor(obs[a]).reshape(1, -1) for a in order)
            }
        }
        inputs = module.forward_inference(batch)[Columns.ACTION_DIST_INPUTS][0]
        start = 0
        for agent in order:
            dim = obs[agent].shape[-1]  # probes: action dim = observation dim
            actions[agent] = float(inputs[start])
            start += 2 * dim
        group_value = float(module.compute_values(batch)[0])
    return actions, values, group_value


def mean_actions(
    algo: Algorithm, trainer: RLTrainer, obs: dict[str, np.ndarray]
) -> dict[str, np.ndarray]:
    """The learner's deterministic action for every agent, as the environment
    receives it: the mean of the action distribution, mapped from the network's
    scale to the action space the way RLlib does for sampled actions: ``[-1, 1]``
    to ``[low, high]``, then clipped. RLlib's own SAC module (DTDE) squashes with
    ``tanh`` first; the custom CTCE and CTDE modules use a plain Gaussian for every
    algorithm, so their mean is not squashed. Same modules and agent order as
    ``query``.

    Args:
        algo: A built (and trained) algorithm, e.g. from ``build_local``.
        trainer: The trainer it was built from.
        obs: Each agent's observation.
    """
    modules = algo.learner_group._learner.module
    spaces = trainer.env_class(trainer.env_config).action_spaces
    squash = trainer.algorithm.value == "sac" and trainer.training == TrainingMode.DTDE
    with torch.no_grad():
        if trainer.training == TrainingMode.DTDE:
            order = list(obs)
            means = {}
            for agent in order:
                batch = {Columns.OBS: torch.as_tensor(obs[agent]).reshape(1, -1)}
                inputs = modules[agent].forward_inference(batch)
                inputs = inputs[Columns.ACTION_DIST_INPUTS][0]
                means[agent] = inputs[: spaces[agent].shape[0]].numpy()
        else:
            order = trainer.env.original_agents_id
            batch = {
                Columns.OBS: {
                    GROUP: tuple(torch.as_tensor(obs[a]).reshape(1, -1) for a in order)
                }
            }
            inputs = modules["default_policy"].forward_inference(batch)
            inputs = inputs[Columns.ACTION_DIST_INPUTS][0]
            means, start = {}, 0
            for agent in order:
                dim = spaces[agent].shape[0]
                means[agent] = inputs[start : start + dim].numpy()
                start += 2 * dim
    actions = {}
    for agent, mean in means.items():
        space = spaces[agent]
        unit = np.tanh(mean) if squash else np.clip(mean, -1.0, 1.0)
        actions[agent] = np.clip(
            space.low + (unit + 1.0) / 2.0 * (space.high - space.low),
            space.low,
            space.high,
        ).astype(np.float32)
    return actions


def evaluate(
    algo: Algorithm,
    trainer: RLTrainer,
    checks: list[Check],
    tolerance: float = 0.15,
) -> pd.DataFrame:
    """Compare the learner's outputs with a probe's checks.

    Values of the grouped paradigms are compared with the sum of the agents'
    expected values. A row passes when the error is at most ``tolerance`` (for
    values: times the size of the expected value, at least 1).

    Returns:
        One row per checked output: ``state``, ``output`` (e.g. ``value
        agent_00``, ``value group``, ``action agent_01``), ``expected``, ``got``,
        ``error`` and ``ok``.
    """
    rows = []
    for check in checks:
        actions, values, group_value = query(algo, trainer, check.obs)
        if check.value is not None:
            if group_value is None:
                pairs = [(f"value {a}", v, values[a]) for a, v in check.value.items()]
            else:
                pairs = [("value group", sum(check.value.values()), group_value)]
            for output, expected, got in pairs:
                scale = max(1.0, abs(expected))
                rows.append(_row(check.name, output, expected, got, tolerance * scale))
        if check.action is not None:
            for agent, expected in check.action.items():
                got = actions[agent]
                rows.append(
                    _row(check.name, f"action {agent}", expected, got, tolerance)
                )
    return pd.DataFrame(rows)


def _row(state: str, output: str, expected: float, got: float, tol: float) -> dict:
    error = got - expected
    return {
        "state": state,
        "output": output,
        "expected": expected,
        "got": got,
        "error": error,
        "ok": abs(error) <= tol,
    }


# --------------------------------------------------------------------------------------
# Train on a probe and check the result
# --------------------------------------------------------------------------------------
def run_probe(
    probe: type,
    mode: TrainingMode,
    iters: int,
    env_config: dict,
    algorithm=None,
    tolerance: float = 0.15,
    **training,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train one paradigm on one probe in this process, then check its outputs.

    Args:
        probe: A probe environment class (``core/envs/probes.py``).
        mode: The training paradigm.
        iters: Training iterations.
        env_config: The probe's configuration (``n_agents``, ``scramble_ids``).
        algorithm: ``RLAlgorithm``; PPO when ``None``.
        tolerance: As in ``evaluate``.
        **training: Overrides of the algorithm's training settings
            (``build_local``), e.g. ``gamma=0.5`` for the discount probe.

    Returns:
        The checks (``evaluate``) and the training history (``local.train``).
    """
    from RL.core.rl.base import RLAlgorithm
    from RL.core.rl.local import build_local, train

    trainer = RLTrainer(
        probe,
        env_config,
        algorithm or RLAlgorithm.PPO,
        mode,
        iters=1,
        checkpoint_freq=1,
        cpus=1,
        gpus=0,
    )
    algo = build_local(trainer, **training)
    try:
        history = train(algo, iters)
        checks = evaluate(
            algo, trainer, probe(env_config).checks(algo.config.gamma), tolerance
        )
    finally:
        algo.stop()
    return checks, history
