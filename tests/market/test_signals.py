"""The observation signals (``core/market/signals.py``): the KPIs, market signals and
agent signals against numbers worked out by hand, the empty cases, and one real day.

Run with ``python -m pytest tests/market/test_signals.py -q`` in the ``marlem`` conda
env. The real-day tests load the SimBench network (~10 s).
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.config import store
from core.market import signals
from core.market.lem import LocalEnergyMarket
from core.market.order import Order, Trade

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"

KPI_NAMES = [
    "social_welfare",
    "liquidity",
    "bid_ask_spread",
    "price_volatility",
    "supply_demand_imbalance",
    "grid_congestion",
    "coordination_score",
    "coordination_convergence",
    "der_self_consumption",
    "flexibility_utilization",
]

MARKET_NAMES = [
    "step",
    "time_of_day",
    "clearing_price",
    "clearing_volume",
    "grid_balance",
    "dso_buy_volume",
    "dso_sell_volume",
    "dso_total_volume",
    "p2p_volume",
    "dso_trade_ratio",
    "net_grid_import",
    "dso_buy_price",
    "dso_sell_price",
    "mean_local_price",
    "price_spread",
    "local_price_advantage",
]
AGENT_NAMES = [
    "generation",
    "demand",
    "cumulative_demand_satisfied",
    "cumulative_demand_deferred",
    "remaining_demand",
    "cumulative_supply_satisfied",
    "cumulative_supply_deferred",
    "remaining_supply",
    "mean_profit",
    "reputation",
    "battery_energy",
    "battery_soc",
    "available_charge",
    "available_discharge",
    "cumulative_charge",
    "cumulative_discharge",
]


def order(agent: str, is_buy: bool, price: float, quantity: float) -> Order:
    return Order(f"o-{agent}", agent, price, quantity, is_buy, 0.0)


def trade(price: float, quantity: float, stage: int = 2) -> Trade:
    return Trade("b", "s", price, quantity, 0.0, stage=stage)


def step(orders=(), trades=(), price=0.5, loading=None, signal=None):
    """The parts of a ``StepRecord`` the KPIs read."""
    grid = SimpleNamespace(line_loading_percent=loading or {})
    graph = SimpleNamespace(line_loading_percent=signal) if signal else None
    return SimpleNamespace(
        orders=tuple(orders),
        trades=list(trades),
        clearing_price=price,
        grid=grid,
        signal=graph,
    )


def kpi(name: str, history) -> float:
    return signals.KPIS[name](history)


# --------------------------------------------------------------------------------------
# The registries
# --------------------------------------------------------------------------------------
def test_the_three_groups_list_the_papers_signals_in_its_order():
    assert list(signals.KPIS) == KPI_NAMES
    assert list(signals.MARKET_SIGNALS) == MARKET_NAMES
    assert list(signals.AGENT_SIGNALS) == AGENT_NAMES


def test_kpis_gives_every_kpi():
    found = signals.kpis([step(trades=[trade(0.2, 10.0)])])
    assert list(found) == KPI_NAMES and found["liquidity"] == 10.0


# --------------------------------------------------------------------------------------
# KPIs by hand
# --------------------------------------------------------------------------------------
def test_welfare_and_liquidity_add_up_every_trade_the_dso_s_too():
    history = [
        step(trades=[trade(0.2, 10.0), trade(0.1, 5.0)]),
        step(trades=[trade(0.3, 2.0, stage=3)]),
    ]
    assert kpi("social_welfare", history) == pytest.approx(2.0 + 0.5 + 0.6)
    assert kpi("liquidity", history) == pytest.approx(17.0)


def test_spread_is_the_mean_ask_minus_the_mean_bid():
    orders = [
        order("a", False, 0.1, 5.0),
        order("b", False, 0.3, 5.0),
        order("c", True, 0.4, 5.0),
    ]
    assert kpi("bid_ask_spread", [step(orders)]) == pytest.approx(0.2 - 0.4)
    assert math.isnan(kpi("bid_ask_spread", [step([order("a", True, 0.4, 1.0)])]))


def test_volatility_is_the_spread_of_the_clearing_price_over_the_steps_given():
    history = [step(price=1.0), step(price=3.0)]
    assert kpi("price_volatility", history) == pytest.approx(1.0)
    assert kpi("price_volatility", history[:1]) == 0.0


def test_imbalance_adds_the_steps_so_a_surplus_does_not_cancel_a_deficit():
    surplus = step([order("a", False, 0.1, 10.0), order("b", True, 0.4, 4.0)])
    deficit = step([order("a", False, 0.1, 4.0), order("b", True, 0.4, 10.0)])
    assert kpi("supply_demand_imbalance", [surplus]) == pytest.approx(6.0 / 14.0)
    both = kpi("supply_demand_imbalance", [surplus, deficit])
    assert both == pytest.approx(12.0 / 28.0)  # not |0| / 28
    assert kpi("coordination_score", [surplus, deficit]) == pytest.approx(1 - both)


def test_convergence_is_the_spread_of_the_score_over_the_steps_with_orders():
    even = step([order("a", False, 0.1, 5.0), order("b", True, 0.4, 5.0)])  # 1.0
    gap = step([order("a", False, 0.1, 10.0)])  # 0.0
    quiet = step()  # no orders: left out
    assert kpi("coordination_convergence", [even, gap, quiet]) == pytest.approx(0.5)
    assert kpi("coordination_convergence", [even]) == 0.0


def test_self_consumption_is_the_peer_share_of_the_energy_traded():
    trades = [trade(0.2, 6.0, stage=1), trade(0.2, 2.0, stage=2)]
    trades.append(trade(0.3, 2.0, stage=3))
    assert kpi("der_self_consumption", [step(trades=trades)]) == pytest.approx(0.8)


def test_flexibility_is_the_peer_energy_over_the_energy_offered():
    orders = [order("a", False, 0.1, 10.0), order("b", False, 0.1, 6.0)]
    orders.append(order("c", True, 0.4, 8.0))
    history = [step(orders, [trade(0.2, 8.0), trade(0.3, 2.0, stage=3)])]
    assert kpi("flexibility_utilization", history) == pytest.approx(0.5)


def test_congestion_is_the_mean_loading_as_a_ratio():
    loaded = step(loading={"a": 50.0, "b": 100.0})
    assert kpi("grid_congestion", [loaded]) == pytest.approx(0.75)
    both = kpi("grid_congestion", [loaded, step(loading={"a": 25.0})])
    assert both == pytest.approx((0.75 + 0.25) / 2)


def test_congestion_reads_the_loading_the_fees_used_and_skips_steps_without():
    graph = step(loading={"a": 90.0}, signal={"a": 20.0})
    assert kpi("grid_congestion", [graph]) == pytest.approx(0.2)
    assert math.isnan(kpi("grid_congestion", [step()]))


@pytest.mark.parametrize("history", [[], [step()]])
def test_nothing_to_measure_is_nan_and_sums_are_zero(history):
    found = signals.kpis(history)
    assert found["social_welfare"] == 0.0 and found["liquidity"] == 0.0
    for name in KPI_NAMES[2:]:
        if name == "price_volatility" and history:
            continue  # one clearing price: no spread, so 0
        assert math.isnan(found[name]), name


# --------------------------------------------------------------------------------------
# Market signals by hand
# --------------------------------------------------------------------------------------
def market_after_one_step(**record):
    last = SimpleNamespace(
        p2p_kwh=8.0,
        dso_kwh=2.0,
        grid_balance_kwh=3.0,
        dso=SimpleNamespace(bought_kwh=1.5, sold_kwh=0.5),
        trades=[trade(0.15, 8.0), trade(0.3, 2.0, stage=3)],
    )
    last.__dict__.update(record)
    return SimpleNamespace(
        history=[last],
        current_step=1,
        n_steps=4,
        clearing_price=0.15,
        dso=SimpleNamespace(feed_in_tariff=0.1, utility_price=0.3),
    )


def test_market_signals_of_the_last_step():
    found = signals.market_signals(market_after_one_step())
    assert found["step"] == 1 and found["time_of_day"] == 0.25
    assert found["clearing_price"] == 0.15 and found["clearing_volume"] == 10.0
    assert found["grid_balance"] == 3.0
    assert (found["dso_buy_volume"], found["dso_sell_volume"]) == (1.5, 0.5)
    assert found["dso_total_volume"] == 2.0 and found["p2p_volume"] == 8.0
    assert found["dso_trade_ratio"] == pytest.approx(0.2)
    assert found["net_grid_import"] == pytest.approx(0.5 - 1.5)
    assert (found["dso_buy_price"], found["dso_sell_price"]) == (0.1, 0.3)
    assert found["mean_local_price"] == pytest.approx(0.15)
    assert found["price_spread"] == pytest.approx(0.2)
    assert found["local_price_advantage"] == pytest.approx(0.2 - 0.15)


def test_market_signals_before_the_first_step_are_nan_but_the_tariffs():
    market = market_after_one_step()
    market.history, market.current_step = [], 0
    found = signals.market_signals(market)
    assert found["step"] == 0 and found["price_spread"] == pytest.approx(0.2)
    for name in ("clearing_volume", "grid_balance", "p2p_volume", "mean_local_price"):
        assert math.isnan(found[name]), name


def test_without_peer_trades_there_is_no_local_price():
    only_dso = {"p2p_kwh": 0.0, "trades": [trade(0.3, 2.0, stage=3)]}
    found = signals.market_signals(market_after_one_step(**only_dso))
    assert math.isnan(found["mean_local_price"])
    assert math.isnan(found["local_price_advantage"])
    assert found["dso_trade_ratio"] == 1.0


# --------------------------------------------------------------------------------------
# Agent signals by hand
# --------------------------------------------------------------------------------------
def outcome():
    return SimpleNamespace(
        satisfied_demand_kwh=3.0,
        deferred_demand_kwh=1.0,
        satisfied_supply_kwh=0.5,
        deferred_supply_kwh=1.5,
        profit=2.0,
        charge_kwh=1.0,
        discharge_kwh=0.5,
    )


def agent_market(played=1, battery=True):
    participant = SimpleNamespace(
        generation_kwh=[1.0, 2.0, 3.0, 4.0],
        demand_kwh=[4.0, 3.0, 2.0, 1.0],
        reputation=0.7,
        battery=SimpleNamespace(energy_kwh=5.0, soc=0.5) if battery else None,
        battery_room=lambda: (3.0, 2.0) if battery else (0.0, 0.0),
    )
    history = [SimpleNamespace(participants={"a": outcome()}) for _ in range(played)]
    return SimpleNamespace(
        history=history, current_step=played, n_steps=4, participants={"a": participant}
    )


def test_agent_signals_after_one_step():
    found = signals.agent_signals(agent_market(), "a")
    assert (found["generation"], found["demand"]) == (2.0, 3.0)
    assert found["remaining_demand"] == 6.0 and found["remaining_supply"] == 9.0
    assert found["cumulative_demand_satisfied"] == 3.0
    assert found["cumulative_demand_deferred"] == 1.0
    assert found["cumulative_supply_satisfied"] == 0.5
    assert found["cumulative_supply_deferred"] == 1.5
    assert found["mean_profit"] == 2.0 and found["reputation"] == 0.7
    assert (found["battery_energy"], found["battery_soc"]) == (5.0, 0.5)
    assert (found["available_charge"], found["available_discharge"]) == (3.0, 2.0)
    assert (found["cumulative_charge"], found["cumulative_discharge"]) == (1.0, 0.5)


def test_cumulative_signals_add_up_and_profit_is_the_mean():
    found = signals.agent_signals(agent_market(played=3), "a")
    assert found["cumulative_demand_satisfied"] == 9.0
    assert found["cumulative_charge"] == 3.0 and found["mean_profit"] == 2.0


def test_before_the_first_step_profit_is_nan_and_nothing_is_added():
    found = signals.agent_signals(agent_market(played=0), "a")
    assert math.isnan(found["mean_profit"])
    assert found["cumulative_charge"] == 0.0 and found["remaining_demand"] == 10.0


def test_without_a_battery_every_battery_signal_is_zero():
    found = signals.agent_signals(agent_market(battery=False), "a")
    for name in ("battery_energy", "battery_soc", "available_charge"):
        assert found[name] == 0.0, name


def test_after_the_day_the_profile_is_the_last_steps_and_nothing_remains():
    found = signals.agent_signals(agent_market(played=4), "a")
    assert (found["generation"], found["demand"]) == (4.0, 1.0)
    assert found["remaining_demand"] == 0.0 and found["remaining_supply"] == 0.0


# --------------------------------------------------------------------------------------
# One real day
# --------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def day():
    market = LocalEnergyMarket(store.load(SCENARIO))
    market.reset()
    market.run_to_end()
    return market


def test_a_day_of_the_market_gives_sound_kpis(day):
    found = signals.kpis(day.history)
    assert list(found) == KPI_NAMES
    assert found["liquidity"] == pytest.approx(
        sum(r.p2p_kwh + r.dso_kwh for r in day.history)
    )
    assert found["social_welfare"] > 0.0
    for name in (
        "supply_demand_imbalance",
        "coordination_score",
        "der_self_consumption",
        "flexibility_utilization",
    ):
        assert 0.0 <= found[name] <= 1.0, name
    assert found["coordination_score"] == pytest.approx(
        1.0 - found["supply_demand_imbalance"]
    )
    p2p = sum(r.p2p_kwh for r in day.history)
    assert found["der_self_consumption"] == pytest.approx(p2p / found["liquidity"])
    assert found["grid_congestion"] >= 0.0
    # one step on its own is the same call on a slice
    assert signals.kpis(day.history[:1])["liquidity"] == pytest.approx(
        day.history[0].p2p_kwh + day.history[0].dso_kwh
    )


def test_a_day_gives_consistent_market_and_agent_signals():
    market = LocalEnergyMarket(store.load(SCENARIO))
    market.reset()
    market.run_to_end()
    found = signals.market_signals(market)
    assert list(found) == MARKET_NAMES and found["time_of_day"] == 1.0
    assert found["p2p_volume"] == pytest.approx(market.history[-1].p2p_kwh)
    for agent, p in market.participants.items():
        a = signals.agent_signals(market, agent)
        assert list(a) == AGENT_NAMES
        demand = a["cumulative_demand_satisfied"] + a["cumulative_demand_deferred"]
        supply = a["cumulative_supply_satisfied"] + a["cumulative_supply_deferred"]
        assert demand == pytest.approx(sum(p.demand_kwh))
        assert supply == pytest.approx(sum(p.generation_kwh))
        assert 0.0 <= a["battery_soc"] <= 1.0
