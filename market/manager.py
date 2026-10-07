"""MarketManager: the one class that runs the market, step by step.

The counterpart of ``LocalEnergyMarket`` (``lem.py``) in the original MARLEM,
without the learning parts (no observation, no reward). It owns the participants,
the DSO, the matcher, the ledger and the step-time grid, and runs one market step
in the order of the paper ([P1] §3.9, Fig. 4; docs: marlem/methodology.md §3):

    1  validate     orders limited to the market bounds and to what is physically
                    possible (eq. 15)
    2  orders       intents become orders; a partner is chosen when none is given
    3  clear        three-stage clearing: preferences, double auction, DSO
    4  settle       energy tracking and batteries (eq. 13, 14, 16)
    4' grid         what each participant physically did -> one power flow
    6  advance      reputation, ledger block, clock

Phases 5 (reward and KPIs) and 7 (observation) of the paper are learning only and
not part of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from config.scenario import Scenario
from grid.contract import GridAssessment, ParticipantInjection
from grid.powerflow import SimBenchGrid


# --------------------------------------------------------------------------------------
# What goes in and comes out of one step
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class OrderIntent:
    """What one participant wants to trade this step (the paper's action)."""

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
class StepRecord:
    """Everything one step produced: the market's outcome and the network's state.

    Attributes:
        step: The step (0-based).
        inputs: Profiles and tariffs of the step.
        orders: Orders as placed, after validation.
        trades: Executed trades (the DSO is a counterparty with ID ``"DSO"``).
        participants: What each participant did.
        clearing_price: Volume-weighted price of the step's trades.
        grid: The power flow with the participants' injections.
    """

    step: int
    inputs: StepInputs
    orders: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    participants: dict[str, ParticipantOutcome] = field(default_factory=dict)
    clearing_price: float = 0.0
    grid: Optional[GridAssessment] = None


# --------------------------------------------------------------------------------------
# The manager
# --------------------------------------------------------------------------------------
class MarketManager:
    """The configured market on its network, run one step at a time.

    Args:
        scenario: The network, the participants, the market rules and the DSO.
    """

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.grid: SimBenchGrid | None = None
        self.history: list[StepRecord] = []

    # --- Running the day -------------------------------------------------------------
    @property
    def current_step(self) -> int:
        """The next step to play."""
        return len(self.history)

    @property
    def n_steps(self) -> int:
        """Steps in the day (24 hourly, 96 quarter-hourly)."""
        return round(24 / self.scenario.grid.step_hours)

    def reset(self) -> None:
        """Build the participants, the DSO, the matcher and the grid; go back to
        step 0 with batteries at their initial state of charge."""
        raise NotImplementedError

    def step(self, intents: Mapping[str, OrderIntent] | None = None) -> StepRecord:
        """Play the next step: phases 1-6 in order; the record is kept in
        ``history``.

        Args:
            intents: Each participant's order; participants without one place
                none.
        """
        raise NotImplementedError

    def run_to_end(self) -> list[StepRecord]:
        """Play every remaining step of the day."""
        raise NotImplementedError

    # --- The phases of one step ------------------------------------------------------
    def _inputs(self, step: int) -> StepInputs:
        """Generation, demand and tariffs of ``step``."""
        raise NotImplementedError

    def _validate(self, inputs: StepInputs, intents: Mapping[str, OrderIntent]):
        """Phase 1: limit each intent to the market bounds and to eq. 15."""
        raise NotImplementedError

    def _orders(self, intents: Mapping[str, OrderIntent]):
        """Phase 2: intents to orders; choose a partner where none is given."""
        raise NotImplementedError

    def _clear(self, orders):
        """Phase 3: preferences, double auction, DSO for the residual."""
        raise NotImplementedError

    def _settle(self, inputs: StepInputs, trades) -> dict[str, ParticipantOutcome]:
        """Phase 4: energy tracking, batteries, balance and profit."""
        raise NotImplementedError

    def _assess_grid(
        self, step: int, outcomes: Mapping[str, ParticipantOutcome]
    ) -> GridAssessment:
        """Phase 4': the participants' physical flows as injections, one power
        flow."""
        raise NotImplementedError

    def _injections(
        self, inputs: StepInputs, outcomes: Mapping[str, ParticipantOutcome]
    ) -> list[ParticipantInjection]:
        """Each participant's net power at its bus, from what it physically did."""
        raise NotImplementedError

    def _advance(self, record: StepRecord) -> None:
        """Phase 6: reputation, ledger block, clock."""
        raise NotImplementedError
