"""LocalEnergyMarket: the one class that runs the market, step by step.

Named as in the original MARLEM (``LocalEnergyMarket`` in ``lem.py``), but
without the learning parts (no observation, no reward). It holds the participants
(``core/market/agent/der.py``), the DSO (``core/market/dso.py``) and the
step-time grid, and runs one market step in the order of the paper ([P1] §3.9;
docs: marlem/methodology.md §3). Each element computes its own equations; the
market only calls them in order:

    1  validate   orders limited to the market bounds and to each participant's
                  eq. 15a-b (``Participant.max_sell_kwh``, ``max_buy_kwh``)
    2  orders     intents become orders; partners chosen by reputation and
                  distance if preferences are on (``Participant.choose_partner``)
    3  clear      stage 1 preferences, stage 2 double auction, stage 3 DSO
                  (§3.3.2, Algorithm 1; ``core/market/clearing.py``, ``Dso.clear``);
                  the DSO gives every trade its distance and loss (eq. 18)
                  (``Dso.assess``)
    4  settle     each participant: balance (eq. 13), trading profit (eq. 14),
                  battery (eq. 16) (``Participant.settle``)
    4' grid       what each participant physically did -> one power flow
                  (``Participant.injection``; replaces the graph model of §3.5.3)
    4" fees       the DSO sees the step's line loading (``Dso.observe``): this power
                  flow's, or with ``grid.method = "graph"`` the paper's graph model
                  (``GraphGrid``: the trades along their paths, §3.5.3), and gives
                  every trade its fee (eq. 8) from it (``Dso.charge``); each participant
                  pays its share (``Participant.pay_fees``); the DSO: its balance
                  (eq. 7) and fees (``Dso.settle``)
    6  advance    reputation (eq. 12 with its decay;
                  ``ReputationHandler.update_reputation``), clearing price, clock

Phases 5 (reward and KPIs) and 7 (observation) of the paper are learning only.

A step can run at once (``step``) or one stage at a time (``start_step``, then
``advance`` until the step is recorded), so the Studio can show each stage.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from typing import Mapping, Optional

from core.config.scenario import BatterySetup, Scenario
from core.grid import simbench
from core.grid.contract import GridAssessment, GridPath, NetworkRef
from core.grid.graph import GraphGrid
from core.grid.powerflow import SimBenchGrid
from core.market import clearing
from core.market.agent import rule_based_bid
from core.market.agent.battery import Battery
from core.market.agent.der import (
    Participant,
    ParticipantOutcome,
    profiles_from_elements,
)
from core.market.clearing import ClearingRules, StageResult
from core.market.dso import DSO_ID, Dso, DsoOutcome
from core.market.order import Order, Trade
from core.market.reputation import ReputationHandler, ReputationScore


# --------------------------------------------------------------------------------------
# What goes in and comes out of one step
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class OrderIntent:
    """What one participant wants to trade this step: the paper's action
    a_i = <p_bid, q_bid, α, β> ([P1] eq. 2)."""

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
        generation_kwh: Each participant's generation G_t.
        demand_kwh: Each participant's demand D_t.
        feed_in_tariff: p_FiT, what the DSO pays per kWh ([P1] §3.3.1).
        utility_price: p_utility, what the DSO charges per kWh ([P1] §3.3.1).
    """

    step: int
    generation_kwh: Mapping[str, float]
    demand_kwh: Mapping[str, float]
    feed_in_tariff: float
    utility_price: float


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

    @property
    def grid_balance_kwh(self) -> float:
        """B_grid before stage 3 ([P1] eq. 20): energy offered minus energy asked
        (+ excess supply). Trades between peers do not change it."""
        return _balance(self.orders)


