"""The reward: what a played market step is worth to each agent.

``MarketEnv`` builds one ``Reward`` (``build_reward``), chosen by the ``reward`` setting
of its ``env_config``, and gives it each step's record. This file holds no market rule
(``core/market/`` stays the one place for those) and changes nothing: it only reads
what the market did.

    "bill"     ``NetBillReward``, the default
    "salazar"  ``SalazarReward``, the original code's reward

``net_bill`` stays the money an agent made, whichever reward it learns from: the infos
and the results report it.

"bill", per agent and step: the net energy bill, scaled,

    r = (profit − p_utility · deferred_demand) / reward_scale

``profit`` is eq. 14 for the step (revenue − cost of its trades − its grid fees);
p_utility is the step's (time-of-use tariffs change by hour).
``deferred_demand`` is the demand that generation, purchases and battery left
uncovered; it is drawn from the upstream grid untraded. Settlement leaves that
energy unpriced, so profit alone would make not buying free: an agent that
orders nothing would pay nothing for its imports, while one that buys pays for
them. The untraded import is therefore charged at the utility price, what the
DSO would have charged for it. Untraded exports (``deferred_supply``) earn
nothing: the surplus is spilled. Buying and selling then only pay off against
these two outside options.

"salazar": the terms of ``src/environment/reward.py`` in the original repository, as
they ran there. It is not scaled by ``reward_scale``, as the original has no such
scale. It needs ``grid_capacity_kwh``.

With ``terminal_value`` (``MarketEnv``) the window's last reward adds the change of
the stored energy at ``stored_kwh_value`` per kWh, whichever the reward.
"""

from __future__ import annotations

import math
from typing import Mapping, Optional

import numpy as np

from core.market import signals
from core.market.lem import LocalEnergyMarket, StepRecord
from core.market.order import Order, Trade


# --------------------------------------------------------------------------------------
# The money
# --------------------------------------------------------------------------------------
def net_bill(record: StepRecord, pid: str) -> float:
    """Agent ``pid``'s net bill for the step, in the scenario's money unit."""
    outcome = record.participants[pid]

    return outcome.profit - record.inputs.utility_price * outcome.deferred_demand_kwh


# --------------------------------------------------------------------------------------
# The original code's reward: every constant and form as it ran there
# --------------------------------------------------------------------------------------
# R_base: the weights of its five parts ([P1] §3.2.4)
W_GRID, W_RESOURCE, W_TRADING, W_STABILITY, W_ECONOMIC = 10.0, 1.5, 5.0, 2.0, 3.0
# f_coop ([P1] eq. 5): the weight of each KPI of ``signals.KPIS``, adding up to 56
COOPERATION_WEIGHTS = {
    "social_welfare": 7.0,
    "liquidity": 1.5,
    "bid_ask_spread": 1.5,
    "price_volatility": 3.0,
    "supply_demand_imbalance": 10.0,
    "grid_congestion": 9.0,
    "coordination_score": 5.0,
    "coordination_convergence": 8.0,
    "der_self_consumption": 5.0,
    "flexibility_utilization": 6.0,
}
LOWER_IS_BETTER = (
    "supply_demand_imbalance",
    "grid_congestion",
    "price_volatility",
    "bid_ask_spread",
)
# Penalties
P_DSO, P_NO_TRADES = 15.0, 5.0
P_IMBALANCE, P_PRICE_DEVIATION, P_UNUTILISED, P_VOLATILITY = 10.0, 2.0, 1.5, 2.0
# E-17: the original's local weight 0.7 was overwritten, so the trading part ran as
# 0.3 / 0.3, as [P1] prints it.
W_LOCAL, W_DSO = 0.3, 0.3
W_PRICE_EFFICIENCY, W_DSO_PROFIT = 0.4, 0.6
W_VOLATILITY, W_IMPROVEMENT = 0.3, 0.7
# f_contrib ([P1] eq. 6)
W_CONTRIB_GRID, W_CONTRIB_DEVIATION, W_CONTRIB_LOCAL = 0.5, 0.2, 0.3
NEUTRAL = 0.5
LOG_SCALE = 20.0  # [P1] eq. 3
BOOST_SCALE = 5.0
PENALTY_SCALE = 0.3


