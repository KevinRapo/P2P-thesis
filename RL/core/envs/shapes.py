"""A synthetic environment with the market's shapes, for timing the learner.

Each agent observes as many numbers and sends as many actions as a MARLEM market
agent (``obs_dim`` 42, ``act_dim`` 4; with partner preference the observation
also holds one reputation per agent, ``42 + n_agents``), in episodes of the
market's length (24 hourly steps by default). Nothing else of the market is in
it: observations are drawn at random every step and the reward is cheap, so a
run on it times RLlib and the networks alone. The market's own cost per step is
measured on the market side (``../notebooks/benchmark_market_step.ipynb``).

The reward is learnable, so the same runs also show whether a paradigm still
learns at this size: each agent has a fixed random linear target
``t_i = clip(W_i o_i, -1, 1)`` and gets ``1 - mean((a_i - t_i)^2)`` per step:
about 0.2 for an untrained policy (wide Gaussian actions), at most about 0.7 for
one that ignores its observation (always 0), and 1 for the right one.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv

MARKET_OBS_DIM = 42
MARKET_ACT_DIM = 4


class MarketShapedEnv(MultiAgentEnv):
    """``n_agents`` agents with the market's observation and action sizes.

    env_config keys:
        n_agents: Number of agents (default 5).
        obs_dim: Observation size per agent before partner preference (42).
        act_dim: Action size per agent (4).
        partner_preference: Add one reputation per agent to each observation.
        episode_length: Steps per episode (24: one day of hourly steps).
        seed: Seed of the targets and of the first reset.
    """

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        config = env_config or {}
        n = int(config.get("n_agents", 5))
        obs_dim = int(config.get("obs_dim", MARKET_OBS_DIM))
        if config.get("partner_preference"):
            obs_dim += n
        act_dim = int(config.get("act_dim", MARKET_ACT_DIM))
        self.length = int(config.get("episode_length", 24))
        self.agents_id = [f"agent_{k:03d}" for k in range(n)]
        self.agents = self.possible_agents = list(self.agents_id)
        obs_box = spaces.Box(-1.0, 1.0, (obs_dim,), np.float32)
        act_box = spaces.Box(-1.0, 1.0, (act_dim,), np.float32)
        self.observation_spaces = {a: obs_box for a in self.agents_id}
        self.action_spaces = {a: act_box for a in self.agents_id}
        # Fixed targets: about unit scale, so most fall inside [-1, 1].
        targets = np.random.default_rng(config.get("seed", 0))
        self.weights = {
            a: targets.normal(0.0, 1.0 / np.sqrt(obs_dim), (act_dim, obs_dim))
            for a in self.agents_id
        }
        self.rng = np.random.default_rng(config.get("seed"))
        self.t = 0

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.t = 0
        self._draw()
        return dict(self.obs), {a: {} for a in self.agents_id}

    def step(self, action_dict: dict[str, np.ndarray]):
        rewards = {}
        for a in self.agents_id:
            action = np.clip(np.asarray(action_dict[a], np.float32), -1.0, 1.0)
            target = np.clip(self.weights[a] @ self.obs[a], -1.0, 1.0)
            rewards[a] = float(1.0 - np.mean((action - target) ** 2))
        self.t += 1
        done = self.t >= self.length
        self._draw()
        terminateds = {a: done for a in self.agents_id} | {"__all__": done}
        truncateds = {a: False for a in self.agents_id} | {"__all__": False}
        return dict(self.obs), rewards, terminateds, truncateds, {}

    def _draw(self) -> None:
        self.obs = {
            a: self.rng.uniform(-1.0, 1.0, space.shape).astype(np.float32)
            for a, space in self.observation_spaces.items()
        }
