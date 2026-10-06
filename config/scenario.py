"""The scenario: everything the user configures before stepping the market.

Only what a market step without RL needs: the network, the participants on it, the
market rules and the DSO. Plain data, edited by the Studio pages and read by the
session that builds the market and the grid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------------------
# Grid: the network and its power flow
# --------------------------------------------------------------------------------------
@dataclass
class GridSetup:
    """The SimBench network and how its power flow runs.

    Attributes:
        code: SimBench code, e.g. ``"1-LV-rural1--0-sw"``.
        day: Day of the SimBench profile year, ``YYYY-MM-DD``.
        step_hours: Hours per market step (1.0 or 0.25).
        background: What the network's own elements do: ``"profiles"`` or ``"off"``.
        v_min_pu: Lowest allowed voltage.
        v_max_pu: Highest allowed voltage.
        line_max_percent: Line loading limit.
    """

    code: str = ""
    day: str = ""
    step_hours: float = 1.0
    background: str = "profiles"
    v_min_pu: float = 0.95
    v_max_pu: float = 1.05
    line_max_percent: float = 100.0


# --------------------------------------------------------------------------------------
# Participants: who trades, where, with what
# --------------------------------------------------------------------------------------
@dataclass
class BatterySetup:
    """A participant's battery ([P1] eq. 16)."""

    capacity_kwh: float
    min_soc: float = 0.1
    max_soc: float = 0.9
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    initial_soc: float = 0.5
    max_power_kw: Optional[float] = None


@dataclass
class ParticipantSetup:
    """One prosumer at one bus.

    Attributes:
        id: Participant ID.
        bus: Bus of the network.
        owns: Network elements (loads, sgens, storage) the participant replaces.
        battery: The battery, if any.
    """

    id: str
    bus: str
    owns: list[str] = field(default_factory=list)
    battery: Optional[BatterySetup] = None


# --------------------------------------------------------------------------------------
# Market and DSO: the rules and the tariffs
# --------------------------------------------------------------------------------------
@dataclass
class MarketSetup:
    """Market rules ([P1] §3.3)."""

    mechanism: str = "average"
    min_price: float = 0.0
    max_price: float = 1.0
    min_quantity: float = 0.0
    max_quantity: float = 100.0
    partner_preference: bool = False
    ledger_difficulty: int = 0


@dataclass
class DsoSetup:
    """DSO tariffs and grid fees ([P1] §3.3.1)."""

    feed_in_tariff: float = 0.08
    utility_price: float = 0.30
    fees_charged: bool = False
    fees: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# The whole scenario
# --------------------------------------------------------------------------------------
@dataclass
class Scenario:
    """One configured market on one network."""

    name: str = "untitled"
    grid: GridSetup = field(default_factory=GridSetup)
    participants: list[ParticipantSetup] = field(default_factory=list)
    market: MarketSetup = field(default_factory=MarketSetup)
    dso: DsoSetup = field(default_factory=DsoSetup)
