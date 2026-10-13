"""Probe 4, ActionProbe: observation 0, one step, reward 1 - (a_i - t_i)^2, with
a different target t_i per agent.

Teaches the policy to output its own target: action mean = t_i. If training
fails here, the policy gradient is broken, or an agent's action reaches another
agent's reward.
"""

import numpy as np
import pytest

from RL.core.envs.probes import ActionProbe
from probe_helpers import per_agent


def _on_target(env):
    return {agent: np.array([t], dtype=np.float32) for agent, t in env.targets.items()}


def test_each_agent_has_its_own_target():
    """Targets -0.6, 0.0 and 0.6, in the environment's agent order (not sorted)."""
    env = ActionProbe({"n_agents": 3, "scramble_ids": True})
    print(f"targets: {per_agent(env.targets)}")

    assert env.targets == dict(zip(env.agents_id, [-0.6, 0.0, 0.6]))


def test_agent_on_its_target_gets_reward_1():
    """Every agent acting exactly on its target gets the best reward, 1."""
    env = ActionProbe({"n_agents": 3, "scramble_ids": True})
    env.reset(seed=42)
    _, rewards, *_ = env.step(_on_target(env))
    print(f"actions = targets: {per_agent(env.targets)}")
    print(f"rewards:           {per_agent(rewards)}")

    assert all(r == pytest.approx(1.0) for r in rewards.values()), f"{rewards}"


def test_rewards_follow_agent_ids_not_sorted_order():
    """Swapping the first and last agent's actions costs exactly those two
    agents: 1 - (0.6 - (-0.6))^2 = -0.44. The middle agent keeps reward 1."""
    env = ActionProbe({"n_agents": 3, "scramble_ids": True})
    env.reset(seed=42)
    actions = _on_target(env)
    first, middle, last = env.agents_id
    actions[first], actions[last] = actions[last], actions[first]
    _, rewards, *_ = env.step(actions)
    print(f"{first} and {last} swap actions -> rewards: {per_agent(rewards)}")

    assert rewards[first] == pytest.approx(-0.44)
    assert rewards[last] == pytest.approx(-0.44)
    assert rewards[middle] == pytest.approx(1.0)
