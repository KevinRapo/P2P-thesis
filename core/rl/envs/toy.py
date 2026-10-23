"""Small multi-agent environments with a known best return, for testing the RL code.

They have the interface the trainer needs from the local energy market
(``core/rl/train.py``), so the algorithms and training paradigms can be checked
without it:

- built as ``Env(env_config)``;
- ``agents_id``: the agents, in a fixed order;
- ``observation_spaces`` and ``action_spaces``: one ``Box`` per agent;
- ``reset`` and ``step`` return one entry per agent, and ``"__all__"`` in
  ``terminateds`` and ``truncateds``; an episode lasts ``max_steps`` steps.

Two tasks, each with a known best and random return per agent and episode:

- ``TargetEnv``: each agent sees a private target and is paid for matching it.
  Rewards are individual, so every paradigm should learn it.
- ``BalanceEnv``: each agent sees its own net position and chooses a trade; all
  agents get the same team reward for the total imbalance. The best policy is
  still "trade your own position", but each agent's effect on its reward is mixed
  with everyone else's (credit assignment), which centralised training should
  handle better than independent learners.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv


# --------------------------------------------------------------------------------------
# Shared base: agents, spaces, episode clock
# --------------------------------------------------------------------------------------
class _ToyEnv(MultiAgentEnv):
    """Agents with ``Box(-1, 1)`` observations and actions, fixed-length episodes.

    env_config keys:
        n_agents: Number of agents (default 3).
        max_steps: Steps per episode (default 10).
        seed: Seed of the first reset (default none).
    """

    obs_dim = 1
    act_dim = 1

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        config = env_config or {}
        self.n_agents = int(config.get("n_agents", 3))
        self.max_steps = int(config.get("max_steps", 10))
        self.seed = config.get("seed")
        # Zero-padded, so sorted order equals this order.
        self.agents_id = [f"agent_{i:02d}" for i in range(self.n_agents)]
        self.agents = self.possible_agents = list(self.agents_id)
        box = dict(low=-1.0, high=1.0, dtype=np.float32)
        self.observation_spaces = {
            a: spaces.Box(shape=(self.obs_dim,), **box) for a in self.agents_id
        }
        self.action_spaces = {
            a: spaces.Box(shape=(self.act_dim,), **box) for a in self.agents_id
        }
        self.rng = np.random.default_rng(self.seed)
        self.t = 0

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.t = 0
        self._draw()
        return self._obs(), {a: {} for a in self.agents_id}

    def step(self, action_dict: dict[str, np.ndarray]):
        actions = {
            a: np.clip(np.asarray(action_dict[a], dtype=np.float64), -1.0, 1.0)
            for a in self.agents_id
        }
        rewards = self._rewards(actions)
        self.t += 1
        done = self.t >= self.max_steps
        self._draw()
        terminateds = {a: done for a in self.agents_id} | {"__all__": done}
        truncateds = {a: False for a in self.agents_id} | {"__all__": False}
        return self._obs(), rewards, terminateds, truncateds, {}

    # --- What each task defines ------------------------------------------------------
    def _draw(self) -> None:
        """New private values for the next step."""
        raise NotImplementedError

    def _obs(self) -> dict[str, np.ndarray]:
        raise NotImplementedError

    def _rewards(self, actions: dict[str, np.ndarray]) -> dict[str, float]:
        raise NotImplementedError

    def best_action(self, agent: str) -> np.ndarray:
        """The optimal action of ``agent`` in the current state."""
        raise NotImplementedError


# --------------------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------------------
class TargetEnv(_ToyEnv):
    """Each agent sees a private target ``x_i`` in [-1, 1]^2 and is paid
    ``-mean((a_i - x_i)^2)``. Two action dimensions, like a bid price and quantity.

    Per agent and episode: best return 0; uniformly random actions about
    ``-max_steps * 2/3``.
    """

    obs_dim = 2
    act_dim = 2

    def _draw(self) -> None:
        self.x = {a: self.rng.uniform(-1, 1, self.obs_dim) for a in self.agents_id}

    def _obs(self) -> dict[str, np.ndarray]:
        return {a: self.x[a].astype(np.float32) for a in self.agents_id}

    def _rewards(self, actions: dict[str, np.ndarray]) -> dict[str, float]:
        return {
            a: -float(np.mean((actions[a] - self.x[a]) ** 2)) for a in self.agents_id
        }

    def best_action(self, agent: str) -> np.ndarray:
        return self.x[agent].astype(np.float32)


class BalanceEnv(_ToyEnv):
    """Each agent sees its own net position ``n_i`` in [-1, 1] and trades ``q_i``.
    Every agent gets the same team reward ``-(sum(n_i - q_i) / n_agents)^2``.

    Per agent and episode: best return 0; uniformly random actions about
    ``-max_steps * 2/3 / n_agents``.
    """

    def _draw(self) -> None:
        self.n = {a: self.rng.uniform(-1, 1, 1) for a in self.agents_id}

    def _obs(self) -> dict[str, np.ndarray]:
        return {a: self.n[a].astype(np.float32) for a in self.agents_id}

    def _rewards(self, actions: dict[str, np.ndarray]) -> dict[str, float]:
        imbalance = sum(float(self.n[a][0] - actions[a][0]) for a in self.agents_id)
        team = -((imbalance / self.n_agents) ** 2)
        return {a: team for a in self.agents_id}

    def best_action(self, agent: str) -> np.ndarray:
        return self.n[agent].astype(np.float32)


# --------------------------------------------------------------------------------------
# Baselines: returns of known policies, to read training curves against
# --------------------------------------------------------------------------------------
def baseline_return(
    env_class: type[_ToyEnv],
    env_config: dict[str, Any],
    policy: str,
    episodes: int = 200,
    seed: int = 0,
) -> float:
    """Mean episode return of all agents together (what RLlib reports as
    ``episode_return_mean``) under ``policy``: ``"best"``, ``"random"`` or
    ``"zero"`` (always act 0)."""
    env = env_class(env_config)
    rng = np.random.default_rng(seed)
    totals = []
    for episode in range(episodes):
        env.reset(seed=seed + episode)
        total, done = 0.0, False
        while not done:
            if policy == "best":
                actions = {a: env.best_action(a) for a in env.agents_id}
            elif policy == "random":
                actions = {
                    a: rng.uniform(-1, 1, env.act_dim).astype(np.float32)
                    for a in env.agents_id
                }
            elif policy == "zero":
                actions = {
                    a: np.zeros(env.act_dim, dtype=np.float32) for a in env.agents_id
                }
            else:
                raise ValueError(f"Unknown policy {policy!r}")
            _, rewards, terminateds, _, _ = env.step(actions)
            total += sum(rewards.values())
            done = terminateds["__all__"]
        totals.append(total)
    return float(np.mean(totals))
