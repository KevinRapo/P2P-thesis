"""How the paradigms see a multi-agent environment: grouped (CTCE) or with a
central state (CTDE).

``GroupedEnv`` (CTCE): all agents as one agent, ``"group"``. It observes every
agent's observation joined into one flat ``Box``, outputs every agent's action as
one ``Tuple`` of the agents' own action spaces, both in the environment's agent
order, and receives the sum of the agents' rewards: one controller maximising the
total (the social planner). RLlib's own modules and PPO train it as an ordinary
single agent. The ``Tuple`` keeps each agent's action as it is, nested and mixed
(the market's ``Dict`` of categorical and continuous parts): RLlib's catalog gives
the group one composite distribution with a part per agent and component, so its
log-probability is the sum over all of them and PPO clips one ratio, the joint
controller's. Nothing categorical is flattened into, or decoded from, a ``Box``.

``CentralStateEnv`` (CTDE): the agents stay separate, each with its own reward,
but each agent's observation is extended with the global state, every agent's
observation joined: ``[o_i, o_1, ..., o_N]``. The CTDE modules
(``core/rl/ctde_modules.py``) let the actor read only ``o_i`` and the critic
read all of it, so the critic is central and the actor decentralised.

Fixes L-05: the original put the agents' spaces in sorted name order and their
data in environment order. Here both follow ``env.agents_id``, and each agent
keeps its own action space (and bounds) at its place in the ``Tuple``, so RLlib
rescales every continuous part to that agent's bounds.
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


def ungroup(joint, agents: list[str]) -> dict:
    """The group's ``Tuple`` action as each agent's own action, in ``agents``
    order."""
    if len(joint) != len(agents):
        raise ValueError(
            f"group action has {len(joint)} parts for {len(agents)} agents"
        )
    return {agent: part for agent, part in zip(agents, joint)}


def join(values: dict, agents: list[str]) -> np.ndarray:
    """Join each agent's vector into one, in ``agents`` order."""
    return np.concatenate(
        [np.asarray(values[a], dtype=np.float32).reshape(-1) for a in agents]
    )


class GroupedEnv(MultiAgentEnv):
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


# --------------------------------------------------------------------------------------
# CTDE: each agent's observation extended with the global state
# --------------------------------------------------------------------------------------
def central_obs(obs: dict, agents: list[str]) -> dict[str, np.ndarray]:
    """Each agent's observation followed by every agent's, ``[o_i, o_1..o_N]``."""
    state = join(obs, agents)
    return {
        a: np.concatenate([np.asarray(obs[a], dtype=np.float32).reshape(-1), state])
        for a in agents
    }


class CentralStateEnv(MultiAgentEnv):
    """The agents of ``env_class``, each observing ``[o_i, o_1, ..., o_N]``.

    Actions, rewards, episode ends and infos pass through unchanged: every agent
    keeps its own reward. ``own_dims[a]`` is the size of agent ``a``'s own part,
    the first entries of its observation.

    env_config keys:
        env_class: The multi-agent environment class.
        env_config: Its ``env_config``.
    """

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        config = env_config or {}
        self.env = config["env_class"](config.get("env_config", {}))
        self.agents_id = list(self.env.agents_id)
        self.agents = self.possible_agents = list(self.agents_id)
        spaces_ = self.env.observation_spaces
        state = join_spaces([spaces_[a] for a in self.agents_id])
        self.own_dims = {a: int(np.prod(spaces_[a].shape)) for a in self.agents_id}
        self.observation_spaces = {
            a: join_spaces([spaces_[a], state]) for a in self.agents_id
        }
        self.action_spaces = dict(self.env.action_spaces)

    def reset(
        self, *, seed: Optional[int] = None, options: Optional[dict] = None
    ) -> tuple[MultiAgentDict, MultiAgentDict]:
        obs, infos = self.env.reset(seed=seed, options=options)
        return central_obs(obs, self.agents_id), infos

    def step(
        self, action_dict: MultiAgentDict
    ) -> tuple[
        MultiAgentDict, MultiAgentDict, MultiAgentDict, MultiAgentDict, MultiAgentDict
    ]:
        obs, rewards, terminateds, truncateds, infos = self.env.step(action_dict)
        missing = set(self.agents_id) - set(obs)
        if missing:
            raise ValueError(
                f"CentralStateEnv needs every agent at every step; no observation "
                f"for {missing}."
            )
        return central_obs(obs, self.agents_id), rewards, terminateds, truncateds, infos

    def render(self):
        return self.env.render()
