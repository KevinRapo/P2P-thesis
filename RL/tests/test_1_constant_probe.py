"""Probe 1, ConstantProbe: observation 0, one step, reward +1.

Teaches the critic the simplest value there is: V = 1. If training fails here,
the value loss or the optimiser is broken.
"""

from RL.core.envs.probes import ConstantProbe
from probe_helpers import per_agent, same_action


def test_observation_is_always_0():
    """Every agent sees 0: there is nothing to learn from the observation."""
    env = ConstantProbe({"n_agents": 3})
    obs, _ = env.reset(seed=42)
    print(f"observations: {per_agent(obs)}")

    assert all(float(o[0]) == 0.0 for o in obs.values())


def test_reward_is_1_whatever_the_action():
    """Every agent gets reward 1 for any action (-1, 0 or 1 tried), so the value
    to learn is V = 1."""
    env = ConstantProbe({"n_agents": 3})
    for action in (-1.0, 0.0, 1.0):
        env.reset(seed=42)
        _, rewards, *_ = env.step(same_action(env, action))
        print(f"action {action:>4} -> rewards: {per_agent(rewards)}")

        assert all(r == 1.0 for r in rewards.values()), f"action {action}: {rewards}"
