"""What components see of each other: narrow, read-mostly protocols.

The market, the DSO, reputation, implicit cooperation, the grid and the
environment's handlers never import a concrete agent or grid class; they accept
anything that has the attributes below. A test can hand them a small stand-in
(``SimpleNamespace`` or a five-line class) instead of building agents, a NetworkX
grid and profile handlers.

The members are exactly the ones the original code reads; nothing is added or
renamed. The concrete classes (``agents.der.DERAgent``,
``adapters.grid.network.GridNetwork``) satisfy them unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple

from src_thesis.marlem.core.location import Location


class BatteryView(Protocol):
    """An agent's battery, as far as the environment reads it."""

    nominal_capacity: float
    min_soc: float
    max_soc: float
    energy_level: float


class Participant(Protocol):
    """A market participant (a DER agent): identity, profiles, running totals."""

    id: str
    capacity: float
    battery: Optional[BatteryView]
    node_id: Optional[str]
    location: Optional[Location]
    generation_profile: List[float]
    demand_profile: List[float]
    reputation: float
    balance: float
    profit: float
    total_demand_required: float
    cumulative_demand_satisfied: float
    cumulative_demand_deferred: float
    cumulative_supply_satisfied: float
    cumulative_supply_deferred: float

    def get_demand(self, step: int) -> float:
        """Demand at a step."""

    def get_generation(self, step: int) -> float:
        """Generation at a step."""

    def get_remaining_demand(self, step: int) -> float:
        """Demand not yet covered at a step."""

    def get_remaining_supply(self, step: int) -> float:
        """Supply not yet sold at a step."""

    def update_location(self, location: Location) -> None:
        """Place the participant in the grid."""


class MarketBounds(Protocol):
    """The price and quantity bounds of the market (``MarketConfig`` has them)."""

    min_price: float
    max_price: float
    min_quantity: float
    max_quantity: float


class GridView(Protocol):
    """The grid as the market, the DSO and the metrics see it."""

    capacity: float
    graph: Any  # networkx.Graph: nodes, edges, shortest paths
    edge_flows: Dict[Tuple[str, str], float]
    edge_capacities: Dict[Tuple[str, str], float]

    def transmission_loss(
        self, distance: float, quantity: float, loss_factor: float = 0.03
    ) -> float:
        """Energy lost transporting ``quantity`` over ``distance``."""

    def get_path_congestion(self, buyer_node: str, seller_node: str) -> float:
        """Highest congestion on the path between two nodes."""

    def calculate_congestion_level(self) -> float:
        """Congestion of the whole grid."""
