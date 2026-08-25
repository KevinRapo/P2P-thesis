"""Regression tests for physical action feasibility (P0-02)."""

import numpy as np

from src.agent.der import DERAgent
from src.market.matching import MarketConfig


def _adjust(generation: float, demand: float, action: list[float]) -> np.ndarray:
    agent = DERAgent("agent", 20.0, generation_profile=[generation], demand_profile=[demand])
    return agent.adjust_action_for_battery(0, np.array(action), MarketConfig(
        min_price=0.0,
        max_price=100.0,
        min_quantity=1.0,
        max_quantity=20.0,
    ))


def test_sell_quantity_is_limited_by_generation_surplus() -> None:
    assert _adjust(10.0, 5.0, [20.0, -20.0])[1] == -5.0


def test_buy_quantity_is_limited_by_generation_deficit() -> None:
    assert _adjust(0.0, 5.0, [20.0, 20.0])[1] == 5.0


def test_infeasible_direction_returns_a_zero_quantity_no_order() -> None:
    assert _adjust(10.0, 5.0, [20.0, 20.0])[1] == 0.0
