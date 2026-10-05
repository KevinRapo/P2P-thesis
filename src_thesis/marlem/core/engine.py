"""The market engine seam: what a simulation needs from "the market".

``EngineSpec`` is the plain-data description of one world for one day (agents with
their profiles, market rules, DSO tariffs); an engine is built from it. A
``MarketEngine`` runs it step by step: it shows each agent what it can see
(``views``), takes its intents, and reports what happened (``StepOutcome``).
The original ``LocalEnergyMarket`` sits behind this interface today
(``environment/engine_lem.py``); a cleaner engine can replace it later without
touching policies, the simulation loop, the checks or the Studio.

Energy is kWh per step, power kW, prices per kWh; ``step_hours`` converts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Protocol

from src_thesis.marlem.core.policy import AgentView, Intent


@dataclass(frozen=True)
class BatterySpec:
    """An agent's battery.

    Attributes:
        capacity_kwh: Nominal capacity.
        min_soc: Lowest allowed state of charge (fraction of capacity).
        max_soc: Highest allowed state of charge (fraction of capacity).
        charge_efficiency: Share of charged energy that is stored.
        discharge_efficiency: Share of stored energy that can be delivered.
        initial_soc: State of charge at the start of each day (fraction); the
            middle of the allowed range when ``None``.
        max_power_kw: Power limit; ``None`` for none (the engine has no limit).
    """

    capacity_kwh: float
    min_soc: float = 0.0
    max_soc: float = 1.0
    charge_efficiency: float = 1.0
    discharge_efficiency: float = 1.0
    initial_soc: Optional[float] = None
    max_power_kw: Optional[float] = None


@dataclass(frozen=True)
class AgentSpec:
    """One participant for one day.

    Attributes:
        id: Agent ID.
        bus: Network bus the agent sits on.
        capacity_kwh: Largest quantity per step the agent can trade.
        generation_kwh: Generation per step.
        demand_kwh: Demand per step.
        battery: The battery, if any.
    """

    id: str
    bus: str
    capacity_kwh: float
    generation_kwh: tuple[float, ...]
    demand_kwh: tuple[float, ...]
    battery: Optional[BatterySpec] = None


@dataclass(frozen=True)
class MarketSpec:
    """Market rules (02 §3.5).

    Attributes:
        min_price: Lowest order price.
        max_price: Highest order price.
        min_quantity: Smallest order quantity (kWh).
        max_quantity: Largest order quantity (kWh).
        mechanism: Clearing mechanism name, e.g. ``"average"``.
        ledger_difficulty: Proof-of-work difficulty of the trade log (at least 1).
        partner_preference: Whether agents choose their trading partners.
        async_orders: Whether orders get random timestamps within a step.
        match_threshold: Smallest matched quantity.
    """

    min_price: float = 0.0
    max_price: float = 1000.0
    min_quantity: float = 0.0
    max_quantity: float = 1000.0
    mechanism: str = "average"
    ledger_difficulty: int = 2
    partner_preference: bool = False
    async_orders: bool = True
    match_threshold: float = 1e-6


@dataclass(frozen=True)
class TariffSpec:
    """Where the DSO's tariffs come from (02 §3.6).

    Attributes:
        source: ``"csv"`` or ``"synthetic"``.
        feed_in_path: CSV file of feed-in tariffs (``csv`` only).
        utility_path: CSV file of utility prices (``csv`` only).
    """

    source: str = "synthetic"
    feed_in_path: Optional[str] = None
    utility_path: Optional[str] = None


@dataclass(frozen=True)
class EngineSpec:
    """One world for one day: everything an engine needs, as plain data.

    Attributes:
        agents: The participants, in agent order.
        market: Market rules.
        tariffs: DSO tariff source.
        fees: DSO fee factors and thresholds by name (``dso.fees``).
        steps: Steps of the day.
        step_hours: Hours per step (1.0 hourly, 0.25 for 15 minutes).
        seed: Seed of the day's randomness.
        day: The day, ``YYYY-MM-DD``.
        warnings: Things changed while building, e.g. profiles clipped.
    """

    agents: tuple[AgentSpec, ...]
    market: MarketSpec
    tariffs: TariffSpec
    steps: int = 24
    step_hours: float = 1.0
    seed: int = 1
    day: str = ""
    fees: Mapping[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepOutcome:
    """What happened in one step, as plain data.

    Attributes:
        step: The step (0-based).
        orders: Orders as placed: ``agent_id, price, quantity_kwh, is_buy``.
        trades: Trades: ``buyer_id, seller_id, price, quantity_kwh, distance,
            loss_kwh, fees`` (the DSO is a counterparty with ID ``"DSO"``).
        generation_kwh: Each agent's generation this step.
        demand_kwh: Each agent's demand this step.
        soc_before_kwh: Battery energy before the step (``None``: no battery).
        soc_after_kwh: Battery energy after the step.
        fit: DSO feed-in tariff of the step.
        utility_price: DSO utility price of the step.
        clearing_price: Volume-weighted average price of all trades.
        p2p_kwh: Energy traded between agents.
        dso_kwh: Energy traded with the DSO.
    """

    step: int
    orders: list[dict]
    trades: list[dict]
    generation_kwh: dict[str, float]
    demand_kwh: dict[str, float]
    soc_before_kwh: dict[str, Optional[float]]
    soc_after_kwh: dict[str, Optional[float]]
    fit: float
    utility_price: float
    clearing_price: float = 0.0
    p2p_kwh: float = 0.0
    dso_kwh: float = 0.0


@dataclass(frozen=True)
class Settlement:
    """What one agent did in one step, in energy (kWh).

    Attributes:
        agent_id: The agent.
        bus: Its network bus.
        generation_kwh: Own generation.
        demand_kwh: Own demand.
        sold_kwh: Energy sold in trades.
        bought_kwh: Energy bought in trades.
        charge_kwh: Energy the battery drew from the bus.
        discharge_kwh: Energy the battery delivered to the bus.
        soc_delta_kwh: Change of the battery's stored energy.
        production_kwh: What the grid sees flowing in: generation + discharge.
        consumption_kwh: What the grid sees flowing out: demand + charge.
        external_kwh: Net flow no trade covers, exchanged with the upstream grid.
    """

    agent_id: str
    bus: str
    generation_kwh: float
    demand_kwh: float
    sold_kwh: float
    bought_kwh: float
    charge_kwh: float
    discharge_kwh: float
    soc_delta_kwh: float
    production_kwh: float
    consumption_kwh: float
    external_kwh: float


class MarketEngine(Protocol):
    """Runs one day of the market step by step.

    Attributes:
        agent_ids: The agents, in order.
        n_steps: Steps in the day.
        step_hours: Hours per step.
        warnings: Things changed while building the engine.
    """

    agent_ids: list[str]
    n_steps: int
    step_hours: float
    warnings: list[str]

    def reset(self, seed: int) -> None:
        """Start the day."""

    def views(self) -> dict[str, AgentView]:
        """What each agent can see now."""

    def step(self, intents: Mapping[str, Intent]) -> StepOutcome:
        """Take every agent's intent, clear the market, report what happened."""