@dataclass(frozen=True)
class StepRecord:
    """Everything one step produced.

    Attributes:
        step: The step (0-based).
        inputs: Profiles and tariffs of the step.
        orders: Orders as submitted.
        stages: The three clearing stages ([P1] §3.3.2).
        participants: What each participant did ([P1] eq. 13, 14, 16).
        clearing_price: Volume-weighted price of the step's peer-to-peer trades
            (the previous one when there were none); UpdateMarketState of [P1]
            Algorithm 1.
        grid: The power flow with the participants' injections (in place of the
            grid state update of [P1] §3.5.3), whatever ``grid.method``: what
            physically happened.
        dso: What the DSO did: its balance (eq. 7), revenue and fees.
        notes: What validation changed.
        reputation: Each participant's reputation update ([P1] eq. 12, §3.3.4):
            its three components, score and reputation after the step.
        signal: With ``grid.method = "graph"``, the graph model's line loading
            the fees were charged on; ``None`` with the power flow (``grid``).
    """

    step: int
    inputs: StepInputs
    orders: tuple[Order, ...]
    stages: tuple[StageResult, ...]
    participants: dict[str, ParticipantOutcome]
    clearing_price: float
    grid: GridAssessment
    dso: DsoOutcome
    notes: tuple[str, ...] = ()
    reputation: dict[str, ReputationScore] = field(default_factory=dict)
    signal: Optional[GridAssessment] = None

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

    @property
    def grid_balance_kwh(self) -> float:
        """B_grid before stage 3 ([P1] eq. 20): offered minus asked."""
        return _balance(self.orders)

    @property
    def losses_kwh(self) -> float:
        """Transmission losses of the step's trades ([P1] eq. 18), recorded."""
        return sum(t.transmission_loss for t in self.trades)

    @property
    def fees(self) -> float:
        """Grid fees of the step's trades ([P1] eq. 8), charged or not."""
        return sum(t.fees for t in self.trades)


def _balance(orders: tuple[Order, ...]) -> float:
    """Energy offered minus energy asked."""
    return sum(-o.quantity if o.is_buy else o.quantity for o in orders)


