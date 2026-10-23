"""CTCE: all agents as one agent, ``"group"`` (centralised training, centralised
execution).

``CTCEEnv`` observes every agent's observation joined into one flat ``Box`` (the
global state, ``core/rl/state.py``), outputs every agent's action as one ``Tuple``
of the agents' own action spaces, both in the environment's agent order, and
receives the sum of the agents' rewards: one controller maximising the total (the
social planner). RLlib's own modules and PPO train it as an ordinary single agent.

The ``Tuple`` keeps each agent's action as it is, nested and mixed (the market's
``Dict`` of categorical and continuous parts): RLlib's catalog gives the group one
composite distribution with a part per agent and component, so its
log-probability is the sum over all of them and PPO clips one ratio, the joint
controller's. Nothing categorical is flattened into, or decoded from, a ``Box``.

Fixes L-05 (with ``state.py``): each agent keeps its own action space (and bounds)
at its place in the ``Tuple``, in ``env.agents_id`` order, so RLlib rescales every
continuous part to that agent's bounds and ``ungroup`` hands each part to the
right agent.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv
from ray.rllib.utils.typing import MultiAgentDict

from core.rl.state import join, join_spaces

GROUP = "group"


def ungroup(joint, agents: list[str]) -> dict:
    """The group's ``Tuple`` action as each agent's own action, in ``agents``
    order."""
    if len(joint) != len(agents):
        raise ValueError(
            f"group action has {len(joint)} parts for {len(agents)} agents"
        )
    return {agent: part for agent, part in zip(agents, joint)}


class CTCEEnv(MultiAgentEnv):
    """The agents of ``env_class`` as one agent, ``"group"``.

    The wrapped environment must have every agent act at every step (as the
    market does): ``agents_id``, one flat ``Box`` per agent in
    ``observation_spaces``, any action space per agent in ``action_spaces``, and
    ``"__all__"`` in ``terminateds`` and ``truncateds``.

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
        self.agents = self.possible_agents = [GROUP]
        self.observation_spaces = {
            GROUP: join_spaces([self.env.observation_spaces[a] for a in self.agents_id])
        }
        self.action_spaces = {
            GROUP: spaces.Tuple([self.env.action_spaces[a] for a in self.agents_id])
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
        actions = ungroup(action_dict[GROUP], self.agents_id)
        obs, rewards, terminateds, truncateds, infos = self.env.step(actions)
        missing = set(self.agents_id) - set(rewards)

        if missing:
            raise ValueError(
                f"CTCEEnv needs every agent at every step; no reward for {missing}."
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
