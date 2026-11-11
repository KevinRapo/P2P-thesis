"""The scenario: everything the user configures before stepping the market.

Only what a market step without RL needs: the network, the participants on it, the
market rules and the DSO. Plain data, edited by the Studio pages and read by the
``LocalEnergyMarket`` that runs the market on the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
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
        method: Where the DSO's fees read the line loading from: ``"powerflow"``
            (the AC power flow) or ``"graph"`` ([P1] §3.5: the step's trades along
            their paths, over a capacity per line). The power flow runs either way
            and is recorded; with ``"graph"`` it sets no fee.
        graph_capacity: The graph model's capacity per line: ``"paper"`` (a total
            spread over the lines in inverse proportion to their length, as the
            original's ``GridNetwork``) or ``"ratings"`` (each line's own rating).
        graph_total_kw: The total of ``"paper"``; ``None``: the sum of the line
            ratings ([P1] gives no value; the original uses 1e6 kW).
        load_scale, generation_scale, storage_scale: Factors on the power of every
            load, generator (``sgen``) and storage unit of the network, the
            participants' included, applied where the power is read
            (``scale_of``): a participant's demand and generation, its battery's
            capacity and power limit, and the background in the power flow. 1.0 is
            SimBench's network as it is; above it, a network under more stress
            (MP-4i).
    """

    code: str = "1-LV-rural1--0-sw"
    day: str = "2016-06-15"
    step_hours: float = 1.0
    background: str = "profiles"
    v_min_pu: float = 0.95
    v_max_pu: float = 1.05
    line_max_percent: float = 100.0
    method: str = "powerflow"
    graph_capacity: str = "paper"
    graph_total_kw: Optional[float] = None
    load_scale: float = 1.0
    generation_scale: float = 1.0
    storage_scale: float = 1.0

    def scale_of(self, kind: str) -> float:
        """The factor on an element of ``kind`` (``load``, ``sgen``, ``storage``;
        1.0 for anything else)."""
        return {
            "load": self.load_scale,
            "sgen": self.generation_scale,
            "storage": self.storage_scale,
        }.get(kind, 1.0)

    def problems(self) -> list[str]:
        """Scaling factors that make no sense."""
        return [
            f"{name.replace('_', ' ').capitalize()} {value} is negative."
            for name in ("load_scale", "generation_scale", "storage_scale")
            if (value := getattr(self, name)) < 0
        ]


