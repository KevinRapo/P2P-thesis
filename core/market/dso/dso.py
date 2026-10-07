"""The DSO: the market maker of last resort ([P1] §3.3.1).

What belongs to the DSO and nobody else:

    tariffs          p_FiT, what it pays for energy it buys, and p_utility, what it
                     charges for energy it sells; p_FiT < p_P2P < p_utility
    market price     the midpoint of the two, the reference before any trade
    stage 3          it buys every remaining sell at p_FiT and sells every
                     remaining buy at p_utility, so every order clears (§3.3.2)

Grid fees (eq. 8) and the DSO balance (eq. 7) are not built yet.
"""

from __future__ import annotations

from typing import Sequence

from core.market.order import Order, Trade

DSO_ID = "DSO"


class Dso:
    """The DSO of one market day.

    Args:
        feed_in_tariff: p_FiT, what the DSO pays per kWh it buys.
        utility_price: p_utility, what the DSO charges per kWh it sells.
        id: The DSO's ID in trades and partner preferences.
    """

    def __init__(
        self, feed_in_tariff: float, utility_price: float, id: str = DSO_ID
    ) -> None:
        self.feed_in_tariff = feed_in_tariff
        self.utility_price = utility_price
        self.id = id

    def market_price(self) -> float:
        """The midpoint of p_FiT and p_utility: the reference price before any
        peer-to-peer trade (the original's ``get_market_price``)."""
        return (self.feed_in_tariff + self.utility_price) / 2

    def clear(self, orders: Sequence[Order]) -> tuple[Trade, ...]:
        """Stage 3 ([P1] §3.3.2): buy every remaining sell at p_FiT and sell every
        remaining buy at p_utility."""
        trades = []
        for o in orders:
            if o.is_buy:
                buyer, seller, price = o.agent_id, self.id, self.utility_price
            else:
                buyer, seller, price = self.id, o.agent_id, self.feed_in_tariff
            trades.append(Trade(buyer, seller, price, o.quantity, o.timestamp, stage=3))
        return tuple(trades)
