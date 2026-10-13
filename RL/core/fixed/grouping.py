"""All agents of a multi-agent environment as one agent, for CTCE and CTDE.

The group observes every agent's observation and outputs every agent's action,
each joined into one flat ``Box`` in the environment's agent order, and receives
the sum of the agents' rewards. Built this way, the group is an ordinary agent
with a ``Box`` observation and action, so RLlib's own modules and algorithms
train it unchanged (CTCE), and CTDE only changes the network that maps the joint
observation to the joint action (``core/fixed/ctde_modules.py``).

Fixes I-59: the original put the agents' spaces in sorted name order and their
data in environment order. Here both follow ``env.agents_id``, and each agent
keeps its own action bounds in its slice of the joint ``Box``, so RLlib rescales
every agent's action to that agent's bounds.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv
from ray.rllib.utils.typing import MultiAgentDict

GROUP = "group"


def join_spaces(boxes: list[spaces.Box]) -> spaces.Box:
    """One ``Box`` holding the given boxes one after the other."""
    return spaces.Box(
        low=np.concatenate([b.low.reshape(-1) for b in boxes]),
        high=np.concatenate([b.high.reshape(-1) for b in boxes]),
        dtype=np.float32,
    )


def split_space(box: spaces.Box, dims: list[int]) -> list[spaces.Box]:
    """Cut a joint ``Box`` back into one ``Box`` per agent."""
    edges = np.cumsum([0, *dims])
    return [
        spaces.Box(box.low[a:b], box.high[a:b], dtype=np.float32)
        for a, b in zip(edges[:-1], edges[1:])
    ]


def split(joint: np.ndarray, agents: list[str], dims: list[int]) -> dict:
    """Cut a joint vector into each agent's part, in ``agents`` order."""
    edges = np.cumsum([0, *dims])
    return {
        agent: np.asarray(joint[..., a:b], dtype=np.float32)
        for agent, a, b in zip(agents, edges[:-1], edges[1:])
    }


def join(values: dict, agents: list[str]) -> np.ndarray:
    """Join each agent's vector into one, in ``agents`` order."""
    return np.concatenate(
        [np.asarray(values[a], dtype=np.float32).reshape(-1) for a in agents]
    )


class GroupedEnv(MultiAgentEnv):
    """The agents of ``env_class`` as one agent, ``"group"``.

    The wrapped environment must have every agent act at every step (as the
    market does): ``agents_id``, one ``Box`` per agent in ``observation_spaces``
    and ``action_spaces``, and ``"__all__"`` in ``terminateds`` and
    ``truncateds``.

    env_config keys:
        env_class: The multi-agent environment class.
        env_config: Its ``env_config``.

    The group's ``infos`` hold the agents' own rewards and infos
    (``{"rewards": {...}, "infos": {...}}``), so evaluation and the market's
    metrics can be read per agent as in DTDE.
    """

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        config = env_config or {}
        self.env = config["env_class"](config.get("env_config", {}))
        self.agents_id = list(self.env.agents_id)
        self.obs_dims = [
            int(np.prod(self.env.observation_spaces[a].shape)) for a in self.agents_id
        ]
        self.act_dims = [
            int(np.prod(self.env.action_spaces[a].shape)) for a in self.agents_id
        ]
        self.agents = self.possible_agents = [GROUP]
        self.observation_spaces = {
            GROUP: join_spaces([self.env.observation_spaces[a] for a in self.agents_id])
        }
        self.action_spaces = {
            GROUP: join_spaces([self.env.action_spaces[a] for a in self.agents_id])
        }

    def reset(
        self, *, seed: Optional[int] = None, options: Optional[dict] = None
    ) -> tuple[MultiAgentDict, MultiAgentDict]:
        obs, infos = self.env.reset(seed=seed, options=options)
        return {GROUP: join(obs, self.agents_id)}, {GROUP: {"infos": infos}}

    def step(
        self, action_dict: MultiAgentDict
    ) -> tuple[
        MultiAgentDict, MultiAgentDict, MultiAgentDict, MultiAgentDict, MultiAgentDict
    ]:
        actions = split(action_dict[GROUP], self.agents_id, self.act_dims)
        obs, rewards, terminateds, truncateds, infos = self.env.step(actions)
        missing = set(self.agents_id) - set(rewards)
        if missing:
            raise ValueError(
                f"GroupedEnv needs every agent at every step; no reward for {missing}."
            )
        group_reward = float(sum(rewards[a] for a in self.agents_id))
        return (
            {GROUP: join(obs, self.agents_id)},
            {GROUP: group_reward},
            {GROUP: terminateds["__all__"], "__all__": terminateds["__all__"]},
            {GROUP: truncateds["__all__"], "__all__": truncateds["__all__"]},
            {GROUP: {"rewards": dict(rewards), "infos": infos}},
        )

    def render(self):
        return self.env.render()
