"""Scripted controllers on plain data: no market, no grid, no engine."""

import pytest

from src_thesis.marlem.core.policy import AgentView, Intent
from src_thesis.marlem.policies.registry import get_policy, names


def view(agent_id="a", generation=5.0, demand=2.0, min_quantity=0.0) -> AgentView:
    return AgentView(
        agent_id=agent_id,
        step=0,
        generation_kwh=generation,
        demand_kwh=demand,
        fit=0.1,
        utility_price=0.3,
        min_price=0.0,
        max_price=1.0,
        min_quantity=min_quantity,
        max_quantity=100.0,
    )


def test_no_order_is_silent_or_unmatchable() -> None:
    policy = get_policy("no_order")
    assert policy.act({"a": view()})["a"].quantity_kwh == 0.0
    forced = policy.act({"a": view(min_quantity=1.0)})["a"]
    assert forced.quantity_kwh == 1.0 and forced.price == 1.0 and not forced.is_buy


def test_net_position_sells_a_surplus_and_buys_a_deficit() -> None:
    views = {"seller": view("seller", 5, 2), "buyer": view("buyer", 1, 4)}
    out = get_policy("net_position").act(views)
    assert out["seller"] == Intent(pytest.approx(0.2), 3.0, False)
    assert out["buyer"] == Intent(pytest.approx(0.2), 3.0, True)
    assert get_policy("net_position").act({"x": view("x", 2, 2)})["x"].quantity_kwh == 0


def test_aggressiveness_moves_prices_to_the_dso_prices() -> None:
    views = {"seller": view("seller", 5, 2), "buyer": view("buyer", 1, 4)}
    out = get_policy("net_position", aggressiveness=1.0).act(views)
    assert out["seller"].price == pytest.approx(0.1)  # the feed-in tariff
    assert out["buyer"].price == pytest.approx(0.3)  # the utility price


def test_random_orders_are_reproducible_and_within_bounds() -> None:
    views = {"a": view("a"), "b": view("b")}
    first, second = get_policy("random"), get_policy("random")
    first.reset(7)
    second.reset(7)
    a, b = first.act(views), second.act(views)
    assert a == b
    for intent in a.values():
        assert 0.0 <= intent.price <= 1.0 and 0.0 <= intent.quantity_kwh <= 100.0
    second.reset(8)
    assert second.act(views) != a


def test_registry_rejects_bad_names_and_parameters() -> None:
    assert {"no_order", "random", "net_position"} <= set(names())
    with pytest.raises(ValueError, match="Unknown controller"):
        get_policy("nope")
    with pytest.raises(ValueError, match="no parameter"):
        get_policy("random", speed=1)
    with pytest.raises(ValueError, match="between"):
        get_policy("net_position", aggressiveness=2)
