"""How participants bid when nobody bids for them: a simple, fixed rule.

Without learning, someone has to decide each participant's order. This rule does
what a sensible prosumer would: use its own battery first, then offer what is left
over or ask for what is missing, at a price between the DSO's two tariffs.

    surplus  G − D > 0   charge the battery, sell the rest
    deficit  G − D < 0   discharge the battery, buy the rest

    ask = FiT + margin · (utility − FiT)      (± jitter)
    bid = utility − margin · (utility − FiT)  (± jitter)

With ``margin`` below 0.5 bids lie above asks and peers trade with each other;
above 0.5 nobody does and everything goes to the DSO.
"""

from __future__ import annotations

import random
from typing import Mapping, Optional

from config.scenario import MarketSetup


# --------------------------------------------------------------------------------------
# What a participant knows when it bids
# --------------------------------------------------------------------------------------
class BidView:
    """One participant at the start of a step.

    Args:
        participant_id: The participant.
        generation_kwh: Its generation this step.
        demand_kwh: Its demand this step.
        chargeable_kwh: What its battery can still take from the bus.
        dischargeable_kwh: What its battery can still deliver to the bus.
    """

    def __init__(
        self,
        participant_id: str,
        generation_kwh: float,
        demand_kwh: float,
        chargeable_kwh: float = 0.0,
        dischargeable_kwh: float = 0.0,
    ) -> None:
        self.participant_id = participant_id
        self.generation_kwh = generation_kwh
        self.demand_kwh = demand_kwh
        self.chargeable_kwh = chargeable_kwh
        self.dischargeable_kwh = dischargeable_kwh


# --------------------------------------------------------------------------------------
# The rule
# --------------------------------------------------------------------------------------
def net_position(
    views: Mapping[str, BidView],
    market: MarketSetup,
    feed_in_tariff: float,
    utility_price: float,
    step: int,
    partners: Optional[Mapping[str, str]] = None,
) -> dict[str, tuple[bool, float, float, Optional[str]]]:
    """Each participant's order as ``(is_buy, price, quantity_kwh, partner)``;
    participants with nothing to trade are left out.

    Args:
        views: What each participant knows.
        market: The margin, jitter and seed.
        feed_in_tariff: The DSO's feed-in tariff this step.
        utility_price: The DSO's utility price this step.
        step: The step, so each step draws its own jitter.
        partners: Preferred partner per participant, if any.
    """
    rng = random.Random(market.seed * 100_003 + step)
    spread = utility_price - feed_in_tariff
    out = {}
    for pid, v in views.items():
        net = v.generation_kwh - v.demand_kwh
        if net > 0:
            quantity = net - min(net, v.chargeable_kwh)
            is_buy = False
            price = feed_in_tariff + market.bid_margin * spread
        else:
            quantity = -net - min(-net, v.dischargeable_kwh)
            is_buy = True
            price = utility_price - market.bid_margin * spread
        if quantity <= 1e-9:
            continue
        price += rng.uniform(-1, 1) * market.bid_jitter * spread
        price = min(market.max_price, max(market.min_price, price))
        out[pid] = (is_buy, price, quantity, (partners or {}).get(pid))
    return out
