"""Golden monotonic reward regressions (P1-06)."""

import pytest

from src.agent.der import DERAgent
from src.environment.reward import RewardHandler
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.dso import DSOAgent
from src.market.matching import MatchingResult
from src.market.order import Order, Trade


def _handler() -> RewardHandler:
    grid = GridNetwork(GridTopology.LINE, num_nodes=2, capacity=10.0)
    return RewardHandler(DSOAgent("DSO", [0.1], [0.2], grid), grid)


def _result(trades=(), congestion=0.0) -> MatchingResult:
    return MatchingResult(list(trades), [], 1.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                          0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, congestion)


def test_unserved_energy_loss_and_constraint_each_reduce_reward() -> None:
    handler = _handler()
    agent = DERAgent("buyer", 1.0, demand_profile=[1.0], generation_profile=[0.0])
    order = Order("buy", "buyer", 1.0, 1.0, True, 0.0)
    filled = _result([Trade("buyer", "seller", 1.0, 1.0, 0.0)])
    lost = _result([Trade("buyer", "seller", 1.0, 1.0, 0.0, transmission_loss=0.5)])

    assert handler.calculate_reward(agent, order, filled, {}, 0.0, 2.0) > handler.calculate_reward(agent, order, _result(), {}, 0.0, 2.0)
    assert handler.calculate_reward(agent, order, lost, {}, 0.0, 2.0) < handler.calculate_reward(agent, order, filled, {}, 0.0, 2.0)
    assert handler.calculate_reward(agent, order, filled, {}, 0.0, 2.0) > handler.calculate_reward(agent, order, _result([filled.trades[0]], congestion=1.0), {}, 0.0, 2.0)


def test_reward_is_invariant_to_equivalent_energy_display_units() -> None:
    handler = _handler()
    agent = DERAgent("buyer", 1.0, demand_profile=[1.0], generation_profile=[0.0])
    kwh_order = Order("kwh", "buyer", 1.0, 1.0, True, 0.0)
    wh_order = Order("wh", "buyer", 0.001, 1000.0, True, 0.0)
    kwh = handler.calculate_reward(agent, kwh_order, _result([Trade("buyer", "seller", 1.0, 1.0, 0.0)]), {}, 0.0, 2.0)
    wh = handler.calculate_reward(agent, wh_order, _result([Trade("buyer", "seller", 0.001, 1000.0, 0.0)]), {}, 0.0, 0.002)

    assert wh == pytest.approx(kwh)
