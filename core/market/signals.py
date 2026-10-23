"""The paper's observation signals ([P1] Table 2, [P2] Table 5), in three groups:

    KPIS             10 implicit-cooperation KPIs, eq. 19-27   f(history)
    MARKET_SIGNALS   16 market signals, public                 f(market)
    AGENT_SIGNALS    16 agent signals, private                 f(market, agent)

KPIs take the steps to measure: ``market.history``, or a slice of it. Market and agent
signals read the market now, after its last step. NaN when there is nothing to
measure (no trades, no orders, no step played yet).
"""

from __future__ import annotations

import statistics

NAN = float("nan")


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _ratio(a: float, b: float) -> float:
    return a / b if b > 0 else NAN


def _trades(history):
    return [t for r in history for t in r.trades]


def _p2p_kwh(history) -> float:
    return sum(t.quantity for t in _trades(history) if t.stage < 3)


def _imbalance(history) -> float:
    # OPEN E-08, E-11: over each step's orders (over trades it is always 0), with the
    # order volume standing in for C_grid.
    gap = total = 0.0
    for r in history:
        buy = sum(o.quantity for o in r.orders if o.is_buy)
        sell = sum(o.quantity for o in r.orders if not o.is_buy)
        gap += abs(buy - sell)
        total += buy + sell
    return _ratio(gap, total)


def _last(market):
    """The last step played, or None before the first."""
    return market.history[-1] if market.history else None


def _played(market, agent: str, field: str) -> float:
    """``field`` of the agent's outcome, added up over the steps played."""
    return sum(getattr(r.participants[agent], field) for r in market.history)


def _now(market) -> int:
    """The step about to be played (the last one after the day's end)."""
    return min(market.current_step, market.n_steps - 1)


# --------------------------------------------------------------------------------------
# KPIs: the steps given -> a number
# --------------------------------------------------------------------------------------
def social_welfare(history) -> float:
    # OPEN E-09: the paper's sum of p x q (turnover), not surplus.
    return sum(t.price * t.quantity for t in _trades(history))


def liquidity(history) -> float:
    # OPEN MP-6a: the DSO's trades count too.
    return sum(t.quantity for t in _trades(history))


def bid_ask_spread(history) -> float:
    """Mean ask price minus mean bid price."""
    asks = [o.price for r in history for o in r.orders if not o.is_buy]
    bids = [o.price for r in history for o in r.orders if o.is_buy]

    return statistics.fmean(asks) - statistics.fmean(bids) if asks and bids else NAN


def price_volatility(history) -> float:
    """Standard deviation of the clearing price."""
    # OPEN E-10: the window is the history given.
    prices = [r.clearing_price for r in history]
    return statistics.pstdev(prices) if prices else NAN


def supply_demand_imbalance(history) -> float:
    return _imbalance(history)


def grid_congestion(history) -> float:
    """Mean line loading as a ratio, from the loading the fees used."""
    means = [
        statistics.fmean(loading.values()) / 100.0
        for r in history
        if (loading := (r.signal or r.grid).line_loading_percent)
    ]
    return statistics.fmean(means) if means else NAN


def coordination_score(history) -> float:
    return 1.0 - _imbalance(history)


def coordination_convergence(history) -> float:
    """Standard deviation of the per-step coordination score."""
    # OPEN MP-6a: not defined in [P1].
    scores = [s for r in history if (s := 1.0 - _imbalance([r])) == s]
    return statistics.pstdev(scores) if scores else NAN


def der_self_consumption(history) -> float:
    # OPEN E-12: the peer share of the energy traded, not self-consumption.
    return _ratio(_p2p_kwh(history), liquidity(history))


def flexibility_utilization(history) -> float:
    # OPEN MP-6a: q_available undefined; the energy offered stands in.
    offered = sum(o.quantity for r in history for o in r.orders if not o.is_buy)
    return _ratio(_p2p_kwh(history), offered)


KPIS = {
    "social_welfare": social_welfare,
    "liquidity": liquidity,
    "bid_ask_spread": bid_ask_spread,
    "price_volatility": price_volatility,
    "supply_demand_imbalance": supply_demand_imbalance,
    "grid_congestion": grid_congestion,
    "coordination_score": coordination_score,
    "coordination_convergence": coordination_convergence,
    "der_self_consumption": der_self_consumption,
    "flexibility_utilization": flexibility_utilization,
}


# --------------------------------------------------------------------------------------
# Market signals: the market now -> a number
# --------------------------------------------------------------------------------------
def step(market) -> float:
    return float(market.current_step)


def time_of_day(market) -> float:
    """Share of the day gone by, 0 to 1."""
    return market.current_step / market.n_steps


def clearing_price(market) -> float:
    """Volume-weighted price of the last peer trades (carried over without any)."""
    return float(market.clearing_price)


def clearing_volume(market) -> float:
    # OPEN MP-6a: the DSO's trades count too, as in the original (M-15).
    r = _last(market)
    return r.p2p_kwh + r.dso_kwh if r else NAN


def grid_balance(market) -> float:
    """B_grid before the DSO clears (eq. 20): energy offered minus asked."""
    r = _last(market)
    return r.grid_balance_kwh if r else NAN


def dso_buy_volume(market) -> float:
    r = _last(market)
    return r.dso.bought_kwh if r else NAN


def dso_sell_volume(market) -> float:
    r = _last(market)
    return r.dso.sold_kwh if r else NAN


def dso_total_volume(market) -> float:
    r = _last(market)
    return r.dso_kwh if r else NAN


def p2p_volume(market) -> float:
    r = _last(market)
    return r.p2p_kwh if r else NAN


