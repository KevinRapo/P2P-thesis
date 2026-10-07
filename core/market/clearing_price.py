"""Clearing (pricing) mechanisms: the price of a matched buy and sell order.

[P1] §3.3.3. Every mechanism takes the same three arguments, in the same order:
the buy order, the sell order and a reference price (the previous clearing price,
or the midpoint of the DSO's tariffs). The original code let each mechanism name
its own arguments, so the seller mechanism received the buy order and returned the
buyer's price; one fixed signature rules that out.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from core.market.order import Order


# --------------------------------------------------------------------------------------
# The interface
# --------------------------------------------------------------------------------------
class BasePricing(Protocol):
    """What every pricing mechanism provides."""

    def calculate_price(
        self, buy_order: Order, sell_order: Order, reference_price: float
    ) -> float:
        """The trade price of a matched pair.

        Args:
            buy_order: The buyer's order.
            sell_order: The seller's order.
            reference_price: Previous clearing price, or the tariffs' midpoint.
        """
        ...


# --------------------------------------------------------------------------------------
# The mechanisms
# --------------------------------------------------------------------------------------
class AveragePricing:
    """Average of bid and ask, [P1] (9)."""

    def calculate_price(
        self, buy_order: Order, sell_order: Order, reference_price: float
    ) -> float:
        return (buy_order.price + sell_order.price) / 2


class BuyerPricing:
    """The buyer's bid ("pay as offer"); favours the seller."""

    def calculate_price(
        self, buy_order: Order, sell_order: Order, reference_price: float
    ) -> float:
        return buy_order.price


class SellerPricing:
    """The seller's ask ("pay as bid"); favours the buyer."""

    def calculate_price(
        self, buy_order: Order, sell_order: Order, reference_price: float
    ) -> float:
        return sell_order.price


class BidAskSpreadPricing:
    """A point inside the bid-ask spread: ``factor`` 0 is the ask, 1 the bid.

    Used in the [P1] case study, not defined in [P1] §3.3.3.
    """

    def __init__(self, factor: float = 0.5) -> None:
        self.factor = max(0.0, min(factor, 1.0))

    def calculate_price(
        self, buy_order: Order, sell_order: Order, reference_price: float
    ) -> float:
        return sell_order.price + (buy_order.price - sell_order.price) * self.factor


class NashBargainingPricing:
    """Equal split of the surplus, [P1] (10); the average when there is none."""

    def calculate_price(
        self, buy_order: Order, sell_order: Order, reference_price: float
    ) -> float:
        spread = buy_order.price - sell_order.price
        if spread <= 0:
            return (buy_order.price + sell_order.price) / 2
        return sell_order.price + spread / 2


class ProportionalSurplusPricing:
    """Surplus split by each side's distance from the reference price, [P1] (11)
    (reconstructed); the average when the distances say nothing."""

    def calculate_price(
        self, buy_order: Order, sell_order: Order, reference_price: float
    ) -> float:
        buyer = max(0.0, buy_order.price - reference_price)
        seller = max(0.0, reference_price - sell_order.price)
        spread = buy_order.price - sell_order.price
        if buyer + seller == 0 or spread <= 0:
            return (buy_order.price + sell_order.price) / 2
        return sell_order.price + buyer / (buyer + seller) * spread


# --------------------------------------------------------------------------------------
# Choosing a mechanism by name
# --------------------------------------------------------------------------------------
class ClearingMechanism(Enum):
    """The mechanisms by the name the scenario uses."""

    AVERAGE = "average"
    BUYER = "buyer"
    SELLER = "seller"
    BID_ASK_SPREAD = "bid_ask_spread"
    NASH_BARGAINING = "nash_bargaining"
    PROPORTIONAL_SURPLUS = "proportional_surplus"

    def get_instance(self) -> BasePricing:
        """The pricing object of this mechanism."""
        return {
            "average": AveragePricing,
            "buyer": BuyerPricing,
            "seller": SellerPricing,
            "bid_ask_spread": BidAskSpreadPricing,
            "nash_bargaining": NashBargainingPricing,
            "proportional_surplus": ProportionalSurplusPricing,
        }[self.value]()


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
