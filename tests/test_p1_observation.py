"""Regression tests for causal decentralized reset observations (P1-09)."""

from src.agent.der import DERAgent
from src.environment.observation import ObservationHandler
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.dso import DSOAgent
from src.market.matching import MarketConfig


def _reset_observation(generation: list[float], demand: list[float]):
    agent = DERAgent("agent", 10.0, generation_profile=generation, demand_profile=demand)
    grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2)
    dso = DSOAgent("DSO", [1.0, 1.0], [2.0, 2.0], grid)
    handler = ObservationHandler(2, [agent], dso, MarketConfig(max_price=10.0, max_quantity=10.0), grid)
    return handler.reset_observation_space()["agent"]


def test_reset_observation_uses_current_state_not_future_ground_truth() -> None:
    first = _reset_observation([3.0, 99.0], [4.0, 98.0])
    second = _reset_observation([3.0, 1.0], [4.0, 2.0])

    assert first.tolist() == second.tolist()
    assert first[16] == 3.0
    assert first[17] == 4.0
    assert first[20] == 0.0
    assert first[23] == 0.0


def test_decentralized_observation_does_not_expand_with_peer_reputations() -> None:
    agent = DERAgent("agent", 10.0, generation_profile=[3.0], demand_profile=[4.0])
    peer = DERAgent("peer", 10.0, generation_profile=[3.0], demand_profile=[4.0])
    grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2)
    dso = DSOAgent("DSO", [1.0], [2.0], grid)
    standard = ObservationHandler(1, [agent, peer], dso, MarketConfig(max_price=10.0, max_quantity=10.0), grid)
    requested_preference = ObservationHandler(1, [agent, peer], dso,
                                              MarketConfig(max_price=10.0, max_quantity=10.0,
                                                           enable_partner_preference=True), grid)

    assert standard.observation_space["agent"].shape == requested_preference.observation_space["agent"].shape
