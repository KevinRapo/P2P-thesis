"""Clearing (pricing) mechanisms: the price of a matched buy and sell order.

[P1] §3.3.3. Every mechanism takes the same three arguments, in the same order:
the buy order, the sell order and a reference price (the previous clearing price,
or the midpoint of the DSO's tariffs). The original code let each mechanism name
its own arguments, so the seller mechanism received the buy order and returned the
buyer's price; one fixed signature rules that out.
"""

from __future__ import annotations

from enum import Enum

from core.market.order import Order


class ClearingMechanism(Enum):
    """The mechanism selected by a scenario, and its trade-price calculation."""

    AVERAGE = "average"  # [P1] eq. 9
    BUYER = "buyer"
    SELLER = "seller"
    BID_ASK_SPREAD = "bid_ask_spread"  # [P1] case study; not defined in §3.3.3
    NASH_BARGAINING = "nash_bargaining"  # [P1] eq. 10
    PROPORTIONAL_SURPLUS = "proportional_surplus"  # [P1] eq. 11, reconstructed

    def calculate_price(
        self,
        buy: Order,
        sell: Order,
        reference_price: float,
        *,
        factor: float = 0.5,
    ) -> float:
        """Return the trade price for a matched pair of orders.

        Args:
            buy: The buyer's order.
            sell: The seller's order.
            reference_price: Previous clearing price, or the tariffs' midpoint.
            factor: For ``BID_ASK_SPREAD`` only, position in the spread,
                clamped to [0, 1].
        """
        match self:
            case ClearingMechanism.AVERAGE:
                return (buy.price + sell.price) / 2
            
            case ClearingMechanism.BUYER:
                return buy.price
            
            case ClearingMechanism.SELLER:
                return sell.price
            
            case ClearingMechanism.BID_ASK_SPREAD:
                factor = max(0.0, min(factor, 1.0))
                return sell.price + (buy.price - sell.price) * factor
            
            case ClearingMechanism.NASH_BARGAINING:
                spread = buy.price - sell.price
                if spread <= 0:
                    return (buy.price + sell.price) / 2
                return sell.price + spread / 2
            
            case ClearingMechanism.PROPORTIONAL_SURPLUS:
                buyer = max(0.0, buy.price - reference_price)
                seller = max(0.0, reference_price - sell.price)
                spread = buy.price - sell.price

                if buyer + seller == 0 or spread <= 0:
                    return (buy.price + sell.price) / 2

                return sell.price + buyer / (buyer + seller) * spread


# What each mechanism means, for the Studio's captions.
DESCRIPTIONS = {
    "average": "Midpoint of bid and ask: both sides share the surplus equally.",
    "buyer": "The buyer's bid: the seller gets the whole surplus.",
    "seller": "The seller's ask: the buyer gets the whole surplus.",
    "bid_ask_spread": "Halfway inside the bid-ask spread (as the paper's case study).",
    "nash_bargaining": "Equal split of the surplus (the same as the average when "
    "bid ≥ ask).",
    "proportional_surplus": "Surplus split by how far each side bid from the "
    "previous clearing price.",
}
