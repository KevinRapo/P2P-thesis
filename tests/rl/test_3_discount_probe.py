"""Probe 3, DiscountProbe: two steps, observation 0 then 1, reward +1 only at the
end.

Teaches the critic discounting: V(1) = 1 and V(0) = gamma, since the reward
comes one step later. If training fails here, discounting or the handling of the
episode end is broken.
"""

from core.rl.envs.probes import DiscountProbe
from probe_helpers import per_agent, same_action


def test_observation_counts_the_steps_0_then_1():
    """Observation 0 on the first step and 1 on the second: the agents can tell
    the two steps apart, which a different value per step requires."""
    env = DiscountProbe({"n_agents": 3})
    first, _ = env.reset(seed=42)
    second, *_ = env.step(same_action(env, 0.0))
    print(f"step 1 observations: {per_agent(first)}")
    print(f"step 2 observations: {per_agent(second)}")

    assert all(float(o[0]) == 0.0 for o in first.values())
    assert all(float(o[0]) == 1.0 for o in second.values())


def test_first_step_pays_nothing():
    """Step 1 pays 0, so the value at the start is only the discounted reward
    still to come: V(0) = gamma * 1, not 1."""
    env = DiscountProbe({"n_agents": 3})
    env.reset(seed=42)
    _, rewards, terminated, *_ = env.step(same_action(env, 0.0))
    print(
        f"step 1 rewards: {per_agent(rewards)}, episode over: {terminated['__all__']}"
    )

    assert all(r == 0.0 for r in rewards.values()), f"rewards: {rewards}"
    assert not terminated["__all__"], "the episode ended after step 1"


def test_last_step_pays_1_and_ends_the_episode():
    """Step 2 pays 1 and ends the episode, so V(1) = 1 with nothing after it."""
    env = DiscountProbe({"n_agents": 3})
    env.reset(seed=42)
    env.step(same_action(env, 0.0))
    _, rewards, terminated, *_ = env.step(same_action(env, 0.0))
    print(
        f"step 2 rewards: {per_agent(rewards)}, episode over: {terminated['__all__']}"
    )

    assert all(r == 1.0 for r in rewards.values()), f"rewards: {rewards}"
    assert terminated["__all__"], "the episode did not end after step 2"