# --------------------------------------------------------------------------------------
# Participants: who trades, where, with what
# --------------------------------------------------------------------------------------
@dataclass
class BatterySetup:
    """A participant's battery ([P1] eq. 16): C_nom (``capacity_kwh``), SoC_min,
    SoC_max, η_charge, η_discharge, and its power limit ``max_power_kw``, which eq. 16
    leaves out but [P1] §3.4 names ("maximum charge/discharge rates"). Every step
    is bounded by both: the energy the window leaves and the power limit over the
    step (``Battery.chargeable_kwh``, ``dischargeable_kwh``). Required: SimBench's
    storage units bring their own, ``placement.simbench_battery`` sizes one."""

    capacity_kwh: float
    max_power_kw: float
    min_soc: float = 0.1
    max_soc: float = 0.9
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    initial_soc: float = 0.5

    def scaled(self, factor: float) -> "BatterySetup":
        """The same battery with its capacity and power limit times ``factor``
        (``GridSetup.storage_scale``); its state of charge stays a share."""
        return BatterySetup(
            capacity_kwh=self.capacity_kwh * factor,
            max_power_kw=self.max_power_kw * factor,
            min_soc=self.min_soc,
            max_soc=self.max_soc,
            charge_efficiency=self.charge_efficiency,
            discharge_efficiency=self.discharge_efficiency,
            initial_soc=self.initial_soc,
        )

    def problems(self) -> list[str]:
        """What makes the battery's capacity, SoC window, efficiencies, start or
        power limit invalid for eq. 16."""
        found = []

        if self.capacity_kwh <= 0:
            found.append(f"capacity {self.capacity_kwh} kWh is not positive")

        if not 0 <= self.min_soc < self.max_soc <= 1:
            found.append(
                f"SoC window {self.min_soc}-{self.max_soc} is not inside 0-1"
            )

        for name in ("charge_efficiency", "discharge_efficiency"):
            if not 0 < getattr(self, name) <= 1:
                found.append(f"{name} {getattr(self, name)} is not in (0, 1]")

        if not self.min_soc <= self.initial_soc <= self.max_soc:
            found.append(f"initial SoC {self.initial_soc} is outside the window")

        if self.max_power_kw is None or self.max_power_kw <= 0:
            found.append(f"power limit {self.max_power_kw} kW is not positive")

        return found


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
        price_decimals: Decimals an order price is rounded to (2: whole cents).
        partner_preference: Participants name a preferred partner β on the other
            side ([P1] eq. 2; stage 1 of the clearing, §3.3.2).
        partner_reputation_weight: How the partner is chosen ([P1] §3.4): weight of
            the candidate's reputation against its closeness on the grid (0: the
            nearest, 1: the most reputable).
        bid_margin: Where participants bid between the DSO's tariffs: sellers ask
            ``FiT + margin · spread``, buyers bid ``utility − margin · spread``.
            Below 0.5 bids and asks overlap and peers trade.
        bid_jitter: Random spread of the prices around that, as a share of the
            tariff spread, so the order book is not flat.
        seed: Seed of the jitter.
        reliability_weight: w_rel of the reputation ([P1] eq. 12; not given in
            [P1], the original's value).
        fairness_weight: w_fair of the reputation ([P1] eq. 12).
        grid_weight: w_grid of the reputation ([P1] eq. 12).
        reputation_decay: Share of the old reputation kept per hour ([P1]
            §3.3.4 names a decay factor without a value). Applied per step as
            ``reputation_decay ** step_hours``, so the memory lasts the same time
            with hourly and quarter-hourly steps (M-43): 0.8 halves the old
            reputation in about 3.1 hours.
    """

    mechanism: str = "average"
    min_price: float = 0.0
    max_price: float = 1.0
    min_quantity: float = 0.0
    max_quantity: float = 100.0
    price_decimals: int = 2
    partner_preference: bool = False
    partner_reputation_weight: float = 0.5
    bid_margin: float = 0.3
    bid_jitter: float = 0.1
    seed: int = 0
    reliability_weight: float = 0.3
    fairness_weight: float = 0.2
    grid_weight: float = 0.5
    reputation_decay: float = 0.8

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

        weights = (self.reliability_weight, self.fairness_weight, self.grid_weight)

        if any(w < 0 for w in weights) or abs(sum(weights) - 1) > 1e-9:
            found.append("Reputation weights are not shares that add up to 1.")

        for name in ("reputation_decay", "partner_reputation_weight"):
            if not 0 <= getattr(self, name) <= 1:
                found.append(f"{name.replace('_', ' ').capitalize()} is not in 0-1.")

        return found


# --------------------------------------------------------------------------------------
# Time-of-use tariffs
# --------------------------------------------------------------------------------------
# The price files: JSON with a ``utility`` and a ``feed_in`` series, one price per
# market step of the day from 00:00, per kWh in the scenario's money unit.
PRICES_DIR = Path(__file__).resolve().parents[2] / "config" / "data"
FLAT_PRICES = {"utility": 0.30, "feed_in": 0.08}  # the default of ``DsoSetup.prices``


def price_files() -> list[str]:
    """The names of the price files in ``config/data/``."""
    return sorted(path.stem for path in PRICES_DIR.glob("*.json"))


def read_prices(name: str) -> dict:
    """The contents of the price file ``name``."""
    return json.loads((PRICES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def load_prices(prices: str | dict, step_hours: float) -> dict:
    """``prices`` in one form, whichever it was given in: the ``utility`` and
    ``feed_in`` series of the market's day, one price per step of ``step_hours`` hours.

    ``prices`` is the name of a file in ``config/data/``, or an object holding the two
    tariffs, each a series or one number for the whole day (``flat_prices``). It may
    add ``days``, the two tariffs of each date; those are what the market trades at
    (``price_days``), and the ones at the top are then the mean day."""
    if isinstance(prices, str):
        prices = read_prices(prices)

    steps = round(24 / step_hours)

    def day(tariffs: dict) -> dict:
        return tariffs | {
            name: _series(name, tariffs[name], steps, step_hours)
            for name in ("utility", "feed_in")
        }

    out = day(prices)

    if "days" in prices:
        out["days"] = {date: day(tariffs) for date, tariffs in prices["days"].items()}

    return out


def _series(name: str, value: float | list, steps: int, step_hours: float) -> list:
    """The series of one tariff: ``value``, or one number repeated for the day."""
    if isinstance(value, (int, float)):
        return [float(value)] * steps

    if len(value) != steps:
        raise ValueError(
            f"The {name} series has {len(value)} prices, but a day has {steps} steps "
            f"of {step_hours} h"
        )

    return value


def flat_prices(prices: str | dict) -> bool:
    """Whether ``prices`` are one number per tariff, all day."""
    return not isinstance(prices, str) and not any(
        isinstance(prices[name], list) for name in ("utility", "feed_in")
    )


def price_days(prices: dict) -> list[dict]:
    """The days of ``load_prices``' result: each date's series, or the one day."""
    return list(prices.get("days", {}).values()) or [prices]


def price_at(series: list, hour: float) -> float:
    """The price at ``hour`` (0-24, wrapping): the price of the series' step that
    holds that hour."""
    return float(series[int((hour % 24) * len(series) / 24)])


@dataclass
class DsoSetup:
    """DSO tariffs ([P1] §3.3.1), grid fees ([P1] eq. 8) and transmission losses
    ([P1] eq. 18). [P1] gives none of the fee factors; the defaults are the
    original code's.

    Attributes:
        prices: p_FiT, what the DSO pays per kWh it buys, and p_utility, what it
            charges per kWh it sells, the one entry for both, read by ``load_prices``:
            the name of a file in ``config/data/``, ``{"utility": 0.3, "feed_in":
            0.08}`` for flat tariffs, or the series themselves in that object. [P1]
            §3.4.4 lets the tariffs change per step.
        peer_charge_kwh: Grid and tax charge per kWh on a peer-to-peer trade, paid
            by the buyer; a trade with the DSO has it in the utility price. Peers
            trade below p_utility − this charge, so the buyer never pays more than
            the DSO would ask. Not in [P1]: 0 is the paper's market.
        fees_charged: Whether the fees are paid (always calculated and recorded).
        fee_buyer_share: Share of a peer-to-peer trade's fee the buyer pays; the
            seller pays the rest. A trade with the DSO is paid by the participant.
        loss_factor: κ of [P1] eq. 18, per km: l_ij = d_ij · q_ij · κ.
        congestion_factor: f_cong of [P1] eq. 8a.
        congestion_threshold: C_threshold of [P1] eq. 8a.
        voltage_factor: f_volt of [P1] eq. 8f, per km.
        voltage_threshold: V_threshold of [P1] eq. 8c.
        thermal_threshold: T_threshold of [P1] eq. 8g.
        thermal_cap: f_threshold of [P1] eq. 8d.
        imbalance_factor: f_imb of [P1] eq. 8b.
        zone_factor: f_zone of [P1] eq. 8e, the same-zone bonus.
        voltage_drop: V_drop of [P1] eq. 8c: ``"distance"`` (eq. 8f, f_volt ·
            d_ij) or ``"measured"`` (|V_a − V_b| between the trade's two buses in
            the step's power flow).
        losses: Who pays the network's losses. ``"trades"``: [P1] eq. 18, each
            trade's loss κ · d_ij · q_ij priced into its fee as F_trans. Or a rule
            of ``core/grid/losses.py`` (``"bcdla"``, ``"pro_rata"``): the step's
            measured power-flow losses shared out, each participant paying its
            share at the step's utility price (a negative share is paid back),
            and F_trans 0.
    """

    prices: str | dict = field(default_factory=lambda: dict(FLAT_PRICES))
    peer_charge_kwh: float = 0.0
    fees_charged: bool = True
    fee_buyer_share: float = 0.5
    loss_factor: float = 0.03
    congestion_factor: float = 0.5
    congestion_threshold: float = 0.8
    voltage_factor: float = 0.15
    voltage_threshold: float = 0.05
    thermal_threshold: float = 0.2
    thermal_cap: float = 0.3
    imbalance_factor: float = 0.15
    zone_factor: float = 0.15
    voltage_drop: str = "distance"
    losses: str = "trades"

    def problems(self, step_hours: float) -> list[str]:
        """Tariffs that break p_FiT < p_P2P < p_utility ([P1] §3.3.2), so peers
        gain nothing by trading with each other, prices that do not fit the market
        step of ``step_hours`` hours, and fee settings out of range."""
        found = []

        try:
            prices = load_prices(self.prices, step_hours)
        except (OSError, ValueError, KeyError) as error:
            return [f"The prices cannot be read: {error}"]

        hours = [step * step_hours for step in range(round(24 / step_hours))]
        below = (
            (hour, day)
            for day in price_days(prices)
            for hour in hours
            if price_at(day["feed_in"], hour)
            >= price_at(day["utility"], hour) - self.peer_charge_kwh
        )

        if (found_hour := next(below, None)) is not None:
            found.append(
                "Feed-in tariff is not below the utility price, less the peer "
                f"charge, at {found_hour[0]:g} h: no gain from peers."
            )

        if self.peer_charge_kwh < 0:
            found.append("Peer charge is negative.")

        if not 0 <= self.fee_buyer_share <= 1:
            found.append("Fee buyer share is not in 0-1.")

        if not 0 <= self.thermal_threshold < 1:
            found.append("Thermal threshold is not in 0-1 (1 excluded).")

        if self.voltage_drop not in ("distance", "measured"):
            found.append("Voltage drop is not 'distance' or 'measured'.")

        from core.grid.losses import LOSS_ALLOCATIONS

        if self.losses != "trades" and self.losses not in LOSS_ALLOCATIONS:
            found.append(
                f"Losses {self.losses!r} is not 'trades' or one of "
                f"{sorted(LOSS_ALLOCATIONS)}."
            )

        return found


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
                ``storage``), to check that someone can generate and that taken
                over storage has a battery; skipped when ``None``.
        """
        found = []

        if not self.participants:
            found.append("No participants: place them on the Scenario page.")
        elif element_types is not None and not any(
            element_types.get(e) == "sgen" for p in self.participants for e in p.owns
        ):
            found.append(
                "No participant owns a generator: nobody has anything to sell."
            )

        if element_types is not None:
            for p in self.participants:
                storage = [e for e in p.owns if element_types.get(e) == "storage"]
                if storage and p.battery is None:
                    found.append(
                        f"{p.id} takes over {', '.join(storage)} but has no "
                        "battery: the storage unit would disappear."
                    )

        for p in self.participants:
            if p.battery is not None:
                found.extend(f"{p.id} battery: {s}" for s in p.battery.problems())

        return (
            found
            + self.grid.problems()
            + self.market.problems()
            + self.dso.problems(self.grid.step_hours)
        )
