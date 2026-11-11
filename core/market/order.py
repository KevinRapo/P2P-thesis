"""
Order and trade data classes for the Local Energy Market.
"""

from dataclasses import dataclass
from typing import Optional

# The ``stage`` of a trade that is no clearing stage: the energy no trade covered,
# settled with the DSO at the tariffs and charged the fees of a DSO trade (MP-1f).
UNTRADED = 4


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


@dataclass(frozen=True)
class GridFees:
    """The parts of one trade's grid fee, F_total ([P1] eq. 8); a negative part is
    a bonus. Calculated by the DSO (``Dso.assess``, ``Dso.clear``)."""

    congestion: float = 0.0  # F_cong (8a)
    transmission: float = 0.0  # F_trans: the lost energy l_ij at the trade price
    imbalance: float = 0.0  # F_imb (8b, 8h): DSO trades that worsen B_grid
    voltage: float = 0.0  # F_volt (8c, 8f)
    thermal: float = 0.0  # F_thermal (8d, 8g)
    zone: float = 0.0  # F_zone (8e): same-zone bonus, negative
    peer_charge: float = 0.0  # Not in [P1]: DsoSetup.peer_charge_kwh, the buyer's

    @property
    def total(self) -> float:
        """F_total ([P1] eq. 8)."""
        return (
            self.congestion
            + self.transmission
            + self.imbalance
            + self.voltage
            + self.thermal
            + self.zone
            + self.peer_charge
        )


@dataclass
class Trade:
    """Represents a completed trade between two agents."""

    buyer_id: str
    seller_id: str
    price: float  # p_ij ([P1] §3.3.3)
    quantity: float  # q_ij
    timestamp: float
    # d_ij ([P1] §3.5.1), km along the lines; with the DSO, to the transformer
    distance: float = 0.0
    # l_ij ([P1] eq. 18), recorded only: the market stays lossless, the power flow
    # has the physical losses
    transmission_loss: float = 0.0
    fees: float = 0.0  # F_total ([P1] eq. 8), calculated whether charged or not
    fee_parts: GridFees = GridFees()
    buyer_fee: float = 0.0  # What the buyer pays of the fee (0 when not charged)
    seller_fee: float = 0.0  # What the seller pays of the fee (0 when not charged)
    # Clearing stage: 1, 2 or 3 (DSO) ([P1] §3.3.2); ``UNTRADED`` for the energy no
    # trade covered, settled with the DSO after the clearing
    stage: int = 0
