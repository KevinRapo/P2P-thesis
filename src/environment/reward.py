"""Auditable reward calculation for the local-energy-market environment."""

from typing import Dict

from ..agent.der import DERAgent
from ..grid.network import GridNetwork
from ..market.dso import DSOAgent
from ..market.matching import MatchingResult
from ..market.order import Order


class RewardHandler:
    """Calculate a bounded reward from settlement records.

    The initial learning objective deliberately contains no cooperation or
    analytics KPI.  Those values remain reported metrics until they have
    independently defined raw inputs and units.
    """

    def __init__(self, dso: DSOAgent, grid_network: GridNetwork) -> None:
        if dso is None:
            raise ValueError("DSO agent must be provided in the config.")
        if grid_network is None:
            raise ValueError("Grid network must be provided in the config.")
        self.dso = dso
        self.grid_network = grid_network
        self.unserved_energy_penalty = 1.0
        self.transmission_loss_penalty = 1.0
        self.constraint_penalty = 0.1
        self.terminal_unserved_penalty = 1.0

    def calculate_reward(self,
                         agent: DERAgent,
                         order: Order,
                         matching: MatchingResult,
                         kpis: Dict[str, float],
                         min_price: float,
                         max_price: float,
                         is_terminal: bool = False) -> float:
        """Return normalized settlement profit minus physical penalties.

        ``kpis`` is retained only for the environment API while KPI definitions
        are repaired; no displayed metric changes the learning objective.
        """
        del kpis
        agent_trades = [trade for trade in matching.trades
                        if trade.buyer_id == agent.id or trade.seller_id == agent.id]
        bought = sum(trade.delivered_quantity for trade in agent_trades
                     if trade.buyer_id == agent.id)
        sold = sum(trade.quantity for trade in agent_trades
                   if trade.seller_id == agent.id)
        losses = sum(trade.transmission_loss for trade in agent_trades
                     if trade.buyer_id == agent.id)

        cash_change = sum(
            (trade.price * trade.quantity if trade.seller_id == agent.id else 0.0)
            - (trade.price * trade.quantity + trade.fees if trade.buyer_id == agent.id else 0.0)
            for trade in agent_trades
        )
        # Price span and order energy convert together if display units change.
        settlement_scale = (max_price - min_price) * order.quantity
        economic_reward = cash_change / settlement_scale if settlement_scale > 0 else 0.0

        requested_delivery = order.quantity if order.is_buy else 0.0
        unserved = max(0.0, requested_delivery - bought)
        unserved_ratio = unserved / requested_delivery if requested_delivery else 0.0
        loss_ratio = losses / requested_delivery if requested_delivery else 0.0
        constraint_ratio = min(1.0, max(0.0, matching.grid_congestion))

        reward = (economic_reward
                  - self.unserved_energy_penalty * unserved_ratio
                  - self.transmission_loss_penalty * loss_ratio
                  - self.constraint_penalty * constraint_ratio)

        if is_terminal and agent.total_demand_required > 0:
            terminal_unserved = max(0.0, agent.total_demand_required - agent.cumulative_demand_satisfied)
            reward -= self.terminal_unserved_penalty * (terminal_unserved / agent.total_demand_required)
        return float(reward)
