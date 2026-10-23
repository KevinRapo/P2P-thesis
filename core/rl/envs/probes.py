"""Probe environments: tiny tasks whose correct value and policy are known exactly.

After Andy Jones, "Debugging RL, Without the Agonizing Pain"
(https://andyljones.com/posts/rl-debugging.html): a sequence of environments,
each adding one piece of the learning problem, so the first one that fails names
the broken piece. Here they are multi-agent and continuous (``Box(-1, 1)``
observations and actions, like the market), and each agent has its own reward,
so they also check what the training paradigms add: routing every agent's
observation, action and reward to the right place, and summing rewards for the
grouped paradigms (CTCE, CTDE).

    1  ConstantProbe       value       obs 0, reward +1             V = 1
    2  ObservationProbe    obs -> value  obs ±1, reward = obs       V(o) = o
    3  DiscountProbe       discounting  obs 0 then 1, +1 at the end  V(0) = γ, V(1) = 1
    4  ActionProbe         policy      obs 0, reward peaks at t_i    action = t_i
    5  ObsActionProbe      obs -> policy  obs ±1, reward peaks at o/2  action = o/2
    6  MixedActionProbe    mixed policy  obs 0, a category and a level  choice = c_i,
                                                                      level = t_i

Each agent has a different target ``t_i`` in probe 4, so an action delivered to
the wrong agent shows. ``scramble_ids`` names the agents so that their sorted
order differs from their order in the environment (the original's grouping sorted
the agents' spaces while RLlib grouped their data in the environment's order, L-05).

``checks(gamma)`` lists what a trained module must output: per agent and state,
the expected value (per agent; the grouped paradigms' value is the sum over the
agents, as their reward is) and/or the expected action mean.

Probe 6 has the market's kind of action: a ``Dict`` with a categorical and a
continuous part (``choice``, ``level``), each with its own optimum per agent. It
checks that RLlib's composite distribution learns both parts at once, in every
paradigm (CTCE's group action is a ``Tuple`` of these ``Dict`` s).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv


@dataclass
class Check:
    """One state to query a trained module in, and what it must output.

    Attributes:
        name: Short description of the state.
        obs: Observation of each agent.
        value: Expected value of each agent (``None``: not checked).
        action: Expected action mean of each agent (``None``: not checked).
    """

    name: str
    obs: dict[str, np.ndarray]
    value: Optional[dict[str, float]] = None
    action: Optional[dict[str, float]] = None


# --------------------------------------------------------------------------------------
# Base: agents, spaces, clock
# --------------------------------------------------------------------------------------
class _Probe(MultiAgentEnv):
    """``n_agents`` agents with one-dimensional observations and actions in
    [-1, 1]; episodes of ``length`` steps.

    env_config keys:
        n_agents: Number of agents (default 3).
        scramble_ids: Name the agents so sorted order differs from their order.
        seed: Seed of the first reset.
    """

    length = 1

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        config = env_config or {}
        n = int(config.get("n_agents", 3))

        if config.get("scramble_ids"):
            # e.g. agent_2, agent_10, agent_1: sorted is agent_1, agent_10, agent_2
            numbers = [2, 10, 1] + list(range(11, 8 + n))
            self.agents_id = [f"agent_{k}" for k in numbers[:n]]
        else:
            self.agents_id = [f"agent_{k:02d}" for k in range(n)]

        self.agents = self.possible_agents = list(self.agents_id)
        box = spaces.Box(-1.0, 1.0, (1,), np.float32)
        self.observation_spaces = {a: box for a in self.agents_id}
        self.action_spaces = {a: box for a in self.agents_id}
        self.rng = np.random.default_rng(config.get("seed"))
        self.t = 0
        # Targets for the action probes: one per agent, all different.
        self.targets = {
            a: float(t) for a, t in zip(self.agents_id, np.linspace(-0.6, 0.6, n))
        }

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        self.t = 0
        self._draw()

        return self._obs(), {a: {} for a in self.agents_id}

    def step(self, action_dict: dict[str, np.ndarray]):
        actions = {a: self._parse(action_dict[a]) for a in self.agents_id}
        rewards = {a: float(self._reward(a, actions[a])) for a in self.agents_id}
        self.t += 1
        done = self.t >= self.length

        if not done:
            self._draw()

        terminateds = {a: done for a in self.agents_id} | {"__all__": done}
        truncateds = {a: False for a in self.agents_id} | {"__all__": False}

        return self._obs(), rewards, terminateds, truncateds, {}

    def _obs(self) -> dict[str, np.ndarray]:
        return {a: np.array([self.o[a]], dtype=np.float32) for a in self.agents_id}

    def _all(self, value: float) -> dict[str, np.ndarray]:
        return {a: np.array([value], dtype=np.float32) for a in self.agents_id}

    # --- What each probe defines -----------------------------------------------------
    def _parse(self, action) -> Any:
        """One agent's action as ``_reward`` takes it (here: a number in [-1, 1])."""
        return float(np.clip(np.asarray(action).reshape(-1)[0], -1.0, 1.0))

    def _draw(self) -> None:
        """Each agent's observation for the current step (``self.o``)."""
        self.o = {a: 0.0 for a in self.agents_id}

    def _reward(self, agent: str, action: float) -> float:
        raise NotImplementedError

    def checks(self, gamma: float) -> list[Check]:
        raise NotImplementedError


