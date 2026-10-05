"""The benchmark cases: external environments for MARLEM's trainer.

A case names an environment, its fixed settings and the paradigms it can test.
It never implements an algorithm or a training loop: ``trainer`` hands the case
to ``marl.train.RLTrainer``, the class that also trains the market (D-16).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src_thesis.marlem.marl.base import RLAlgorithm, TrainingMode
from src_thesis.marlem.marl.train import RLTrainer


@dataclass(frozen=True)
class BenchmarkCase:
    """One external task.

    Attributes:
        case_id: Short name, used on the command line and in run folders.
        gate: Gate of the plan (A–D, rl-testbench.md §2).
        description: One line for listings.
        paradigms: Paradigms this task tests (``"dtde"``, ``"ctce"``, ``"ctde"``).
        env_config: Fixed settings passed to the environment.
        load_env: Returns the environment class; imported on demand, so a case
            whose package is missing only fails when it is used.
    """

    case_id: str
    gate: str
    description: str
    paradigms: tuple[str, ...]
    env_config: dict[str, Any]
    load_env: Callable[[], type]

    def env_cls(self) -> type:
        """The environment class (an RLlib ``MultiAgentEnv``)."""
        return self.load_env()


def _multiagent_cartpole() -> type:
    from ray.rllib.examples.envs.classes.multi_agent import MultiAgentCartPole

    return MultiAgentCartPole


def _simple_spread() -> type:
    try:
        from mpe2 import simple_spread_v3
        from ray.rllib.env.wrappers.pettingzoo_env import ParallelPettingZooEnv
    except ImportError as error:
        raise ImportError(
            "Simple Spread needs mpe2 1.1.1 and pettingzoo 1.27.0 (gate C, "
            "rl-testbench.md §5); they are not installed"
        ) from error

    class SimpleSpread(ParallelPettingZooEnv):
        """MPE2 Simple Spread as an RLlib multi-agent environment."""

        def __init__(self, config: dict[str, Any]) -> None:
            super().__init__(simple_spread_v3.parallel_env(**config))

    return SimpleSpread


CASES: dict[str, BenchmarkCase] = {
    c.case_id: c
    for c in (
        BenchmarkCase(
            "cartpole",
            "A",
            "CartPole with one agent, through RLlib's multi-agent API",
            ("dtde",),
            {"num_agents": 1},
            _multiagent_cartpole,
        ),
        BenchmarkCase(
            "multiagent_cartpole",
            "B",
            "RLlib MultiAgentCartPole, two independent carts",
            ("dtde", "ctce", "ctde"),  # grouped modes: plumbing checks only
            {"num_agents": 2},
            _multiagent_cartpole,
        ),
        BenchmarkCase(
            "simple_spread",
            "C",
            "MPE2 Simple Spread, three agents, 25 cycles, discrete actions",
            ("dtde", "ctce", "ctde"),
            {"N": 3, "max_cycles": 25, "continuous_actions": False},
            _simple_spread,
        ),
    )
}


def trainer(
    case: BenchmarkCase, algorithm: str, paradigm: str, **kwargs: Any
) -> RLTrainer:
    """MARLEM's ``RLTrainer`` for one case, algorithm and paradigm.

    Args:
        case: The benchmark case.
        algorithm: ``"ppo"``, ``"appo"`` or ``"sac"``.
        paradigm: One of the case's paradigms.
        **kwargs: Further ``RLTrainer`` arguments (iterations, CPUs, storage, …).

    Raises:
        ValueError: The case does not test ``paradigm``.
    """
    if paradigm not in case.paradigms:
        raise ValueError(
            f"{case.case_id} tests {list(case.paradigms)}, not {paradigm!r}"
        )
    return RLTrainer(
        dict(case.env_config),
        algorithm=RLAlgorithm[algorithm.upper()],
        training=TrainingMode[paradigm.upper()],
        env_cls=case.env_cls(),
        **kwargs,
    )
