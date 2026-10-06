"""The market step without RL ([P1] Algorithm 1).

Orders in, trades and each participant's physical outcome out. Built from the
original MARLEM pieces in this package (``matching``, ``mechanism``, ``dso``,
``agent``, ``reputation``, ``validation``); rewards and observations are not part
of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from config.scenario import Scenario


# --------------------------------------------------------------------------------------
# What goes in and comes out of one step
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class OrderIntent:
    """What one participant wants to trade this step."""

    participant_id: str
    is_buy: bool
    price: float
    quantity_kwh: float
    partner_id: Optional[str] = None


@dataclass(frozen=True)
class StepInputs:
    """What the world gives the market at step ``t``.

    Attributes:
        step: The step (0-based).
        generation_kwh: Each participant's generation.
        demand_kwh: Each participant's demand.
        feed_in_tariff: What the DSO pays per kWh.
        utility_price: What the DSO charges per kWh.
    """

    step: int
    generation_kwh: Mapping[str, float]
    demand_kwh: Mapping[str, float]
    feed_in_tariff: float
    utility_price: float


@dataclass(frozen=True)
class ParticipantOutcome:
    """What one participant did in one step ([P1] eq. 13, 14, 16)."""

    participant_id: str
    bought_kwh: float
    sold_kwh: float
    charge_kwh: float
    discharge_kwh: float
    external_kwh: float
    soc_kwh: Optional[float]
    profit: float


@dataclass(frozen=True)
class StepOutcome:
    """Everything one market step produced."""

    step: int
    orders: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    participants: dict[str, ParticipantOutcome] = field(default_factory=dict)
    clearing_price: float = 0.0


# --------------------------------------------------------------------------------------
# The market step
# --------------------------------------------------------------------------------------
class MarketStep:
    """The configured market, stepped one period at a time.

    Phases per step: feasibility (eq. 15) -> orders -> three-stage clearing ->
    settlement and batteries -> reputation and ledger.

    Args:
        scenario: The participants, market rules and DSO.
    """

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    def reset(self) -> None:
        """Start the day: batteries at their initial SoC, no trades."""
        raise NotImplementedError

    def step(
        self, inputs: StepInputs, intents: Mapping[str, OrderIntent]
    ) -> StepOutcome:
        """Clear one period."""
        raise NotImplementedError
