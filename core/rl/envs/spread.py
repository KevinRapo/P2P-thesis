"""Farama MPE2 ``simple_spread`` as an environment the trainer can use.

A second test of the RL code after the probes (``core/rl/envs/probes.py``): a
standard cooperative multi-agent task with continuous actions, small enough to
train in minutes and to watch (``notebooks/rl/simple_spread.ipynb``).

The task: ``n_agents`` agents and as many landmarks in a 2D plane. The agents
should cover the landmarks, one each, without bumping into each other. Episodes
last ``max_cycles`` steps (25) and end by time, never by success.

- Observation (``Box(-inf, inf, (6 * n_agents,))`` per agent): own velocity (2), own
  position (2), the position of each landmark relative to the agent (2 each), the
  position of each other agent relative to the agent (2 each) and the other agents'
  communication (2 each, always 0: the agents are silent). 18 numbers for 3 agents.
- Action (``Box(0, 1, (5,))`` per agent, as in PettingZoo's MPE with continuous
  actions): ``[no-op, left, right, down, up]``. The agent is pushed with the force
  ``(right - left, up - down)`` (times 5); element 0 is not used. So the action
  ``[0, 0, 0, 0, 0]`` is "no force" and ``[x, 1, 1, 0, 0]`` also is: left and right
  cancel. Values are clipped to [0, 1] here.
- Reward (per agent): ``local_ratio`` times the agent's own reward (minus one for
  each other agent it touches) plus ``1 - local_ratio`` times the team's reward (minus
  the distance from each landmark to the nearest agent, summed over the landmarks).
  The team part is the same for everyone, so the task is cooperative. The sum over
  the agents is the episode return RLlib reports.

The interface is that of ``core/rl/envs/toy.py``: built as ``SimpleSpread(env_config)``,
fixed ``agents_id`` (``agent_00``, ``agent_01``, ..., zero-padded so that sorted
order, which ``GroupedEnv`` uses, equals this order), one ``Box`` per agent in
``observation_spaces`` and ``action_spaces``, and ``"__all__"`` in ``terminateds``
and ``truncateds``. PettingZoo ends the episode by truncation at ``max_cycles``;
that is passed on as ``truncateds``, with ``terminateds`` always False.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np
from gymnasium import spaces
from mpe2 import simple_spread_v3
from ray.rllib.env.multi_agent_env import MultiAgentEnv


class SimpleSpread(MultiAgentEnv):
    """``simple_spread`` with continuous actions, one RLlib agent per MPE agent.

    env_config keys:
        n_agents: Agents, and as many landmarks (default 3).
        max_cycles: Steps per episode (default 25).
        local_ratio: Weight of the agent's own reward against the team's (default
            0.5, PettingZoo's).
        seed: Seed of the first reset (default none).
        render_mode: ``None`` or ``"rgb_array"`` (for ``render``).
    """

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        config = env_config or {}
        self.n_agents = int(config.get("n_agents", 3))
        self.max_cycles = int(config.get("max_cycles", 25))
        self.local_ratio = float(config.get("local_ratio", 0.5))
        self.seed = config.get("seed")
        self.render_mode = config.get("render_mode")
        self.env = simple_spread_v3.parallel_env(
            N=self.n_agents,
            local_ratio=self.local_ratio,
            max_cycles=self.max_cycles,
            continuous_actions=True,
            render_mode=self.render_mode,
        )
        # PettingZoo's names (agent_0, ...) to ours, zero-padded.
        width = max(2, len(str(self.n_agents - 1)))
        self._name = {
            pz: f"agent_{i:0{width}d}" for i, pz in enumerate(self.env.possible_agents)
        }
        self._pz = {name: pz for pz, name in self._name.items()}
        self.agents_id = list(self._name.values())
        self.agents = self.possible_agents = list(self.agents_id)
        self.observation_spaces = {
            self._name[pz]: spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=self.env.observation_space(pz).shape,
                dtype=np.float32,
            )
            for pz in self.env.possible_agents
        }
        self.action_spaces = {
            self._name[pz]: spaces.Box(
                low=0.0,
                high=1.0,
                shape=self.env.action_space(pz).shape,
                dtype=np.float32,
            )
            for pz in self.env.possible_agents
        }
        self._first_reset = True

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        if seed is None and self._first_reset:
            seed = self.seed
        self._first_reset = False
        obs, _ = self.env.reset(seed=seed, options=options)
        return self._obs(obs), {a: {} for a in self.agents_id}

    def step(self, action_dict: dict[str, np.ndarray]):
        actions = {
            self._pz[a]: np.clip(np.asarray(action_dict[a], dtype=np.float32), 0.0, 1.0)
            for a in self.agents_id
        }
        obs, rewards, terminations, truncations, _ = self.env.step(actions)
        # PettingZoo empties its agent list when the episode ends; the last
        # observation of an ended episode is still returned.
        done = any(terminations.values())
        cut = any(truncations.values()) and not done
        terminateds = {a: done for a in self.agents_id} | {"__all__": done}
        truncateds = {a: cut for a in self.agents_id} | {"__all__": cut}
        rewards = {self._name[pz]: float(r) for pz, r in rewards.items()}
        return self._obs(obs), rewards, terminateds, truncateds, {}

    def render(self) -> np.ndarray:
        """The current state as an RGB frame (needs ``render_mode="rgb_array"``)."""
        return self.env.render()

    def close(self) -> None:
        self.env.close()

    def _obs(self, obs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return {
            self._name[pz]: np.asarray(o, dtype=np.float32) for pz, o in obs.items()
        }


# --------------------------------------------------------------------------------------
# Baselines: returns of simple policies, to read training curves against
# --------------------------------------------------------------------------------------
def baseline_return(
    env_config: dict[str, Any],
    policy: str,
    episodes: int = 200,
    seed: int = 0,
) -> float:
    """Mean episode return of all agents together (what RLlib reports as
    ``episode_return_mean``) under ``policy``: ``"random"`` (each action element
    uniform in [0, 1]) or ``"zero"`` (the no-op action, all zeros: no force)."""
    env = SimpleSpread({**env_config, "render_mode": None})
    rng = np.random.default_rng(seed)
    totals = []
    for episode in range(episodes):
        env.reset(seed=seed + episode)
        total, done = 0.0, False
        while not done:
            if policy == "random":
                actions = {
                    a: rng.uniform(0, 1, env.action_spaces[a].shape).astype(np.float32)
                    for a in env.agents_id
                }
            elif policy == "zero":
                actions = {
                    a: np.zeros(env.action_spaces[a].shape, dtype=np.float32)
                    for a in env.agents_id
                }
            else:
                raise ValueError(f"Unknown policy {policy!r}")
            _, rewards, terminateds, truncateds, _ = env.step(actions)
            total += sum(rewards.values())
            done = terminateds["__all__"] or truncateds["__all__"]
        totals.append(total)
    env.close()
    return float(np.mean(totals))


# --------------------------------------------------------------------------------------
# Watching an episode
# --------------------------------------------------------------------------------------
def episode_frames(
    env_config: dict[str, Any],
    act: Callable[[dict[str, np.ndarray]], dict[str, np.ndarray]],
    seed: int = 0,
    size: int = 240,
) -> tuple[list[np.ndarray], float]:
    """Play one episode, drawing every step.

    Args:
        env_config: As for ``SimpleSpread`` (``render_mode`` is set here).
        act: Maps all agents' observations to all agents' actions.
        seed: Seed of the episode, so two policies can start from the same state.
        size: Frame width and height in pixels (the environment draws 700).

    Returns:
        The frames (the start and the state after each step, RGB, ``size`` x
        ``size``) and the episode return summed over the agents.
    """
    from PIL import Image

    env = SimpleSpread({**env_config, "render_mode": "rgb_array"})

    def frame() -> np.ndarray:
        image = Image.fromarray(env.render()).resize((size, size), Image.LANCZOS)
        return np.asarray(image)

    obs, _ = env.reset(seed=seed)
    frames, total, done = [frame()], 0.0, False
    while not done:
        obs, rewards, terminateds, truncateds, _ = env.step(act(obs))
        frames.append(frame())
        total += sum(rewards.values())
        done = terminateds["__all__"] or truncateds["__all__"]
    env.close()
    return frames, total


def random_policy(env_config: dict[str, Any], seed: int = 0):
    """A policy for ``episode_frames``: every action element uniform in [0, 1]."""
    rng = np.random.default_rng(seed)
    shape = SimpleSpread({**env_config, "render_mode": None}).action_spaces
    return lambda obs: {
        a: rng.uniform(0, 1, shape[a].shape).astype(np.float32) for a in obs
    }
