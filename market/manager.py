"""MarketManager: the one class that runs the market, step by step.

The counterpart of ``LocalEnergyMarket`` (``lem.py``) in the original MARLEM,
without the learning parts (no observation, no reward). It owns the participants'
profiles and batteries, the clearing, the ledger and the step-time grid, and runs
one market step in the order of the paper ([P1] §3.9; docs: marlem/methodology.md
§3):

    1  validate   orders limited to the market bounds and to eq. 15
    2  orders     intents become orders; partners chosen if preferences are on
    3  clear      stage 1 preferences, stage 2 double auction, stage 3 DSO
    4  settle     energy, batteries (eq. 16), balance (eq. 13), profit (eq. 14)
    4' grid       what each participant physically did -> one power flow
    6  advance    clearing price, ledger block, clock

Phases 5 (reward and KPIs) and 7 (observation) of the paper are learning only.

A step can run at once (``step``) or one stage at a time (``start_step``, then
``advance`` until the step is recorded), so the Studio can show each stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from config.scenario import ParticipantSetup, Scenario
from grid import simbench
from grid.contract import GridAssessment, NetworkRef, ParticipantInjection
from grid.powerflow import SimBenchGrid
from market import bidding, clearing
from market.clearing import DSO_ID, ClearingRules, StageResult
from market.order import Order, Trade
from market.validation import Validator


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
    """What one participant did in one step ([P1] eq. 13, 14, 16).

    Attributes:
        generation_kwh, demand_kwh: Own generation and demand.
        bought_kwh, sold_kwh: Energy traded (with peers and the DSO).
        charge_kwh: Energy the battery drew from the bus.
        discharge_kwh: Energy the battery delivered to the bus.
        external_kwh: Energy no trade covers: + exported, − imported.
        soc_kwh: Battery energy after the step (``None``: no battery).
        balance_kwh: Eq. 13: (G − D) + (bought − sold).
        profit: Eq. 14 for this step: revenue − cost of its trades.
    """

    participant_id: str
    generation_kwh: float
    demand_kwh: float
    bought_kwh: float
    sold_kwh: float
    charge_kwh: float
    discharge_kwh: float
    external_kwh: float
    soc_kwh: Optional[float]
    balance_kwh: float
    profit: float


@dataclass
class PendingStep:
    """A step being played: its orders and the clearing stages run so far.

    Attributes:
        step: The step (0-based).
        inputs: Profiles and tariffs of the step.
        intents: Each participant's intent as given.
        orders: The orders as submitted, after validation (phase 1, 2).
        notes: What validation changed.
        stages: The clearing stages run so far.
    """

    step: int
    inputs: StepInputs
    intents: dict[str, OrderIntent]
    orders: tuple[Order, ...]
    notes: list[str] = field(default_factory=list)
    stages: list[StageResult] = field(default_factory=list)

    @property
    def open_orders(self) -> tuple[Order, ...]:
        """Orders still open: after the last stage, or as submitted."""
        return self.stages[-1].remaining if self.stages else self.orders

    @property
    def trades(self) -> list[Trade]:
        """Every trade of the stages run so far."""
        return [t for s in self.stages for t in s.trades]


@dataclass(frozen=True)
class StepRecord:
    """Everything one step produced.

    Attributes:
        step: The step (0-based).
        inputs: Profiles and tariffs of the step.
        orders: Orders as submitted.
        stages: The three clearing stages.
        participants: What each participant did.
        clearing_price: Volume-weighted price of the step's peer-to-peer trades
            (the previous one when there were none).
        grid: The power flow with the participants' injections.
        notes: What validation changed.
    """

    step: int
    inputs: StepInputs
    orders: tuple[Order, ...]
    stages: tuple[StageResult, ...]
    participants: dict[str, ParticipantOutcome]
    clearing_price: float
    grid: GridAssessment
    notes: tuple[str, ...] = ()

    @property
    def trades(self) -> list[Trade]:
        """Every trade of the step."""
        return [t for s in self.stages for t in s.trades]

    @property
    def p2p_kwh(self) -> float:
        """Energy traded between participants."""
        return sum(s.volume_kwh for s in self.stages if s.stage < 3)

    @property
    def dso_kwh(self) -> float:
        """Energy traded with the DSO."""
        return sum(s.volume_kwh for s in self.stages if s.stage == 3)


# --------------------------------------------------------------------------------------
# The manager
# --------------------------------------------------------------------------------------
class MarketManager:
    """The configured market on its network, run one step at a time.

    Args:
        scenario: The network, the participants, the market rules and the DSO.
    """

    def __init__(self, scenario: Scenario) -> None:
        if not scenario.participants:
            raise ValueError("The scenario has no participants")
        self.scenario = scenario
        self.participants: dict[str, ParticipantSetup] = {
            p.id: p for p in scenario.participants
        }
        self.grid = SimBenchGrid(
            scenario.grid, {p.id: list(p.owns) for p in scenario.participants}
        )
        self.history: list[StepRecord] = []
        self.pending: Optional[PendingStep] = None
        self.energy_kwh: dict[str, Optional[float]] = {}
        self.profit: dict[str, float] = {}
        self.reputation: dict[str, float] = {}
        self.ledger: Optional[Validator] = None
        self.clearing_price = 0.0
        self._generation: dict[str, list[float]] = {}
        self._demand: dict[str, list[float]] = {}
        self._distance: dict[tuple[str, str], float] = {}

    # --- Running the day -------------------------------------------------------------
    @property
    def current_step(self) -> int:
        """The next step to play (or the one being played)."""
        return len(self.history)

    @property
    def n_steps(self) -> int:
        """Steps in the day (24 hourly, 96 quarter-hourly)."""
        return round(24 / self.scenario.grid.step_hours)

    @property
    def done(self) -> bool:
        """Whether every step of the day is played."""
        return self.current_step >= self.n_steps

    def reset(self) -> None:
        """Read the participants' profiles, fill the batteries to their initial
        state of charge, prepare the grid and go back to step 0."""
        g, d = self.scenario.grid, self.scenario.dso
        self._read_profiles()
        self.energy_kwh = {
            pid: (p.battery.initial_soc * p.battery.capacity_kwh if p.battery else None)
            for pid, p in self.participants.items()
        }
        self.profit = {pid: 0.0 for pid in self.participants}
        self.reputation = {pid: 0.5 for pid in self.participants}
        difficulty = self.scenario.market.ledger_difficulty
        self.ledger = Validator(difficulty) if difficulty > 0 else None
        self.clearing_price = (d.feed_in_tariff + d.utility_price) / 2
        self.grid = SimBenchGrid(
            g, {p.id: list(p.owns) for p in self.participants.values()}
        )
        self.grid.reset()
        self._distance = {}
        self.history = []
        self.pending = None

    def start_step(
        self, intents: Optional[Mapping[str, OrderIntent]] = None
    ) -> PendingStep:
        """Phases 1 and 2: the step's inputs, intents (the bidding rule's when none
        are given), validation and orders. The clearing stages follow with
        ``advance``."""
        if self.pending is not None:
            raise RuntimeError("A step is already being played")
        if self.done:
            raise RuntimeError("The day is over")
        step = self.current_step
        inputs = self._inputs(step)
        if intents is None:
            intents = self._rule_intents(inputs)
        valid, notes = self._validate(inputs, intents)
        self.pending = PendingStep(
            step, inputs, dict(intents), self._orders(valid), notes
        )
        return self.pending

    def advance(self) -> StageResult | StepRecord:
        """Run the next part of the pending step: the next clearing stage, or, after
        stage 3, settlement, power flow and the record."""
        p = self.pending
        if p is None:
            raise RuntimeError("No step is being played; call start_step")
        if len(p.stages) < len(clearing.STAGES):
            result = clearing.STAGES[len(p.stages)](p.open_orders, self._rules(p))
            p.stages.append(result)
            return result
        outcomes = self._settle(p.inputs, p.trades)
        record = StepRecord(
            step=p.step,
            inputs=p.inputs,
            orders=p.orders,
            stages=tuple(p.stages),
            participants=outcomes,
            clearing_price=self._clearing_price(p.trades),
            grid=self._assess_grid(p.step, outcomes),
            notes=tuple(p.notes),
        )
        self._advance(record)
        return record

    def step(self, intents: Optional[Mapping[str, OrderIntent]] = None) -> StepRecord:
        """Play one whole step."""
        if self.pending is None:
            self.start_step(intents)
        while True:
            result = self.advance()
            if isinstance(result, StepRecord):
                return result

    def run_to_end(self) -> list[StepRecord]:
        """Play every remaining step of the day."""
        played = []
        while not self.done:
            played.append(self.step())
        return played

    # --- Inputs ----------------------------------------------------------------------
    def _read_profiles(self) -> None:
        """Each participant's generation and demand per step, in kWh, from the
        SimBench profiles of the elements it owns."""
        g = self.scenario.grid
        ref = NetworkRef("simbench", g.code)
        kinds = {e.id: e.element_type for e in simbench.elements(ref)}
        owned = [e for p in self.participants.values() for e in p.owns]
        resolution = "hourly" if g.step_hours == 1.0 else "15min"
        _, power = simbench.element_power(ref, owned, g.day, 1, resolution)
        for pid, p in self.participants.items():
            gen = [0.0] * self.n_steps
            dem = [0.0] * self.n_steps
            for e in p.owns:
                series = power.get(e, [])
                target = gen if kinds.get(e) == "sgen" else dem
                if kinds.get(e) == "storage":
                    continue  # storage elements follow the participant's battery
                for t, kw in enumerate(series[: self.n_steps]):
                    target[t] += kw * g.step_hours
            self._generation[pid] = gen
            self._demand[pid] = dem

    def _inputs(self, step: int) -> StepInputs:
        """Generation, demand and tariffs of ``step``."""
        d = self.scenario.dso
        return StepInputs(
            step=step,
            generation_kwh={
                pid: self._generation[pid][step] for pid in self.participants
            },
            demand_kwh={pid: self._demand[pid][step] for pid in self.participants},
            feed_in_tariff=d.feed_in_tariff,
            utility_price=d.utility_price,
        )

    def _rule_intents(self, inputs: StepInputs) -> dict[str, OrderIntent]:
        """The bidding rule's intents (``market/bidding.py``)."""
        views = {
            pid: bidding.BidView(
                pid,
                inputs.generation_kwh[pid],
                inputs.demand_kwh[pid],
                *self._battery_room(pid),
            )
            for pid in self.participants
        }
        rule = bidding.net_position(
            views,
            self.scenario.market,
            inputs.feed_in_tariff,
            inputs.utility_price,
            inputs.step,
        )
        intents = {
            pid: OrderIntent(pid, is_buy, price, quantity)
            for pid, (is_buy, price, quantity, _) in rule.items()
        }
        if self.scenario.market.partner_preference:
            intents = self._with_partners(intents)
        return intents

    def _with_partners(self, intents: dict[str, OrderIntent]) -> dict[str, OrderIntent]:
        """Each participant names the electrically nearest participant on the other
        side of the market as its preferred partner."""
        out = {}
        for pid, intent in intents.items():
            others = [o for o in intents.values() if o.is_buy != intent.is_buy]
            if not others:
                out[pid] = intent
                continue
            nearest = min(others, key=lambda o: self._km(pid, o.participant_id))
            out[pid] = OrderIntent(
                pid,
                intent.is_buy,
                intent.price,
                intent.quantity_kwh,
                nearest.participant_id,
            )
        return out

    def _km(self, a: str, b: str) -> float:
        """Line length between two participants' buses (cached)."""
        key = (a, b) if a < b else (b, a)
        if key not in self._distance:
            self._distance[key] = self.grid.electrical_distance(
                self.participants[a].bus, self.participants[b].bus
            )
        return self._distance[key]

    # --- Phases 1 and 2: validate, orders --------------------------------------------
    def _battery_room(self, pid: str) -> tuple[float, float]:
        """(chargeable, dischargeable) energy at the bus this step, eq. 15c-d with
        efficiencies and the power limit."""
        p = self.participants[pid]
        b, e = p.battery, self.energy_kwh.get(pid)
        if b is None or e is None:
            return 0.0, 0.0
        cap = b.max_power_kw * self.scenario.grid.step_hours if b.max_power_kw else None
        charge = max(0.0, b.max_soc * b.capacity_kwh - e) / b.charge_efficiency
        discharge = max(0.0, e - b.min_soc * b.capacity_kwh) * b.discharge_efficiency
        if cap is not None:
            charge, discharge = min(charge, cap), min(discharge, cap)
        return charge, discharge

    def _validate(
        self, inputs: StepInputs, intents: Mapping[str, OrderIntent]
    ) -> tuple[dict[str, OrderIntent], list[str]]:
        """Phase 1: limit each intent to the market bounds and to what is
        physically possible (eq. 15a-b)."""
        m = self.scenario.market
        valid, notes = {}, []
        for pid, i in intents.items():
            if pid not in self.participants:
                notes.append(f"{pid}: not a participant, dropped")
                continue
            charge, discharge = self._battery_room(pid)
            net = inputs.generation_kwh[pid] - inputs.demand_kwh[pid]
            most = max(0.0, -net) + charge if i.is_buy else max(0.0, net) + discharge
            quantity = min(i.quantity_kwh, most, m.max_quantity)
            price = min(m.max_price, max(m.min_price, i.price))
            if quantity < i.quantity_kwh - 1e-9:
                notes.append(
                    f"{pid}: {i.quantity_kwh:.2f} kWh limited to {quantity:.2f}"
                )
            if price != i.price:
                notes.append(f"{pid}: price {i.price:.3f} limited to {price:.3f}")
            if quantity <= max(m.min_quantity, 1e-9):
                continue
            valid[pid] = OrderIntent(pid, i.is_buy, price, quantity, i.partner_id)
        return valid, notes

    def _orders(self, intents: Mapping[str, OrderIntent]) -> tuple[Order, ...]:
        """Phase 2: intents to orders; arrival order is the participants' order."""
        rank = {pid: n for n, pid in enumerate(self.participants)}
        return tuple(
            Order(
                id=f"{pid}-{self.current_step}",
                agent_id=pid,
                price=i.price,
                quantity=i.quantity_kwh,
                is_buy=i.is_buy,
                timestamp=float(rank[pid]),
                location=self.participants[pid].bus,
                partner_id=i.partner_id,
            )
            for pid, i in intents.items()
        )

    # --- Phase 3: clearing -----------------------------------------------------------
    def _rules(self, p: PendingStep) -> ClearingRules:
        return ClearingRules(
            mechanism=self.scenario.market.mechanism,
            feed_in_tariff=p.inputs.feed_in_tariff,
            utility_price=p.inputs.utility_price,
            reference_price=self.clearing_price,
            reputation=self.reputation,
        )

    def _clearing_price(self, trades: list[Trade]) -> float:
        """Volume-weighted price of the peer-to-peer trades; the previous price when
        there were none."""
        p2p = [t for t in trades if t.stage < 3]
        volume = sum(t.quantity for t in p2p)
        if volume <= 0:
            return self.clearing_price
        return sum(t.price * t.quantity for t in p2p) / volume

    # --- Phase 4: settlement and the grid --------------------------------------------
    def _settle(
        self, inputs: StepInputs, trades: list[Trade]
    ) -> dict[str, ParticipantOutcome]:
        """Energy tracking, batteries (eq. 16), balance (eq. 13), profit (eq. 14).

        After its trades a participant has ``G − D + bought − sold`` left at its
        bus: a surplus charges its battery, a deficit discharges it, and what the
        battery cannot take or give is exchanged with the upstream grid untraded.
        """
        out = {}
        for pid, p in self.participants.items():
            bought = sum(t.quantity for t in trades if t.buyer_id == pid)
            sold = sum(t.quantity for t in trades if t.seller_id == pid)
            profit = sum(t.price * t.quantity for t in trades if t.seller_id == pid)
            profit -= sum(t.price * t.quantity for t in trades if t.buyer_id == pid)
            g, d = inputs.generation_kwh[pid], inputs.demand_kwh[pid]
            net = g - d + bought - sold
            charge_room, discharge_room = self._battery_room(pid)
            charge = discharge = 0.0
            if net > 0:
                charge = min(net, charge_room)
            else:
                discharge = min(-net, discharge_room)
            e = self.energy_kwh.get(pid)
            if e is not None and p.battery is not None:
                e += charge * p.battery.charge_efficiency
                e -= discharge / p.battery.discharge_efficiency
                self.energy_kwh[pid] = e
            out[pid] = ParticipantOutcome(
                participant_id=pid,
                generation_kwh=g,
                demand_kwh=d,
                bought_kwh=bought,
                sold_kwh=sold,
                charge_kwh=charge,
                discharge_kwh=discharge,
                external_kwh=net - charge + discharge,
                soc_kwh=self.energy_kwh.get(pid),
                balance_kwh=(g - d) + (bought - sold),
                profit=profit,
            )
        return out

    def _injections(
        self, outcomes: Mapping[str, ParticipantOutcome]
    ) -> list[ParticipantInjection]:
        """Each participant's net power at its bus, from what it physically did:
        generation and discharge flow in, demand and charge flow out."""
        h = self.scenario.grid.step_hours
        out = []
        for pid, o in outcomes.items():
            production = (o.generation_kwh + o.discharge_kwh) / h
            consumption = (o.demand_kwh + o.charge_kwh) / h
            out.append(
                ParticipantInjection(
                    pid,
                    self.participants[pid].bus,
                    production,
                    consumption,
                    production - consumption,
                )
            )
        return out

    def _assess_grid(
        self, step: int, outcomes: Mapping[str, ParticipantOutcome]
    ) -> GridAssessment:
        """Phase 4': one power flow with the participants' injections."""
        return self.grid.assess(step, self._injections(outcomes))

    # --- Phase 6: advance ------------------------------------------------------------
    def _advance(self, record: StepRecord) -> None:
        """Profit, clearing price, ledger block, clock. Reputation stays at its
        start value for now."""
        for pid, o in record.participants.items():
            self.profit[pid] += o.profit
        self.clearing_price = record.clearing_price
        if self.ledger is not None:
            for t in record.trades:
                self.ledger.add_trade(t)
            if self.ledger.pending_trades:
                self.ledger._create_new_block()
        self.history.append(record)
        self.pending = None


__all__ = [
    "DSO_ID",
    "MarketManager",
    "OrderIntent",
    "ParticipantOutcome",
    "PendingStep",
    "StepInputs",
    "StepRecord",
]
