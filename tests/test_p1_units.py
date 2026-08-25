"""Regression test for explicit kW-to-kWh action conversion (P1-11)."""

from src.agent.der import DERAgent
from src.environment.action import ActionHandler
from src.environment.lem import LocalEnergyMarket
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.dso import DSOAgent
from src.market.matching import MarketConfig


def test_action_quantity_limit_scales_power_by_timestep_hours() -> None:
    agent = DERAgent("agent", 10.0, generation_profile=[0.0], demand_profile=[0.0])
    grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2)
    dso = DSOAgent("DSO", [1.0], [2.0], grid)
    handler = ActionHandler([agent], dso, MarketConfig(max_price=10.0, max_quantity=100.0), time_step_hours=0.25)

    assert handler.action_space["agent"].high[1] == 2.5


def test_power_profiles_convert_once_to_equivalent_step_energy() -> None:
    def environment(step_hours: float, profile: list[float]) -> LocalEnergyMarket:
        grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2)
        return LocalEnergyMarket({
            "max_steps": len(profile), "time_step_hours": step_hours,
            "profile_values_are_power": True,
            "market_config": MarketConfig(max_price=10.0, max_quantity=10.0),
            "grid_network": grid,
            "dso": DSOAgent("DSO", [1.0] * len(profile), [2.0] * len(profile), grid),
            "agents": [DERAgent("agent", 10.0, generation_profile=profile,
                                demand_profile=[0.0] * len(profile))],
        })

    quarter_hour = environment(0.25, [4.0] * 4)
    hour = environment(1.0, [4.0])

    assert sum(quarter_hour._agents["agent"].generation_profile) == 4.0
    assert sum(hour._agents["agent"].generation_profile) == 4.0
