"""Recorded, explicitly named market and physical summary metrics."""

from typing import Dict, List

import numpy as np

from ..agent.der import DERAgent
from ..market.matching import MatchingHistory
from ..market.order import Order, Trade


class ImplicitCooperation:
    """Provide only metrics whose inputs are present in the simulation record."""

    def __init__(self, grid_capacity: float) -> None:
        if grid_capacity <= 0:
            raise ValueError("Grid capacity must be greater than 0.")
        self.grid_capacity = grid_capacity

    def get_kpis(self,
                 current_step: int,
                 dso_id: str,
                 agents: List[DERAgent],
                 orders: List[Order],
                 trades: List[Trade],
                 grid_congestion: float,
                 matching_history: MatchingHistory) -> Dict[str, float]:
        """Return descriptive metrics; none are used as a training reward."""
        del matching_history
        bids = [order.price for order in orders if order.is_buy]
        asks = [order.price for order in orders if not order.is_buy]
        trade_energy = sum(trade.quantity for trade in trades)
        local_energy = sum(trade.quantity for trade in trades
                           if trade.buyer_id != dso_id and trade.seller_id != dso_id)
        total_generation = sum(agent.get_generation(current_step) for agent in agents)
        total_demand = sum(agent.get_demand(current_step) for agent in agents)
        physical_imbalance = min(1.0, abs(total_generation - total_demand) / self.grid_capacity)

        return {
            "settlement_turnover": sum(trade.price * trade.quantity for trade in trades),
            "traded_energy": trade_energy,
            "bid_ask_spread": float(np.mean(bids) - np.mean(asks)) if bids and asks else 0.0,
            "settlement_price_volatility": float(np.std([trade.price for trade in trades])) if len(trades) > 1 else 0.0,
            "physical_supply_demand_imbalance": physical_imbalance,
            "grid_congestion": min(1.0, max(0.0, grid_congestion)),
            "physical_balance_score": 1.0 - physical_imbalance,
            "local_trade_share": local_energy / trade_energy if trade_energy else 0.0,
        }
