"""The three clearing stages of one market step ([P1] §3.3.2, Algorithm 1).

Each stage takes the orders still open and returns its trades and the orders left
over, so the Studio can show the market after every stage:

    1  preferences    mutually preferred partners trade first
    2  double auction bids from the highest price down, asks from the lowest up;
                      every pair with bid >= ask trades
    3  DSO            the DSO clears the rest (``Dso.clear``,
                      ``core/market/dso/dso.py``)

The stages work on copies: the orders as submitted are never changed. The market
is lossless (losses come from the power flow) and charges no grid fees yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

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
        mechanism: Pricing mechanism name (``ClearingMechanism``).
        dso: The DSO, which clears stage 3.
        reference_price: Reference for the proportional mechanism.
        reputation: Each participant's reputation, the double auction's tie-break.
        threshold_kwh: Quantities below this count as nothing.
    """

    mechanism: str
    dso: Dso
    reference_price: float
    reputation: Mapping[str, float] = field(default_factory=dict)
    threshold_kwh: float = 1e-6


def _trade(buy: Order, sell: Order, quantity: float, price: float, stage: int) -> Trade:
    return Trade(
        buyer_id=buy.agent_id,
        seller_id=sell.agent_id,
        price=price,
        quantity=quantity,
        timestamp=max(buy.timestamp, sell.timestamp),
        stage=stage,
    )


def _open(orders: Sequence[Order], rules: ClearingRules) -> tuple[Order, ...]:
    return tuple(o for o in orders if o.quantity > rules.threshold_kwh)


# --------------------------------------------------------------------------------------
# Stage 1: mutual preferences
# --------------------------------------------------------------------------------------
def preferences(orders: Sequence[Order], rules: ClearingRules) -> StageResult:
    """Pairs that named each other as preferred partner trade first, at the
    mechanism's price, whatever their prices. Orders that prefer the DSO wait for
    stage 3."""
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
        quantity = min(buy.quantity, sell.quantity)
        if quantity <= rules.threshold_kwh:
            continue
        price = pricing.calculate_price(buy, sell, rules.reference_price)
        trades.append(_trade(buy, sell, quantity, price, 1))
        buy.quantity -= quantity
        sell.quantity -= quantity
    return StageResult(1, STAGE_NAMES[1], tuple(trades), _open(work, rules))


# --------------------------------------------------------------------------------------
# Stage 2: double auction
# --------------------------------------------------------------------------------------
def double_auction(orders: Sequence[Order], rules: ClearingRules) -> StageResult:
    """Bids sorted by price (high first), asks by price (low first); reputation and
    arrival break ties. Pairs trade while the bid is at least the ask. Orders that
    prefer the DSO stay out."""
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
        trades.append(_trade(buy, sell, quantity, price, 2))
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
    """The DSO clears every order still open ([P1] §3.3.2, ``Dso.clear``)."""
    return StageResult(3, STAGE_NAMES[3], rules.dso.clear(_open(orders, rules)), ())


STAGES = (preferences, double_auction, dso)
