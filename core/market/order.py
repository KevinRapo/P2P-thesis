"""
Order and trade data classes for the Local Energy Market.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    """Represents a market order: the paper's action a_i = <p_bid, q_bid, α, β>
    ([P1] eq. 2, §3.2.3)."""

    id: str  # Unique identifier for the order
    agent_id: str
    price: float  # p_bid
    quantity: float  # q_bid
    is_buy: bool  # α: True = buy, False = sell
    timestamp: float
    location: Optional[str] = None  # Agent's bus in the network
    # β ([P1] eq. 2): ID of the preferred trading partner. If specified, the agent
    # prefers to trade with this partner when possible.
    partner_id: Optional[str] = None


@dataclass
class Trade:
    """Represents a completed trade between two agents."""

    buyer_id: str
    seller_id: str
    price: float  # p_ij ([P1] §3.3.3)
    quantity: float  # q_ij
    timestamp: float
    distance: float = 0.0  # d_ij ([P1] §3.5.1); not filled in yet
    transmission_loss: float = 0.0  # l_ij ([P1] eq. 18); unused, see power flow
    fees: float = 0.0  # F_total ([P1] eq. 8); not charged yet
    stage: int = 0  # Clearing stage: 1, 2 or 3 (DSO) ([P1] §3.3.2)