# --------------------------------------------------------------------------------------
# The five probes
# --------------------------------------------------------------------------------------
class ConstantProbe(_Probe):
    """1. Zero observation, one step, reward +1. Checks the value loss and the
    optimiser: the value must reach 1."""

    def _reward(self, agent: str, action: float) -> float:
        return 1.0

    def checks(self, gamma: float) -> list[Check]:
        return [Check("obs 0", self._all(0.0), value={a: 1.0 for a in self.agents_id})]


class ObservationProbe(_Probe):
    """2. Observation ±1 per agent, one step, reward = the agent's observation.
    Checks that observations reach the value network (and reach it for the right
    agent): the value must equal the observation."""

    def _draw(self) -> None:
        self.o = {a: float(self.rng.choice([-1.0, 1.0])) for a in self.agents_id}

    def _reward(self, agent: str, action: float) -> float:
        return self.o[agent]

    def checks(self, gamma: float) -> list[Check]:
        mixed = {a: (1.0 if i % 2 == 0 else -1.0) for i, a in enumerate(self.agents_id)}
        out = []

        for name, o in (
            ("all +1", {a: 1.0 for a in self.agents_id}),
            ("all -1", {a: -1.0 for a in self.agents_id}),
            ("mixed", mixed),
        ):
            obs = {a: np.array([v], dtype=np.float32) for a, v in o.items()}
            out.append(Check(name, obs, value=dict(o)))

        return out


class DiscountProbe(_Probe):
    """3. Two steps: observation 0, then 1; reward +1 only at the end. Checks
    discounting and episode ends: V(1) = 1, V(0) = γ."""

    length = 2

    def _draw(self) -> None:
        self.o = {a: float(self.t) for a in self.agents_id}

    def _reward(self, agent: str, action: float) -> float:
        return 1.0 if self.t == 1 else 0.0

    def checks(self, gamma: float) -> list[Check]:
        return [
            Check(
                "first step", self._all(0.0), value={a: gamma for a in self.agents_id}
            ),
            Check("last step", self._all(1.0), value={a: 1.0 for a in self.agents_id}),
        ]


class ActionProbe(_Probe):
    """4. Zero observation, one step, reward ``1 - (a_i - t_i)^2`` with a
    different target ``t_i`` per agent. Checks the policy gradient and that each
    agent's action reaches its own reward: the action mean must reach ``t_i``."""

    def _reward(self, agent: str, action: float) -> float:
        return 1.0 - (action - self.targets[agent]) ** 2

    def checks(self, gamma: float) -> list[Check]:
        return [Check("obs 0", self._all(0.0), action=dict(self.targets))]


class ObsActionProbe(_Probe):
    """5. Observation ±1 per agent, one step, reward ``1 - (a_i - o_i/2)^2``.
    Checks that the policy uses the agent's own observation: the action mean must
    be half the observation."""

    def _draw(self) -> None:
        self.o = {a: float(self.rng.choice([-1.0, 1.0])) for a in self.agents_id}

    def _reward(self, agent: str, action: float) -> float:
        return 1.0 - (action - self.o[agent] / 2) ** 2

    def checks(self, gamma: float) -> list[Check]:
        mixed = {a: (1.0 if i % 2 == 0 else -1.0) for i, a in enumerate(self.agents_id)}
        out = []

        for name, o in (
            ("all +1", {a: 1.0 for a in self.agents_id}),
            ("all -1", {a: -1.0 for a in self.agents_id}),
            ("mixed", mixed),
        ):
            obs = {a: np.array([v], dtype=np.float32) for a, v in o.items()}
            out.append(Check(name, obs, action={a: v / 2 for a, v in o.items()}))

        return out


class MixedActionProbe(_Probe):
    """6. Zero observation, one step, a mixed action ``{"choice": Discrete(3),
    "level": Box(-1, 1)}`` and reward ``[choice = c_i] + 1 - (level - t_i)^2``, with
    a different category ``c_i`` and level ``t_i`` per agent. Checks that the
    composite (categorical and Gaussian) distribution learns both parts, and that
    both reach the right agent: the most likely choice must be ``c_i`` and the
    level's mean ``t_i``. The best reward is 2."""

    n_choices = 3

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(env_config)
        unit = spaces.Box(-1.0, 1.0, (1,), np.float32)
        mixed = spaces.Dict({"choice": spaces.Discrete(self.n_choices), "level": unit})
        self.action_spaces = {a: mixed for a in self.agents_id}
        # Categories 2, 0, 1, 2, ... in agent order: not the agent's index.
        self.choices = {
            a: (i + 2) % self.n_choices for i, a in enumerate(self.agents_id)
        }

    def _parse(self, action) -> tuple[int, float]:
        level = float(np.clip(np.asarray(action["level"]).reshape(-1)[0], -1, 1))
        return int(np.asarray(action["choice"]).reshape(-1)[0]), level

    def _reward(self, agent: str, action: tuple[int, float]) -> float:
        choice, level = action
        hit = 1.0 if choice == self.choices[agent] else 0.0
        return hit + 1.0 - (level - self.targets[agent]) ** 2

    def best(self) -> dict[str, dict]:
        """Each agent's best action."""
        return {
            a: {
                "choice": self.choices[a],
                "level": np.array([self.targets[a]], dtype=np.float32),
            }
            for a in self.agents_id
        }

    def checks(self, gamma: float) -> list[Check]:
        best = {
            a: {"choice": c, "level": self.targets[a]} for a, c in self.choices.items()
        }
        return [
            Check(
                "obs 0",
                self._all(0.0),
                value={a: 2.0 for a in self.agents_id},
                action=best,
            )
        ]


PROBES = [ConstantProbe, ObservationProbe, DiscountProbe, ActionProbe, ObsActionProbe]
MIXED_PROBES = [MixedActionProbe]
