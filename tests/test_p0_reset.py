"""Regression test for deterministic, non-destructive environment reset (P0-08)."""

from utils import create_env_config, create_market_config
from src.environment.lem import LocalEnergyMarket
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.profile.der import DERProfileHandler


def test_reset_preserves_configured_profiles_and_distinguishes_agents() -> None:
    config = create_env_config(
        max_steps=24,
        num_agents=2,
        market_config=create_market_config(min_price=0.0, max_price=100.0, min_quantity=0.0, max_quantity=100.0),
    )
    config["agents"][0].generation_profile = [1.0] * 24
    config["agents"][0].demand_profile = [2.0] * 24
    config["agents"][1].generation_profile = [3.0] * 24
    config["agents"][1].demand_profile = [4.0] * 24
    env = LocalEnergyMarket(config)

    env.reset(seed=19)
    first_reset = [(agent.generation_profile, agent.demand_profile, agent.reputation, agent.balance) for agent in env._agents.values()]
    env.reset(seed=19)
    second_reset = [(agent.generation_profile, agent.demand_profile, agent.reputation, agent.balance) for agent in env._agents.values()]

    assert first_reset == second_reset
    assert first_reset[0][0] == [1.0] * 24
    assert first_reset[1][0] == [3.0] * 24
    assert first_reset[0][2] != first_reset[1][2]
    assert all(balance == 0.0 for *_, balance in first_reset)


def test_grid_seed_does_not_mutate_global_numpy_rng_state() -> None:
    import numpy as np

    np.random.seed(123)
    expected = np.random.random()
    np.random.seed(123)
    GridNetwork(topology=GridTopology.MESH, num_nodes=3, seed=7)

    assert np.random.random() == expected


def test_profile_generation_does_not_mutate_global_numpy_rng_state() -> None:
    import numpy as np

    np.random.seed(123)
    expected = np.random.random()
    np.random.seed(123)
    DERProfileHandler(0.0, 10.0, seed=7).get_energy_profiles(4, 10.0)

    assert np.random.random() == expected
