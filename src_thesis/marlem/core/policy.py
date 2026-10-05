"""What a controller sees and says: the seam where policies plug in.

A ``Policy`` is anything that turns what each agent can see (``AgentView``) into
what each agent wants to do (``Intent``): a scripted rule, a tiny optimizer, later
a trained RL policy. It never touches the market engine: the engine adapter
translates intents into the engine's own action format, so the same policy runs
on the original ``LocalEnergyMarket`` and on a future clean engine.

Quantities are energy per step (kWh), prices per kWh, as in the market.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Protocol


@dataclass(frozen=True)
class AgentView:
    """What one agent knows at the start of a step (privileged, plain data).

    Attributes:
        agent_id: The agent.
        step: Step of the episode (0-based).
        generation_kwh: Own generation this step.
        demand_kwh: Own demand this step.
        fit: DSO feed-in tariff this step (what the DSO pays for energy).
        utility_price: DSO utility price this step (what the DSO charges).
        min_price: Lowest order price the market accepts.
        max_price: Highest order price the market accepts.
        min_quantity: Smallest order quantity (kWh).
        max_quantity: Largest order quantity (kWh), already limited by capacity.
        soc_kwh: Battery energy level, ``None`` without a battery.
        battery_available_charge: Energy the battery can still take (kWh).
        battery_available_discharge: Energy the battery can still give (kWh).
    """

    agent_id: str
    step: int
    generation_kwh: float
    demand_kwh: float
    fit: float
    utility_price: float
    min_price: float
    max_price: float
    min_quantity: float
    max_quantity: float
    soc_kwh: Optional[float] = None
    battery_available_charge: float = 0.0
    battery_available_discharge: float = 0.0

    @property
    def surplus_kwh(self) -> float:
        """Generation minus demand (negative: a deficit)."""
        return self.generation_kwh - self.demand_kwh

    @property
    def midpoint(self) -> float:
        """Midpoint of the DSO's two prices."""
        return (self.fit + self.utility_price) / 2.0


@dataclass(frozen=True)
class Intent:
    """What an agent wants to do this step: one order, or nothing.

    Attributes:
        price: Order price per kWh.
        quantity_kwh: Energy to trade; 0 means no order.
        is_buy: Buy (True) or sell (False).
        partner: Preferred trading partner, ``None`` for none.
    """

    price: float
    quantity_kwh: float
    is_buy: bool
    partner: Optional[str] = None

    @classmethod
    def nothing(cls, price: float = 0.0) -> "Intent":
        """No order."""
        return cls(price=price, quantity_kwh=0.0, is_buy=False)


class Policy(Protocol):
    """A controller for all agents of one run.

    Attributes:
        name: Registry name, e.g. ``"net_position"``.
    """

    name: str

    def reset(self, seed: Optional[int]) -> None:
        """Start an episode; seed any randomness."""

    def act(self, views: Mapping[str, AgentView]) -> dict[str, Intent]:
        """One intent per agent for the current step."""
