"""Regression test for episode transition count (P0-07)."""

import numpy as np

from utils import create_env_config, create_market_config
from src.environment.lem import LocalEnergyMarket


def test_episode_executes_exactly_max_steps_transitions() -> None:
    config = create_env_config(
        max_steps=4,
        num_agents=2,
        market_config=create_market_config(min_price=0.0, max_price=1.0, min_quantity=0.0, max_quantity=100.0),
    )
    for agent in config["agents"]:
        agent.generation_profile = agent.generation_profile[:4]
        agent.demand_profile = agent.demand_profile[:4]
    env = LocalEnergyMarket(config)
    env.reset(seed=7)
    actions = {agent_id: np.array([0.5, 0.0], dtype=np.float32) for agent_id in env.agents_id}
    assert all(space.shape == (2,) for space in env.action_spaces.values())

    for step in range(4):
        _, _, terminated, _, infos = env.step(actions)
        assert terminated["__all__"] is (step == 3)
        assert infos[env.agents_id[0]]["orders"] == []

    assert env.current_step == 4
