"""Probe 2, ObservationProbe: observation +1 or -1 per agent, one step, reward =
the agent's own observation.

Teaches the critic V(o) = o. If training fails here, observations do not reach
the value network, or reach it for the wrong agent.
"""

from core.rl.envs.probes import ObservationProbe
from probe_helpers import per_agent, same_action


def test_observations_are_plus_or_minus_1():
    """Each agent sees +1 or -1, drawn at random on each reset."""
    env = ObservationProbe({"n_agents": 3})
    seen = set()

    for seed in range(20):
        obs, _ = env.reset(seed=seed)
        seen |= {float(o[0]) for o in obs.values()}

    print(f"values seen over 20 resets: {sorted(seen)}")

    assert seen == {-1.0, 1.0}


def test_reward_equals_the_agents_own_observation():
    """Each agent's reward is its own observation, not another agent's."""
    env = ObservationProbe({"n_agents": 3, "scramble_ids": True})
    obs, _ = env.reset(seed=42)
    _, rewards, *_ = env.step(same_action(env, 0.0))
    print(f"observations: {per_agent(obs)}")
    print(f"rewards:      {per_agent(rewards)}")

    for agent in env.agents_id:
        assert rewards[agent] == float(
            obs[agent][0]
        ), f"{agent}: observed {obs[agent][0]}, got reward {rewards[agent]}"
