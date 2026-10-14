"""Every probe: the basics a trainer relies on, whatever the probe teaches.

These check the environments only; nothing is trained. Each test loops over the
five probes and names the probe in its failure message.
"""

import numpy as np

from core.rl.envs.probes import PROBES
from probe_helpers import per_agent, same_action


def test_same_seed_gives_same_start():
    """Two resets with seed 42 give the same observations, so runs repeat exactly."""
    for probe_class in PROBES:
        env = probe_class({"n_agents": 3, "scramble_ids": True})
        first, _ = env.reset(seed=42)
        second, _ = env.reset(seed=42)
        print(f"{probe_class.__name__:>16}  1st: {per_agent(first)}")
        print(f"{'':>16}  2nd: {per_agent(second)}")

        for agent in env.agents_id:
            np.testing.assert_array_equal(
                first[agent],
                second[agent],
                err_msg=f"{probe_class.__name__}: {agent} starts differently",
            )


def test_every_agent_gets_an_observation_inside_its_space():
    """reset returns an observation and an info entry for each agent, and each
    observation lies inside the agent's observation space, Box(-1, 1)."""
    for probe_class in PROBES:
        env = probe_class({"n_agents": 3, "scramble_ids": True})
        obs, info = env.reset(seed=42)
        print(f"{probe_class.__name__:>16}  {per_agent(obs)}")

        name = probe_class.__name__
        assert set(obs) == set(info) == set(env.agents_id), f"{name}: agent missing"
        for agent in env.agents_id:
            space = env.observation_spaces[agent]
            assert space.contains(
                obs[agent]
            ), f"{name}: {agent} observes {obs[agent]}, outside {space}"


def test_episode_ends_after_its_length():
    """The episode runs exactly ``length`` steps (2 for DiscountProbe, else 1):
    every step before the last is not terminated, the last one is."""
    for probe_class in PROBES:
        env = probe_class({"n_agents": 3})
        env.reset(seed=42)
        ended = []
        for _ in range(env.length):
            *_, terminated, truncated, _ = env.step(same_action(env, 0.0))
            ended.append(terminated["__all__"])
            assert not truncated["__all__"], "probes end by termination"
        print(f"{probe_class.__name__:>16}  terminated after each step: {ended}")

        expected = [False] * (env.length - 1) + [True]
        assert ended == expected, f"{probe_class.__name__}: {ended} != {expected}"


def test_scrambled_ids_are_not_in_sorted_order():
    """With scramble_ids the agents' order in the environment differs from their
    sorted order. GroupedEnv sorts, RLlib does not, so the action and reward tests
    can catch an agent's data delivered to another agent."""
    env = PROBES[0]({"n_agents": 3, "scramble_ids": True})
    print(f"environment order: {list(env.agents_id)}")
    print(f"sorted order:      {sorted(env.agents_id)}")

    assert list(env.agents_id) != sorted(env.agents_id)
