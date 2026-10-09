"""The scenario: everything the user configures before stepping the market.

Only what a market step without RL needs: the network, the participants on it, the
market rules and the DSO. Plain data, edited by the Studio pages and read by the
``LocalEnergyMarket`` that runs the market on the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional


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

    code: str = "1-LV-rural1--0-sw"
    day: str = "2016-06-15"
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
    """A participant's battery ([P1] eq. 16): C_nom (``capacity_kwh``), SoC_min,
    SoC_max, η_charge, η_discharge. ``max_power_kw`` is not in eq. 16."""

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
    """Market rules ([P1] §3.3) and how participants bid.

    Attributes:
        mechanism: Pricing mechanism (``core/market/clearing_price.py``, [P1]
            §3.3.3).
        min_price: Lowest order price, p_min ([P1] eq. 2).
        max_price: Highest order price, p_max ([P1] eq. 2).
        min_quantity: Smallest order quantity (kWh), q_min ([P1] eq. 2).
        max_quantity: Largest order quantity (kWh), q_max ([P1] eq. 2).
        partner_preference: Participants name their nearest counterpart as
            preferred partner β ([P1] eq. 2; stage 1 of the clearing, §3.3.2).
        bid_margin: Where participants bid between the DSO's tariffs: sellers ask
            ``FiT + margin · spread``, buyers bid ``utility − margin · spread``.
            Below 0.5 bids and asks overlap and peers trade.
        bid_jitter: Random spread of the prices around that, as a share of the
            tariff spread, so the order book is not flat.
        seed: Seed of the jitter.
        ledger_difficulty: Proof-of-work difficulty of the trade ledger (0: off;
            [P1] §3.3.4).
    """

    mechanism: str = "average"
    min_price: float = 0.0
    max_price: float = 1.0
    min_quantity: float = 0.0
    max_quantity: float = 100.0
    partner_preference: bool = False
    bid_margin: float = 0.3
    bid_jitter: float = 0.1
    seed: int = 0
    ledger_difficulty: int = 0

    def problems(self) -> list[str]:
        """What makes these rules wrong or the peer market pointless."""
        found = []
        if self.bid_margin >= 0.5:
            found.append(
                "Bid margin is 0.5 or more: peers will not trade with each other."
            )
        if self.min_price > self.max_price:
            found.append("Min price is above max price.")
        if self.min_quantity > self.max_quantity:
            found.append("Min quantity is above max quantity.")
        return found


@dataclass
class DsoSetup:
    """DSO tariffs and grid fees ([P1] §3.3.1): p_FiT, p_utility and the fee
    factors f_* of [P1] eq. 8 (fees not charged yet)."""

    feed_in_tariff: float = 0.08
    utility_price: float = 0.30
    fees_charged: bool = False
    fees: dict[str, float] = field(default_factory=dict)

    def problems(self) -> list[str]:
        """Tariffs that break p_FiT < p_P2P < p_utility ([P1] §3.3.2), so peers
        gain nothing by trading with each other."""
        if self.feed_in_tariff >= self.utility_price:
            return [
                "Feed-in tariff is not below the utility price: no gain from peers."
            ]
        return []


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

    def problems(self, element_types: Optional[Mapping[str, str]] = None) -> list[str]:
        """What would make the market pointless or wrong, in plain words.

        Args:
            element_types: Element type per network element (``load``, ``sgen``,
                ``storage``), to check that someone can generate; skipped when
                ``None``.
        """
        found = []
        if not self.participants:
            found.append(
                "No participants: place them on the Grid & Participants page."
            )
        elif element_types is not None and not any(
            element_types.get(e) == "sgen" for p in self.participants for e in p.owns
        ):
            found.append(
                "No participant owns a generator: nobody has anything to sell."
            )
        return found + self.market.problems() + self.dso.problems()
