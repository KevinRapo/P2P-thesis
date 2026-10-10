"""The three clearing stages of one market step ([P1] §3.3.2, Algorithm 1).

Each stage takes the orders still open and returns its trades and the orders left
over, so the Studio can show the market after every stage:

    1  preferences    mutually preferred partners trade first, if bid >= ask
    2  double auction bids from the highest price down, asks from the lowest up;
                      every pair with bid >= ask trades
    3  DSO            the DSO clears the rest (``Dso.clear``,
                      ``core/market/dso/dso.py``)

The stages work on copies: the orders as submitted are never changed. Every trade
leaves its stage assessed by the DSO: distance d_ij, transmission loss l_ij ([P1]
eq. 18, recorded: the market stays lossless, the power flow has the physical
losses) and grid fee ([P1] eq. 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Mapping, Sequence

from core.grid.contract import GridPath
from core.market.clearing_price import ClearingMechanism
from core.market.dso.dso import DSO_ID, Dso
from core.market.order import Order, Trade

STAGE_NAMES = {1: "Preferences", 2: "Double auction", 3: "DSO"}


# --------------------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class StageResult:
    """One clearing stage.

    Attributes:
        stage: 1, 2 or 3.
        name: The stage's name.
        trades: Trades made in this stage.
        remaining: Orders still open after it, with their remaining quantity.
    """

    stage: int
    name: str
    trades: tuple[Trade, ...]
    remaining: tuple[Order, ...]

    @property
    def volume_kwh(self) -> float:
        """Energy traded in this stage."""
        return sum(t.quantity for t in self.trades)


@dataclass
class ClearingRules:
    """What the stages need besides the orders.

    Attributes:
        mechanism: Pricing mechanism name (``ClearingMechanism``, [P1] §3.3.3).
        dso: The DSO, which clears stage 3.
        reference_price: p_ref of the proportional mechanism ([P1] eq. 11).
        reputation: Each participant's reputation r_i ([P1] eq. 12), the double
            auction's tie-break.
        path: The grid path between two participants (distance, lines, zones),
            for the DSO's losses and fees.
        grid_balance_kwh: The market's balance B_grid before stage 3 ([P1] eq.
            20; + excess supply), for the imbalance fee of stage 3 (eq. 8b).
        threshold_kwh: Quantities below this count as nothing.
    """

    mechanism: str
    dso: Dso
    reference_price: float
    reputation: Mapping[str, float] = field(default_factory=dict)
    path: Callable[[str, str], GridPath] = lambda a, b: GridPath()
    grid_balance_kwh: float = 0.0
    threshold_kwh: float = 1e-6


def _trade(
    buy: Order,
    sell: Order,
    quantity: float,
    price: float,
    stage: int,
    rules: ClearingRules,
) -> Trade:
    """A peer-to-peer trade, assessed by the DSO (distance, loss, fee)."""
    trade = Trade(
        buyer_id=buy.agent_id,
        seller_id=sell.agent_id,
        price=price,
        quantity=quantity,
        timestamp=max(buy.timestamp, sell.timestamp),
        stage=stage,
    )
    return rules.dso.assess(trade, rules.path(buy.agent_id, sell.agent_id))


def _open(orders: Sequence[Order], rules: ClearingRules) -> tuple[Order, ...]:
    return tuple(o for o in orders if o.quantity > rules.threshold_kwh)


# --------------------------------------------------------------------------------------
# Stage 1: mutual preferences
# --------------------------------------------------------------------------------------
def preferences(orders: Sequence[Order], rules: ClearingRules) -> StageResult:
    """Stage 1 ([P1] §3.3.2; PreferenceMatch in Algorithm 1): pairs that named each
    other as preferred partner (β, [P1] eq. 2) trade first, at the mechanism's
    price, when the bid reaches the ask (as the original's
    ``validate_grid_constraints``). Orders that prefer the DSO wait for stage 3."""
    work = [replace(o) for o in orders]
    pricing = ClearingMechanism(rules.mechanism).get_instance()
    trades = []
    by_agent = {o.agent_id: o for o in work}
    for buy in work:
        if not buy.is_buy or buy.partner_id in (None, DSO_ID):
            continue
        sell = by_agent.get(buy.partner_id)
        if sell is None or sell.is_buy or sell.partner_id != buy.agent_id:
            continue
        if buy.price < sell.price:
            continue
        quantity = min(buy.quantity, sell.quantity)
        if quantity <= rules.threshold_kwh:
            continue
        price = pricing.calculate_price(buy, sell, rules.reference_price)
        trades.append(_trade(buy, sell, quantity, price, 1, rules))
        buy.quantity -= quantity
        sell.quantity -= quantity
    return StageResult(1, STAGE_NAMES[1], tuple(trades), _open(work, rules))


# --------------------------------------------------------------------------------------
# Stage 2: double auction
# --------------------------------------------------------------------------------------
def double_auction(orders: Sequence[Order], rules: ClearingRules) -> StageResult:
    """Stage 2 ([P1] §3.3.2; PriceMatch in Algorithm 1): bids sorted by price (high
    first), asks by price (low first); reputation ([P1] eq. 12) and arrival break
    ties. Pairs trade while the bid is at least the ask. Orders that prefer the DSO
    stay out."""
    work = [replace(o) for o in orders]
    pricing = ClearingMechanism(rules.mechanism).get_instance()
    rep = rules.reputation
    auction = [o for o in work if o.partner_id != DSO_ID]
    buys = sorted(
        (o for o in auction if o.is_buy),
        key=lambda o: (-o.price, -rep.get(o.agent_id, 0.5), o.timestamp),
    )
    sells = sorted(
        (o for o in auction if not o.is_buy),
        key=lambda o: (o.price, -rep.get(o.agent_id, 0.5), o.timestamp),
    )
    trades = []
    b = s = 0
    while b < len(buys) and s < len(sells) and buys[b].price >= sells[s].price:
        buy, sell = buys[b], sells[s]
        quantity = min(buy.quantity, sell.quantity)
        price = pricing.calculate_price(buy, sell, rules.reference_price)
        trades.append(_trade(buy, sell, quantity, price, 2, rules))
        buy.quantity -= quantity
        sell.quantity -= quantity
        if buy.quantity <= rules.threshold_kwh:
            b += 1
        if sell.quantity <= rules.threshold_kwh:
            s += 1
    return StageResult(2, STAGE_NAMES[2], tuple(trades), _open(work, rules))


# --------------------------------------------------------------------------------------
# Stage 3: the DSO clears the rest
# --------------------------------------------------------------------------------------
def dso(orders: Sequence[Order], rules: ClearingRules) -> StageResult:
    """Stage 3: the DSO clears every order still open ([P1] §3.3.2; DSOClear in
    Algorithm 1; ``Dso.clear``)."""
    trades = rules.dso.clear(_open(orders, rules), rules.grid_balance_kwh)
    return StageResult(3, STAGE_NAMES[3], trades, ())


STAGES = (preferences, double_auction, dso)