def dso_trade_ratio(market) -> float:
    """The DSO's share of the energy traded."""
    r = _last(market)
    return _ratio(r.dso_kwh, r.dso_kwh + r.p2p_kwh) if r else NAN


def net_grid_import(market) -> float:
    # OPEN MP-6a: the market's figure (DSO sold minus bought); the power flow's
    # external_grid_kwh is the physical one.
    r = _last(market)
    return r.dso.sold_kwh - r.dso.bought_kwh if r else NAN


def dso_buy_price(market) -> float:
    return float(market.dso.feed_in_tariff)


def dso_sell_price(market) -> float:
    return float(market.dso.utility_price)


def mean_local_price(market) -> float:
    """Volume-weighted price of the last step's peer trades; NaN without any."""
    r = _last(market)
    p2p = [t for t in r.trades if t.stage < 3] if r else []
    value = sum(t.price * t.quantity for t in p2p)

    return _ratio(value, sum(t.quantity for t in p2p))


def price_spread(market) -> float:
    """Utility price minus feed-in tariff: the room peers trade in."""
    return dso_sell_price(market) - dso_buy_price(market)


def local_price_advantage(market) -> float:
    """The tariffs' midpoint minus the local price; > 0 when trading locally pays."""
    return (dso_buy_price(market) + dso_sell_price(market)) / 2 - mean_local_price(
        market
    )


MARKET_SIGNALS = {
    "step": step,
    "time_of_day": time_of_day,
    "clearing_price": clearing_price,
    "clearing_volume": clearing_volume,
    "grid_balance": grid_balance,
    "dso_buy_volume": dso_buy_volume,
    "dso_sell_volume": dso_sell_volume,
    "dso_total_volume": dso_total_volume,
    "p2p_volume": p2p_volume,
    "dso_trade_ratio": dso_trade_ratio,
    "net_grid_import": net_grid_import,
    "dso_buy_price": dso_buy_price,
    "dso_sell_price": dso_sell_price,
    "mean_local_price": mean_local_price,
    "price_spread": price_spread,
    "local_price_advantage": local_price_advantage,
}


# --------------------------------------------------------------------------------------
# Agent signals: the market and one agent now -> a number
# --------------------------------------------------------------------------------------
def generation(market, agent: str) -> float:
    return market.participants[agent].generation_kwh[_now(market)]


def demand(market, agent: str) -> float:
    return market.participants[agent].demand_kwh[_now(market)]


def cumulative_demand_satisfied(market, agent: str) -> float:
    return _played(market, agent, "satisfied_demand_kwh")


def cumulative_demand_deferred(market, agent: str) -> float:
    return _played(market, agent, "deferred_demand_kwh")


def remaining_demand(market, agent: str) -> float:
    # OPEN E-05: the true future; [P1] has forecasts with up to 30 % error.
    return sum(market.participants[agent].demand_kwh[market.current_step :])


def cumulative_supply_satisfied(market, agent: str) -> float:
    return _played(market, agent, "satisfied_supply_kwh")


def cumulative_supply_deferred(market, agent: str) -> float:
    return _played(market, agent, "deferred_supply_kwh")


def remaining_supply(market, agent: str) -> float:
    # OPEN E-05: as remaining_demand.
    return sum(market.participants[agent].generation_kwh[market.current_step :])


def mean_profit(market, agent: str) -> float:
    """Profit per step played."""
    return _ratio(_played(market, agent, "profit"), len(market.history))


def reputation(market, agent: str) -> float:
    return float(market.participants[agent].reputation)


def battery_energy(market, agent: str) -> float:
    """0 without a battery, as are the other battery signals."""
    b = market.participants[agent].battery
    return b.energy_kwh if b else 0.0


def battery_soc(market, agent: str) -> float:
    """Share of the capacity."""
    b = market.participants[agent].battery
    return b.soc if b else 0.0


def available_charge(market, agent: str) -> float:
    """What the battery can still take this step (eq. 15d)."""
    return market.participants[agent].battery_room()[0]


def available_discharge(market, agent: str) -> float:
    """What the battery can still give this step (eq. 15c)."""
    return market.participants[agent].battery_room()[1]


def cumulative_charge(market, agent: str) -> float:
    return _played(market, agent, "charge_kwh")


def cumulative_discharge(market, agent: str) -> float:
    return _played(market, agent, "discharge_kwh")


AGENT_SIGNALS = {
    "generation": generation,
    "demand": demand,
    "cumulative_demand_satisfied": cumulative_demand_satisfied,
    "cumulative_demand_deferred": cumulative_demand_deferred,
    "remaining_demand": remaining_demand,
    "cumulative_supply_satisfied": cumulative_supply_satisfied,
    "cumulative_supply_deferred": cumulative_supply_deferred,
    "remaining_supply": remaining_supply,
    "mean_profit": mean_profit,
    "reputation": reputation,
    "battery_energy": battery_energy,
    "battery_soc": battery_soc,
    "available_charge": available_charge,
    "available_discharge": available_discharge,
    "cumulative_charge": cumulative_charge,
    "cumulative_discharge": cumulative_discharge,
}


# --------------------------------------------------------------------------------------
# All of a group at once
# --------------------------------------------------------------------------------------
def kpis(history) -> dict[str, float]:
    return {name: f(history) for name, f in KPIS.items()}


def market_signals(market) -> dict[str, float]:
    return {name: f(market) for name, f in MARKET_SIGNALS.items()}


def agent_signals(market, agent: str) -> dict[str, float]:
    return {name: f(market, agent) for name, f in AGENT_SIGNALS.items()}
