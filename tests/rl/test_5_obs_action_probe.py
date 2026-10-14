"""Probe 5, ObsActionProbe: observation +1 or -1 per agent, one step, reward
1 - (a_i - o_i / 2)^2.

Teaches the policy to act on its own observation: action mean = o_i / 2. If
training fails here, the policy does not use the observation, or uses another
agent's.
"""

import numpy as np
import pytest

from core.rl.envs.probes import ObsActionProbe
from probe_helpers import per_agent, same_action


def test_reward_is_1_at_half_the_observation():
    """Each agent acting at half its own observation gets the best reward, 1."""
    env = ObsActionProbe({"n_agents": 3, "scramble_ids": True})
    obs, _ = env.reset(seed=42)
    actions = {agent: o / 2 for agent, o in obs.items()}
    _, rewards, *_ = env.step(actions)
    print(f"observations: {per_agent(obs)}")
    print(f"actions:      {per_agent(actions)}")
    print(f"rewards:      {per_agent(rewards)}")

    assert all(r == pytest.approx(1.0) for r in rewards.values()), f"{rewards}"


def test_ignoring_the_observation_costs_reward():
    """Acting 0 whatever the observation gives 1 - 0.5^2 = 0.75: a policy that
    ignores its observation cannot reach the best reward."""
    env = ObsActionProbe({"n_agents": 3})
    env.reset(seed=42)
    _, rewards, *_ = env.step(same_action(env, 0.0))
    print(f"action 0 -> rewards: {per_agent(rewards)}")

    assert all(r == pytest.approx(0.75) for r in rewards.values()), f"{rewards}"


def test_acting_on_another_agents_observation_costs_reward():
    """Agents with opposite observations that swap actions are each 1 off their
    best action: reward 1 - 1^2 = 0."""
    env = ObsActionProbe({"n_agents": 3, "scramble_ids": True})
    for seed in range(100):
        obs, _ = env.reset(seed=seed)
        plus = [a for a in env.agents_id if obs[a][0] > 0]
        minus = [a for a in env.agents_id if obs[a][0] < 0]
        if plus and minus:
            break
    a, b = plus[0], minus[0]
    actions = {agent: o / 2 for agent, o in obs.items()}
    actions[a], actions[b] = actions[b], actions[a]
    _, rewards, *_ = env.step(actions)
    print(f"seed {seed}, observations: {per_agent(obs)}")
    print(f"{a} and {b} swap actions -> rewards: {per_agent(rewards)}")

    assert rewards[a] == pytest.approx(0.0)
    assert rewards[b] == pytest.approx(0.0)
    assert np.isclose([rewards[x] for x in env.agents_id if x not in (a, b)], 1.0).all()
