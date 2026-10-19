"""Acting with a trained module, baselines, and evaluation on held-out seeds.

One evaluation for every paradigm: episodes run in the original multi-agent
environment (never the grouped one), and returns are computed from its raw
per-agent rewards, so all nine combinations and the baselines are scored the
same way.

- Fixes L-15: a ``Policy`` acts as RLlib does in training: the module's action
  distribution, then RLlib's own ``unsquash_action`` from ``[-1, 1]`` to each
  agent's bounds. Infos are returned per agent, as the environment gives them.
- Fixes L-03: the team score is the sum over agents of the episode return, from
  the raw rewards; per-agent returns are reported next to it.
- Fixes L-16 and L-17 (the capability): random, constant and untrained policies
  on the same seeds, and evaluation seeds that training never uses.

``evaluation`` keeps every episode, not only the means: one row per policy, episode
and agent, one row per policy and episode, and, for the episodes asked for, one row
per step. It reads the environment's infos by this layout (any environment may
follow it; one that does not still gets its returns):

    infos[agent] = {
        <name>: amount over the step, of this agent    summed over the episode
        "state": {<name>: value at the step}           in the step rows only
        "shared": {<name>: amount over the step}       the same for every agent:
                                                       summed into the episode row
        "shared_state": {<name>: value at the step}    in the step rows only
    }

The infos of ``reset`` (e.g. the market's ``day``) are copied into every row of the
episode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd
import torch
from ray.rllib.core.columns import Columns
from ray.rllib.core.distribution.torch.torch_distribution import TorchSquashedGaussian
from ray.rllib.core.rl_module.apis import ValueFunctionAPI
from ray.rllib.utils.spaces.space_utils import unsquash_action

from core.rl.config import Paradigm
from core.rl.grouping import GROUP, central_obs, join, join_spaces, split

ActFn = Callable[[dict[str, np.ndarray]], dict[str, np.ndarray]]
# The nested parts of an agent's infos (see the module).
STATE, SHARED, SHARED_STATE = "state", "shared", "shared_state"


# --------------------------------------------------------------------------------------
# Policy: a trained module acting in the multi-agent environment
# --------------------------------------------------------------------------------------
def _deterministic(dist) -> torch.Tensor:
    """The distribution's most likely action, in the network's ``[-1, 1]`` units.

    RLlib's ``TorchSquashedGaussian.to_deterministic`` returns the mean *before*
    the tanh (Ray 2.51.1), so SAC's evaluation in RLlib would act with an
    unsquashed mean; squash it here as sampling does.
    """
    if isinstance(dist, TorchSquashedGaussian):
        unit = (torch.tanh(torch.as_tensor(dist.loc)) + 1.0) / 2.0
        return torch.clamp(
            dist.low + unit * (dist.high - dist.low), dist.low, dist.high
        )
    return dist.to_deterministic().sample()


class Policy:
    """Acts for every agent with the modules of one run.

    Args:
        modules (MultiRLModule): The run's modules (the learner's, with its critic).
        paradigm: How the modules map to agents: one per agent (DTDE, CTDE; under
            CTDE each also sees the global state) or one for the group (CTCE).
        env (MultiAgentEnv): The multi-agent environment (for agents and spaces).
    """

    def __init__(self, modules, paradigm: Paradigm | str, env) -> None:
        self.modules = modules
        self.paradigm = Paradigm(paradigm)
        self.agents = list(env.agents_id)
        self.act_spaces = {a: env.action_spaces[a] for a in self.agents}
        self.act_dims = [int(np.prod(self.act_spaces[a].shape)) for a in self.agents]
        self.joint_space = join_spaces([self.act_spaces[a] for a in self.agents])

    def _inputs(self, obs: dict) -> dict[str, np.ndarray]:
        """Each module's input: the agent's observation (DTDE), extended with the
        global state (CTDE), or all of them joined (CTCE)."""
        if self.paradigm == Paradigm.DTDE:
            return {a: np.asarray(obs[a], dtype=np.float32) for a in self.agents}
        if self.paradigm == Paradigm.CTDE:
            return central_obs(obs, self.agents)
        return {GROUP: join(obs, self.agents)}

    def _unit_actions(self, obs: dict, explore: bool) -> dict[str, np.ndarray]:
        """Each module's action in the network's units (before rescaling)."""
        out = {}
        with torch.no_grad():
            for mid, x in self._inputs(obs).items():
                module = self.modules[mid]
                batch = {Columns.OBS: torch.as_tensor(x).reshape(1, -1)}
                if explore:
                    logits = module.forward_exploration(batch)
                    dist_cls = module.get_exploration_action_dist_cls()
                else:
                    logits = module.forward_inference(batch)
                    dist_cls = module.get_inference_action_dist_cls()
                dist = dist_cls.from_logits(logits[Columns.ACTION_DIST_INPUTS])
                action = dist.sample() if explore else _deterministic(dist)
                out[mid] = action[0].numpy()
        return out

    def act(self, obs: dict, explore: bool = False) -> dict[str, np.ndarray]:
        """Each agent's action, in the environment's units.

        Args:
            obs: Each agent's observation.
            explore: Sample from the policy (as in training) instead of taking its
                most likely action.
        """
        unit = self._unit_actions(obs, explore)
        if self.paradigm != Paradigm.CTCE:
            return {
                a: np.asarray(unsquash_action(unit[a], self.act_spaces[a]), np.float32)
                for a in self.agents
            }
        joint = np.asarray(unsquash_action(unit[GROUP], self.joint_space), np.float32)
        return split(joint, self.agents, self.act_dims)

    def __call__(self, obs: dict) -> dict[str, np.ndarray]:
        return self.act(obs)

    def values(self, obs: dict) -> dict[str, float]:
        """Each module's value of the state: ``V`` (PPO, APPO) or, for SAC, the
        smaller twin ``Q`` at the policy's most likely action: per agent in DTDE and
        CTDE (each agent's own return), the group's in CTCE (the summed return)."""
        unit = self._unit_actions(obs, explore=False)
        out = {}
        with torch.no_grad():
            for mid, x in self._inputs(obs).items():
                module = self.modules[mid]
                batch = {Columns.OBS: torch.as_tensor(x).reshape(1, -1)}
                if isinstance(module, ValueFunctionAPI):
                    out[mid] = float(module.compute_values(batch)[0])
                else:
                    batch[Columns.ACTIONS] = torch.as_tensor(unit[mid]).reshape(1, -1)
                    out[mid] = float(module.compute_q_values(batch)[0])
        return out


# --------------------------------------------------------------------------------------
# Baselines
# --------------------------------------------------------------------------------------
def random_policy(env, seed: int = 0) -> ActFn:
    """Uniform random actions within each agent's bounds."""
    rng = np.random.default_rng(seed)

    def act(obs):
        return {
            a: rng.uniform(env.action_spaces[a].low, env.action_spaces[a].high).astype(
                np.float32
            )
            for a in env.agents_id
        }

    return act


def constant_policy(env, value: float = 0.0) -> ActFn:
    """The same action ``value`` for every agent and dimension, within bounds."""

    def act(obs):
        return {
            a: np.clip(
                np.full(env.action_spaces[a].shape, value, dtype=np.float32),
                env.action_spaces[a].low,
                env.action_spaces[a].high,
            )
            for a in env.agents_id
        }

    return act


# --------------------------------------------------------------------------------------
# Episodes and evaluation
# --------------------------------------------------------------------------------------
@dataclass
class Episode:
    """One episode in the multi-agent environment.

    Attributes:
        seed: The seed it was reset with.
        rewards: Each step's reward per agent.
        infos: Each step's infos per agent, as the environment returned them.
    """

    seed: int
    rewards: list[dict[str, float]] = field(default_factory=list)
    infos: list[dict[str, Any]] = field(default_factory=list)

    def returns(self) -> dict[str, float]:
        """Each agent's undiscounted return."""
        agents = self.rewards[0].keys() if self.rewards else []
        return {a: float(sum(step[a] for step in self.rewards)) for a in agents}

    def team_return(self) -> float:
        """The team score: the sum of the agents' returns."""
        return float(sum(self.returns().values()))


def rollout(
    env_class: type,
    env_config: dict,
    act: ActFn,
    seeds: list[int],
    max_steps: int = 100_000,
    options: Optional[Sequence[Optional[dict]]] = None,
) -> list[Episode]:
    """Run one episode per seed with ``act`` in the multi-agent environment.
    ``options`` are the ``reset`` options of each episode (e.g. the market's
    ``{"day": ...}``), one per seed."""
    env = env_class(env_config)
    episodes = []
    for seed, option in zip(seeds, options or [None] * len(seeds)):
        obs, infos = env.reset(seed=int(seed), options=option)
        episode = Episode(seed=int(seed), infos=[infos])
        for _ in range(max_steps):
            obs, rewards, terminateds, truncateds, infos = env.step(act(obs))
            episode.rewards.append({a: float(r) for a, r in rewards.items()})
            episode.infos.append(infos)
            if terminateds["__all__"] or truncateds["__all__"]:
                break
        episodes.append(episode)
    return episodes


def summarize(episodes: list[Episode]) -> dict[str, float]:
    """Mean and spread of the team score, and each agent's mean return."""
    team = np.array([e.team_return() for e in episodes])
    returns = [e.returns() for e in episodes]
    per_agent = {a: float(np.mean([r[a] for r in returns])) for a in returns[0]}
    return {
        "team_return_mean": float(team.mean()),
        "team_return_std": float(team.std()),
        "episodes": len(episodes),
        **{f"return/{a}": float(v) for a, v in per_agent.items()},
    }


@dataclass
class Evaluation:
    """Several policies scored on the same episodes (``evaluation``).

    Attributes:
        summary: One row per policy (``summarize``).
        agents: One row per policy, episode and agent: its return and the sums of
            its infos' amounts.
        episodes: One row per policy and episode: the team return and the sums of
            the shared amounts.
        trace_agents: For the traced episodes, one row per policy, episode, step
            and agent: reward, amounts and state (None if none was traced).
        trace_steps: For the traced episodes, one row per policy, episode and step:
            the team reward, shared amounts and shared state.
    """

    summary: pd.DataFrame
    agents: pd.DataFrame
    episodes: pd.DataFrame
    trace_agents: Optional[pd.DataFrame] = None
    trace_steps: Optional[pd.DataFrame] = None


def evaluation(
    env_class: type,
    env_config: dict,
    policies: dict[str, ActFn],
    seeds: list[int],
    options: Optional[Sequence[Optional[dict]]] = None,
    trace: Sequence[int] = (),
) -> Evaluation:
    """Score several policies on the same episodes (one per seed, with its
    ``reset`` options), keeping every episode; the episodes at the indices in
    ``trace`` are also kept step by step."""
    summary, agents, episodes, trace_agents, trace_steps = [], [], [], [], []
    for name, act in policies.items():
        played = rollout(env_class, env_config, act, seeds, options=options)
        summary.append({"policy": name, **summarize(played)})
        for index, episode in enumerate(played):
            head = {"policy": name, "episode": index, "seed": episode.seed}
            head |= _reset_fields(episode)
            episodes.append(head | _episode_row(episode))
            agents.extend(head | row for row in _agent_rows(episode))
            if index in trace:
                steps, per_agent = _trace_rows(episode)
                trace_steps.extend(head | row for row in steps)
                trace_agents.extend(head | row for row in per_agent)
    traced = bool(trace_steps)
    return Evaluation(
        pd.DataFrame(summary),
        pd.DataFrame(agents),
        pd.DataFrame(episodes),
        pd.DataFrame(trace_agents) if traced else None,
        pd.DataFrame(trace_steps) if traced else None,
    )


def evaluate(
    env_class: type,
    env_config: dict,
    policies: dict[str, ActFn],
    seeds: list[int],
) -> pd.DataFrame:
    """Score several policies on the same seeds; one row per policy."""
    return evaluation(env_class, env_config, policies, seeds).summary


def _reset_fields(episode: Episode) -> dict[str, Any]:
    """The plain values the first agent's ``reset`` infos give (e.g. ``day``)."""
    first = next(iter(episode.infos[0].values()), {}) if episode.infos else {}
    return {k: v for k, v in first.items() if isinstance(v, (str, int, float))}


def _amounts(info: dict) -> dict[str, float]:
    """The numbers at the top of an agent's infos (the nested parts left out)."""
    return {
        k: float(v)
        for k, v in info.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def _step_infos(episode: Episode) -> list[dict]:
    """Each step's infos (those of ``reset`` left out)."""
    return episode.infos[1:]


def _agent_rows(episode: Episode) -> list[dict[str, Any]]:
    returns = episode.returns()
    rows = []
    for agent, value in returns.items():
        sums: dict[str, float] = {}
        for infos in _step_infos(episode):
            for k, v in _amounts(infos.get(agent, {})).items():
                sums[k] = sums.get(k, 0.0) + v
        rows.append({"agent": agent, "return": value, **sums})
    return rows


def _episode_row(episode: Episode) -> dict[str, Any]:
    sums: dict[str, float] = {}
    for infos in _step_infos(episode):
        first = next(iter(infos.values()), {})
        for k, v in _amounts(first.get(SHARED, {})).items():
            sums[k] = sums.get(k, 0.0) + v
    return {"team_return": episode.team_return(), **sums}


def _trace_rows(episode: Episode) -> tuple[list[dict], list[dict]]:
    """The rows of one episode step by step: ``(steps, agents)``."""
    steps, agents = [], []
    for step, (rewards, infos) in enumerate(zip(episode.rewards, _step_infos(episode))):
        first = next(iter(infos.values()), {})
        steps.append(
            {"step": step, "team_reward": float(sum(rewards.values()))}
            | _amounts(first.get(SHARED, {}))
            | _amounts(first.get(SHARED_STATE, {}))
        )
        for agent, reward in rewards.items():
            info = infos.get(agent, {})
            agents.append(
                {"step": step, "agent": agent, "reward": reward}
                | _amounts(info)
                | _amounts(info.get(STATE, {}))
            )
    return steps, agents


def evaluation_seeds(n: int, start: int = 1_000_000) -> list[int]:
    """Seeds for evaluation episodes. Training resets with RLlib's run seed only
    once per sampler and lets the environment's generator run on, so seeds from
    ``start`` on are episodes training has not seen."""
    return list(range(start, start + n))


def baselines(env_class: type, env_config: dict, seed: int = 0) -> dict[str, ActFn]:
    """The policies every run is compared with: random and always 0."""
    env = env_class(env_config)
    return {"random": random_policy(env, seed), "zero": constant_policy(env, 0.0)}
