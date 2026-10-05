"""Results of order matching: one record per step and their history.

No ``from __future__ import annotations``: ``MatchingResult.__post_init__``
reads its annotations at run time.
"""

from dataclasses import dataclass
from typing import List

from src_thesis.core.orders import Order, Trade


@dataclass
class MatchingResult:
    """Result of order matching process."""

    trades: List[Trade]
    unmatched_orders: List[Order]
    clearing_price: float
    clearing_volume: float
    dso_buy_volume: float
    dso_sell_volume: float
    dso_total_volume: float
    p2p_volume: float
    dso_trade_ratio: float
    dso_grid_import: float
    dso_buy_price: float
    dso_sell_price: float
    price_spread: float
    local_price_avg: float
    local_price_advantage: float
    grid_balance: float
    grid_congestion: float

    def __post_init__(self) -> None:
        """Convert all numpy numeric types to standard float."""
        for k, v in self.__annotations__.items():
            if v is float:
                setattr(self, k, float(getattr(self, k)))


class MatchingHistory:
    """History of order matching process."""

    def __init__(self):
        """Initialize the matching history."""
        self.history: List[MatchingResult] = []

    def reset(self):
        """Reset the matching history."""
        self.history = []

    def update(self, matching_result: MatchingResult):
        """Update the matching history.

        Args:
            matching_result: Matching result to add to the history
        """
        self.history.append(matching_result)

    def get_matching_result(self, step: int) -> MatchingResult:
        """Get the matching result at a specific step.

        Args:
            step: Step to get the matching result for

        Returns:
            Matching result at the specified step
        """
        return self.history[step]