# --------------------------------------------------------------------------------------
# The market
# --------------------------------------------------------------------------------------
class LocalEnergyMarket:
    """The configured market on its network, run one step at a time.

    Args:
        scenario: The network, the participants, the market rules and the DSO. The
            market keeps its own copy: later edits to the caller's scenario do
            not change a market being played.
    """

    def __init__(self, scenario: Scenario) -> None:
        if not scenario.participants:
            raise ValueError("The scenario has no participants")
        scenario = self.scenario = deepcopy(scenario)
        self.grid = SimBenchGrid(
            scenario.grid, {p.id: list(p.owns) for p in scenario.participants}
        )
        self.participants: dict[str, Participant] = {}
        d, m = scenario.dso, scenario.market
        self.dso = Dso(**asdict(d))
        self.reputation_handler = ReputationHandler(
            reliability_weight=m.reliability_weight,
            fairness_weight=m.fairness_weight,
            grid_weight=m.grid_weight,
            decay=m.reputation_decay**scenario.grid.step_hours,  # per hour (M-43)
        )
        self.history: list[StepRecord] = []
        self.pending: Optional[PendingStep] = None
        self.clearing_price = 0.0
        self._paths: dict[tuple[str, str], GridPath] = {}
        self._upstream_paths: dict[str, GridPath] = {}
        self.graph: Optional[GraphGrid] = None

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
        """Build the participants from their profiles (batteries at their initial
        state of charge), the DSO, prepare the grid and go back to step 0."""
        g = self.scenario.grid
        self.participants = self._build_participants()
        self.dso.reset()
        self.clearing_price = self.dso.market_price()
        self.grid = SimBenchGrid(
            g, {p.id: list(p.owns) for p in self.scenario.participants}
        )
        self.grid.reset()
        self.graph = self._graph_model()
        self._paths = {}
        self._upstream_paths = {}
        self.history = []
        self.pending = None

    def start_step(
        self, intents: Optional[Mapping[str, OrderIntent]] = None
    ) -> PendingStep:
        """Phases 1 and 2 ([P1] §3.9; Phase 1 of Algorithm 1): the step's inputs,
        intents (the bidding rule's when none are given), validation and orders.
        The clearing stages follow with ``advance``."""
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
        """Run the next part of the pending step: the next clearing stage (phase 3,
        [P1] §3.3.2), or, after stage 3, settlement, power flow, fees and the
        record (phases 4 and 6, [P1] §3.9)."""
        p = self.pending
        if p is None:
            raise RuntimeError("No step is being played; call start_step")
        if len(p.stages) < len(clearing.STAGES):
            result = clearing.STAGES[len(p.stages)](p.open_orders, self._rules(p))
            p.stages.append(result)
            return result
        outcomes = self._settle(p.inputs, p.trades)
        grid = self._assess_grid(p.step, outcomes)
        signal = self._grid_signal(p, grid)
        stages = self._charge_fees(p, signal, grid)
        trades = [t for s in stages for t in s.trades]
        outcomes = {
            pid: self.participants[pid].pay_fees(o, trades)
            for pid, o in outcomes.items()
        }
        record = StepRecord(
            step=p.step,
            inputs=p.inputs,
            orders=p.orders,
            stages=stages,
            participants=outcomes,
            clearing_price=self._clearing_price(trades),
            grid=grid,
            dso=self.dso.settle(trades),
            notes=tuple(p.notes),
            signal=signal if signal is not grid else None,
        )
        record = self._update_reputation(record)
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
        """Play every remaining step of the day (phase 8 of [P1] §3.9: stop after
        the last period)."""
        played = []
        while not self.done:
            played.append(self.step())
        return played

    # --- Inputs ----------------------------------------------------------------------
    def _build_participants(self) -> dict[str, Participant]:
        """One ``Participant`` per scenario participant, with its generation and
        demand from the SimBench profiles of the elements it owns (in place of the
        profiles of [P1] §3.4.4)."""
        g = self.scenario.grid
        ref = NetworkRef("simbench", g.code)
        kinds = {e.id: e.element_type for e in simbench.elements(ref)}
        owned = [e for p in self.scenario.participants for e in p.owns]
        resolution = "hourly" if g.step_hours == 1.0 else "15min"
        _, power = simbench.element_power(ref, owned, g.day, 1, resolution)
        out = {}
        for p in self.scenario.participants:
            generation, demand = profiles_from_elements(
                p.owns, kinds, power, g.step_hours, self.n_steps
            )
            out[p.id] = Participant(
                id=p.id,
                bus=p.bus,
                owns=p.owns,
                generation_kwh=generation,
                demand_kwh=demand,
                battery=self._battery(p.battery),
            )
        return out

    def _battery(self, b: Optional[BatterySetup]) -> Optional[Battery]:
        """The configured battery as a ``Battery`` ([P1] eq. 16); ``None`` without
        one."""
        if b is None:
            return None
        return Battery(**asdict(b), step_hours=self.scenario.grid.step_hours)

    def _inputs(self, step: int) -> StepInputs:
        """G_t, D_t, p_FiT and p_utility of ``step``. The tariffs are fixed for the
        day; [P1] §3.4.4 lets them change per step."""
        people = self.participants.items()
        return StepInputs(
            step=step,
            generation_kwh={pid: p.generation_kwh[step] for pid, p in people},
            demand_kwh={pid: p.demand_kwh[step] for pid, p in people},
            feed_in_tariff=self.dso.feed_in_tariff,
            utility_price=self.dso.utility_price,
        )

    def _rule_intents(self, inputs: StepInputs) -> dict[str, OrderIntent]:
        """The bidding rule's intents (``core/market/agent/rule_based_bid.py``)."""
        views = {
            pid: rule_based_bid.BidView(
                pid,
                inputs.generation_kwh[pid],
                inputs.demand_kwh[pid],
                *p.battery_room(),
            )
            for pid, p in self.participants.items()
        }
        rule = rule_based_bid.net_position(
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
        """Each participant names a preferred partner β ([P1] eq. 2) on the other
        side of the market, by reputation and distance
        (``Participant.choose_partner``, [P1] §3.4)."""
        reputation = {pid: q.reputation for pid, q in self.participants.items()}
        weight = self.scenario.market.partner_reputation_weight
        out = {}
        for pid, i in intents.items():
            others = [
                o.participant_id for o in intents.values() if o.is_buy != i.is_buy
            ]
            partner = self.participants[pid].choose_partner(
                others,
                lambda other: self._path(pid, other).distance_km,
                reputation,
                weight,
            )
            out[pid] = OrderIntent(pid, i.is_buy, i.price, i.quantity_kwh, partner)
        return out

    def distance_km(self, a: str, b: str) -> float:
        """The grid distance d_ij ([P1] §3.5.1) between participants ``a`` and ``b``,
        km along the lines; with ``b`` the DSO (``DSO_ID``), to the transformer's
        busbar (the route of a trade with the DSO). Topology only: the same on
        every day. Needs the network, so the market must have been ``reset``."""
        if b == DSO_ID:
            return self._upstream(a).distance_km
        return self._path(a, b).distance_km

    def _path(self, a: str, b: str) -> GridPath:
        """The grid path between two participants' buses (cached): distance d_ij
        ([P1] §3.5.1), lines and zones."""
        key = (a, b) if a < b else (b, a)
        if key not in self._paths:
            self._paths[key] = self.grid.path(
                self.participants[key[0]].bus, self.participants[key[1]].bus
            )
        return self._paths[key]

    def _upstream(self, pid: str) -> GridPath:
        """A participant's path to the transformer's busbar (cached): the route of
        its trades with the DSO."""
        if pid not in self._upstream_paths:
            bus = self.participants[pid].bus
            self._upstream_paths[pid] = self.grid.path_upstream(bus)
        return self._upstream_paths[pid]

    # --- Phases 1 and 2: validate, orders --------------------------------------------
    def _validate(
        self, inputs: StepInputs, intents: Mapping[str, OrderIntent]
    ) -> tuple[dict[str, OrderIntent], list[str]]:
        """Phase 1 ([P1] §3.9): limit each intent to the market bounds ([P1] eq. 2,
        §3.2.3) and to what the participant can physically deliver or take ([P1]
        eq. 15a-b)."""
        m = self.scenario.market
        valid, notes = {}, []
        for pid, i in intents.items():
            if pid not in self.participants:
                notes.append(f"{pid}: not a participant, dropped")
                continue
            p, step = self.participants[pid], inputs.step
            most = p.max_buy_kwh(step) if i.is_buy else p.max_sell_kwh(step)
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
        """Phase 2 ([P1] §3.9): intents to orders; arrival order is the
        participants' order."""
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
        """Phase 3 ([P1] §3.9): what the stages need besides the orders: the
        mechanism ([P1] §3.3.3), p_ref ([P1] eq. 11), reputation ([P1] eq. 12),
        the grid paths and the market's balance (for the DSO's fees, eq. 8)."""
        return ClearingRules(
            mechanism=self.scenario.market.mechanism,
            dso=self.dso,
            reference_price=self.clearing_price,
            reputation={pid: q.reputation for pid, q in self.participants.items()},
            path=self._path,
            upstream=self._upstream,
        )

    def _clearing_price(self, trades: list[Trade]) -> float:
        """Volume-weighted price of the peer-to-peer trades; the previous price when
        there were none. Next step's p_ref ([P1] eq. 11)."""
        p2p = [t for t in trades if t.stage < 3]
        volume = sum(t.quantity for t in p2p)
        if volume <= 0:
            return self.clearing_price
        return sum(t.price * t.quantity for t in p2p) / volume

    # --- Phase 4: settlement and the grid --------------------------------------------
    def _settle(
        self, inputs: StepInputs, trades: list[Trade]
    ) -> dict[str, ParticipantOutcome]:
        """Phase 4 ([P1] §3.9): each participant settles its trades
        (``Participant.settle``: [P1] eq. 13, 14, 16)."""
        return {
            pid: p.settle(inputs.step, trades) for pid, p in self.participants.items()
        }

    def _assess_grid(
        self, step: int, outcomes: Mapping[str, ParticipantOutcome]
    ) -> GridAssessment:
        """Phase 4': one power flow with each participant's injection
        (``Participant.injection``), in place of the grid update of [P1] §3.5.3
        (flows, eq. 19; balance, eq. 20)."""
        h = self.scenario.grid.step_hours
        injections = [
            self.participants[pid].injection(o, h) for pid, o in outcomes.items()
        ]
        return self.grid.assess(step, injections)

    def _graph_model(self) -> Optional[GraphGrid]:
        """The paper's graph model on this network when ``grid.method`` is
        ``"graph"``, else ``None``."""
        g = self.scenario.grid
        if g.method == "powerflow":
            return None
        if g.method != "graph":
            raise ValueError("grid.method must be 'powerflow' or 'graph'")
        return GraphGrid(self.grid.line_table(), g.graph_capacity, g.graph_total_kw)

    def _grid_signal(self, p: PendingStep, grid: GridAssessment) -> GridAssessment:
        """The line loading the fees are charged on: the power flow's, or the
        graph model's from this step's trades, each along the path its fee uses
        (``Dso.charge``) at q / Δt kW."""
        if self.scenario.grid.method == "powerflow":
            return grid
        if self.graph is None:
            self.graph = self._graph_model()
        h = self.scenario.grid.step_hours
        flows = [
            (self.dso.trade_path(t, self._path, self._upstream), t.quantity / h)
            for t in p.trades
        ]
        return self.graph.assess(p.step, flows)

    def _charge_fees(
        self, p: PendingStep, signal: GridAssessment, grid: GridAssessment
    ) -> tuple[StageResult, ...]:
        """Phase 4": the DSO sees the step's line loading (``signal``: the power
        flow's or the graph model's) and the measured voltages of the power flow
        (``grid``) (``Dso.observe``), and gives every trade its fee (eq. 8) from
        them (``Dso.charge``). The stages with their trades charged."""
        self.dso.observe(signal, measured=grid)
        charged = iter(
            self.dso.charge(p.trades, self._path, self._upstream, p.grid_balance_kwh)
        )
        return tuple(
            replace(s, trades=tuple(next(charged) for _ in s.trades)) for s in p.stages
        )

    # --- Phase 6: advance ------------------------------------------------------------
    def _update_reputation(self, record: StepRecord) -> StepRecord:
        """Phase 6 ([P1] §3.9): every participant's reputation from the step's
        outcome, by the reputation module (``ReputationHandler.update_reputation``,
        [P1] eq. 12 and its decay), as the original's ``lem.py`` did; the record
        with the updates."""
        updates = {}
        for pid, participant in self.participants.items():
            update = self.reputation_handler.update_reputation(participant, record)
            participant.reputation = update.reputation
            updates[pid] = update
        return replace(record, reputation=updates)

    def _advance(self, record: StepRecord) -> None:
        """Phase 6 ([P1] §3.9): clearing price, clock. The participants added their
        profit when they settled and paid their fees ([P1] eq. 14); their
        reputation is updated just before (``_update_reputation``)."""
        self.clearing_price = record.clearing_price
        self.history.append(record)
        self.pending = None


__all__ = [
    "DSO_ID",
    "DsoOutcome",
    "LocalEnergyMarket",
    "OrderIntent",
    "ParticipantOutcome",
    "PendingStep",
    "ReputationScore",
    "StepInputs",
    "StepRecord",
]