def log_compress(value: float) -> float:
    """[P1] eq. 3: sign(x) · 20 · ln(1 + |x| / 20)."""
    return float(np.sign(value) * math.log1p(abs(value) / LOG_SCALE) * LOG_SCALE)


def _clip(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _side_kwh(trades: list[Trade], pid: str) -> tuple[float, float]:
    """The energy ``pid`` bought and sold in ``trades``."""
    bought = sum(t.quantity for t in trades if t.buyer_id == pid)
    sold = sum(t.quantity for t in trades if t.seller_id == pid)

    return bought, sold


# --- The five parts of R_base ---------------------------------------------------------
def trading_reward(order: Order, local_kwh: float, dso_kwh: float) -> float:
    """r_trade: the order's fill rates, by peers and by the DSO."""
    if order.quantity <= 0:
        return 0.0

    local = min(local_kwh / order.quantity, 1.0)
    dso = min(dso_kwh / order.quantity, 1.0)

    return W_LOCAL * local + W_DSO * dso


def grid_balance_reward(
    order: Order, balance: float, position: float, capacity: float
) -> float:
    """r_grid: the order's direction against the balance, minus a penalty for the
    balance itself, plus the agent's impact on it."""
    helps = balance > 0 if order.is_buy else balance < 0
    contribution = order.quantity if helps else -order.quantity
    state = _clip(balance / capacity, -1.0, 1.0)
    impact = abs(balance - position) - abs(balance)
    impact = _clip(impact / (0.1 * capacity), -1.0, 1.0)
    base = contribution / capacity - abs(state) * P_IMBALANCE

    return 1.0 - min(abs(balance) / capacity, 1.0) + base + 0.5 * impact


def resource_reward(order: Order, trades: list[Trade]) -> float:
    """r_res: the share of the order executed, minus a penalty for the rest."""
    bought, sold = _side_kwh(trades, order.agent_id)
    executed = (bought if order.is_buy else sold) / order.quantity

    return executed - (1.0 - executed) * P_UNUTILISED


def stability_reward(
    order: Order, trades: list[Trade], clearing_price: float, balance: float
) -> float:
    """r_stab: the spread of the agent's trade prices, and how far its trades closed
    the balance."""
    if not trades:
        return 0.0

    volatility = 1.0

    if clearing_price > 0:
        volatility = float(np.std([t.price for t in trades])) / clearing_price

    stability = 1.0 - volatility * P_VOLATILITY
    improvement = 0.0

    if balance != 0:
        bought, sold = _side_kwh(trades, order.agent_id)
        after = abs(balance + bought - sold)
        improvement = max(0.0, (abs(balance) - after) / abs(balance))

    return W_VOLATILITY * stability + W_IMPROVEMENT * improvement


def economic_reward(
    order: Order,
    trades: list[Trade],
    clearing_price: float,
    feed_in_tariff: float,
    utility_price: float,
    min_price: float,
    max_price: float,
) -> float:
    """r_econ: the agent's mean price against the clearing price, and its gain
    against the DSO's tariffs."""
    if clearing_price == 0 or not trades:
        return 0.0

    kwh = sum(t.quantity for t in trades)
    price = sum(t.price * t.quantity for t in trades) / kwh
    deviation = abs(price - clearing_price) / clearing_price
    efficiency = 1.0 - min(deviation * P_PRICE_DEVIATION, 1.0)

    if order.is_buy:
        gain, most = utility_price - price, utility_price - min_price
    else:
        gain, most = price - feed_in_tariff, max_price - feed_in_tariff

    score = _clip(gain / most, 0.0, 1.0) if most > 0 else 0.0

    return W_PRICE_EFFICIENCY * efficiency + W_DSO_PROFIT * score


# --- f_coop and f_contrib -------------------------------------------------------------
def cooperation_factor(kpis: Mapping[str, float]) -> float:
    """f_coop ([P1] eq. 5): the KPIs' weighted mean, with those where lower is better
    inverted. A NaN KPI counts as 0, as a missing one did in the original."""
    # OPEN E-13, E-20: the KPIs enter raw, as in the original; no source gives the
    # ranges that would keep this in [0, 1].
    total = 0.0

    for name, weight in COOPERATION_WEIGHTS.items():
        value = kpis.get(name, 0.0)
        value = 0.0 if math.isnan(value) else value
        total += weight * (1.0 - value if name in LOWER_IS_BETTER else value)

    return total / sum(COOPERATION_WEIGHTS.values())


def contribution_factor(
    pid: str,
    trades: list[Trade],
    local: list[Trade],
    clearing_price: float,
    balance: float,
) -> float:
    """f_contrib ([P1] eq. 6): the agent's net trade against the balance, its trade
    prices against the clearing price, and its share of trades with peers."""
    if not trades:
        return NEUTRAL

    grid = NEUTRAL

    if balance != 0:
        bought, sold = _side_kwh(trades, pid)
        net = sold - bought
        share = min(1.0, abs(net) / abs(balance))
        helps = (balance > 0 and net < 0) or (balance < 0 and net > 0)
        grid = 0.5 + 0.5 * share if helps else 0.5 - 0.5 * share

    deviation = NEUTRAL

    if clearing_price > 0:
        gaps = [abs(t.price - clearing_price) / clearing_price for t in trades]
        deviation = _clip(1.0 - float(np.mean(gaps)) * 2.0, 0.0, 1.0)

    return (
        W_CONTRIB_GRID * grid
        + W_CONTRIB_DEVIATION * deviation
        + W_CONTRIB_LOCAL * len(local) / len(trades)
    )


# --- Penalties ------------------------------------------------------------------------
def dso_penalty(
    local_kwh: float, dso_kwh: float, balance: float, capacity: float
) -> float:
    """γ_DSO: the agent's DSO share, scaled by the balance against the capacity."""
    total = local_kwh + dso_kwh
    share = dso_kwh / total if total > 0 else 0.0

    return share * P_DSO * abs(balance) / max(capacity, 1.0)


def demand_penalty(required_kwh: float, satisfied_kwh: float) -> float:
    """γ_UD at the terminal step: the squared share of the episode's demand left
    unmet. It uses p_dso, not [P1]'s p_no_trades (E-18)."""
    if required_kwh <= 0:
        return 0.0

    unmet = max(0.0, required_kwh - satisfied_kwh)

    return P_DSO * (unmet / required_kwh) ** 2


# --------------------------------------------------------------------------------------
# The rewards to choose from
# --------------------------------------------------------------------------------------
class Reward:
    """What each agent is paid for a step. A subclass defines ``step``.

    Args:
        market: The market the environment plays.
        reward_scale: The environment's reward scale.
        grid_capacity_kwh: The grid capacity C, for a reward that needs it.
    """

    def __init__(
        self,
        market: LocalEnergyMarket,
        reward_scale: float,
        grid_capacity_kwh: Optional[float] = None,
    ) -> None:
        self.market = market
        self.reward_scale = reward_scale
        self.grid_capacity_kwh = grid_capacity_kwh

    def step(self, record: StepRecord) -> dict[str, float]:
        """Every agent's reward for the step just played, ``record``."""
        raise NotImplementedError

    def stored_energy(self, gain_kwh: float, stored_kwh_value: float) -> float:
        """What the window's last reward adds for ``gain_kwh`` more energy stored."""
        return stored_kwh_value * gain_kwh / self.reward_scale


class NetBillReward(Reward):
    """The net bill, scaled (see the module)."""

    def step(self, record: StepRecord) -> dict[str, float]:
        return {
            pid: net_bill(record, pid) / self.reward_scale
            for pid in record.participants
        }


class SalazarReward(Reward):
    """The original code's reward (see the module). The market day's last step pays
    the unmet-demand penalty, for that day."""

    def __init__(
        self,
        market: LocalEnergyMarket,
        reward_scale: float,
        grid_capacity_kwh: Optional[float] = None,
    ) -> None:
        super().__init__(market, reward_scale, grid_capacity_kwh)

        # OPEN: SimBench has no single capacity C, so a run must state one.
        if not grid_capacity_kwh or grid_capacity_kwh <= 0:
            raise ValueError("the 'salazar' reward needs a grid_capacity_kwh above 0")

    def step(self, record: StepRecord) -> dict[str, float]:
        history = self.market.history
        # OPEN E-10: the KPIs over the day so far, as in the observation; the
        # original took most of them over the step alone.
        kpis = signals.kpis(history)
        previous = history[-2] if len(history) > 1 else None
        out = {}

        for pid in record.participants:
            # The original's agent.balance: 0 on the first step of a day, where it
            # drew a random number.
            position = 0.0

            if previous is not None:
                then = previous.participants[pid]
                position = then.sold_kwh - then.bought_kwh

            required, satisfied = None, 0.0

            if self.market.done:
                required = sum(self.market.participants[pid].demand_kwh)
                satisfied = sum(
                    r.participants[pid].satisfied_demand_kwh for r in history
                )

            out[pid] = self.agent_reward(
                record, pid, kpis, position, required, satisfied
            )

        return out

    def agent_reward(
        self,
        record: StepRecord,
        pid: str,
        kpis: Mapping[str, float],
        position: float,
        required_kwh: Optional[float] = None,
        satisfied_kwh: float = 0.0,
    ) -> float:
        """Agent ``pid``'s reward for the step.

        Args:
            record: The step.
            pid: The agent.
            kpis: The KPIs (``signals.kpis``).
            position: The agent's net traded energy in the previous step, + sold.
            required_kwh: The agent's total demand of the day, given only on its
                last step (``None``: no unmet-demand penalty).
            satisfied_kwh: The demand satisfied that day.
        """
        # OPEN E-16: the original read a balance that is always 0 after clearing;
        # here B_grid before the DSO clears, so its grid terms act for the first time.
        balance = record.grid_balance_kwh
        capacity = self.grid_capacity_kwh
        rules = self.market.scenario.market
        trades = [t for t in record.trades if pid in (t.buyer_id, t.seller_id)]

        if not trades:  # E-19: returned before any other term
            return log_compress(-P_NO_TRADES)

        order = next(o for o in record.orders if o.agent_id == pid)
        local = [t for t in trades if t.stage < 3]
        local_kwh = sum(t.quantity for t in local)
        dso_kwh = sum(t.quantity for t in trades) - local_kwh
        clearing_price, inputs = record.clearing_price, record.inputs
        economic = economic_reward(
            order,
            trades,
            clearing_price,
            inputs.feed_in_tariff,
            inputs.utility_price,
            rules.min_price,
            rules.max_price,
        )
        base = (
            W_GRID * grid_balance_reward(order, balance, position, capacity)
            + W_RESOURCE * resource_reward(order, trades)
            + W_TRADING * trading_reward(order, local_kwh, dso_kwh)
            + W_STABILITY * stability_reward(order, trades, clearing_price, balance)
            + W_ECONOMIC * economic
        )
        cooperation = cooperation_factor(kpis)
        contribution = contribution_factor(pid, trades, local, clearing_price, balance)
        boosted = base * (
            1.0 + math.log1p(max(0.0, cooperation * contribution)) / BOOST_SCALE
        )
        scale = PENALTY_SCALE * max(abs(boosted), 1.0)
        raw = boosted - scale * dso_penalty(local_kwh, dso_kwh, balance, capacity)

        if required_kwh is not None:
            raw -= scale * demand_penalty(required_kwh, satisfied_kwh) / P_DSO

        return log_compress(raw)


REWARDS: dict[str, type[Reward]] = {
    "bill": NetBillReward,
    "salazar": SalazarReward,
}


def build_reward(
    name: str,
    market: LocalEnergyMarket,
    reward_scale: float,
    grid_capacity_kwh: Optional[float] = None,
) -> Reward:
    """The reward called ``name`` (``REWARDS``) for ``market``."""
    if name not in REWARDS:
        raise ValueError(f"unknown reward {name!r}; choose from {sorted(REWARDS)}")

    return REWARDS[name](market, reward_scale, grid_capacity_kwh)
