"""Market probes: tiny scripted market cases whose outcome is known by hand.

Like the RL probes (``core/rl/envs/probes.py``), each probe isolates one part of
the market step and states what it must give, so the first probe that fails names
the broken part. Not a check of every formula (``tests/market/`` does that), but a
case played out where the mechanism is visible ([docs/plan/validation.md]).

Every probe plays the same small market: four participants on the SimBench network
``1-LV-rural1--0-sw`` on 15 June 2016 (two with PV, two consumers), with their
SimBench profiles. The day runs from midnight with no orders up to the probe's
window, five hourly steps around midday where the PV has a surplus and the
consumers a deficit; there each participant submits a scripted order
(``OrderIntent``, the RL agents' path, no bidding rule), its quantity a share of its
eq. 15 bound. The expected values are computed from the profiles of those steps
(e.g. "C1 buys min(PV1's surplus, C1's deficit)"), never typed in.

    M1  stage 1, mutual preference   PV1 and C1 name each other, bid >= ask
    M2  stage 1 needs both           names that are not returned: no stage 1
    M3  double auction               2 sellers, 2 buyers: price order, partial fills
    M4  the DSO clears the rest      bid < ask: everything to the DSO

Each probe is played on both grid methods (``play(probe, method)``): the market's
outcome must be the same on both (``same_market``), only the fees differ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from core.config.scenario import (
    DsoSetup,
    GridSetup,
    MarketSetup,
    ParticipantSetup,
    Scenario,
)
from core.market.dso import DSO_ID
from core.market.lem import LocalEnergyMarket, OrderIntent, StepInputs, StepRecord

METHODS = ("powerflow", "graph")
WINDOW = range(8, 13)  # 08:00-13:00: PV surplus, consumer deficit in every step
TOLERANCE = 1e-9


# --------------------------------------------------------------------------------------
# The probe market: four participants on a SimBench LV network
# --------------------------------------------------------------------------------------
def scenario(method: str = "powerflow") -> Scenario:
    """The market every probe plays: PV1 and PV2 own a load and a PV generator,
    C1 and C2 a load only (with the same profile); no batteries. The DSO's tariffs
    and the market rules are the defaults (FiT 0.08, utility 0.30, the average
    price)."""
    lv = "LV1.101"

    return Scenario(
        name="market_probes",
        grid=GridSetup(code="1-LV-rural1--0-sw", day="2016-06-15", method=method),
        participants=[
            ParticipantSetup("PV1", f"{lv} Bus 7", [f"{lv} Load 9", f"{lv} SGen 1"]),
            ParticipantSetup("PV2", f"{lv} Bus 8", [f"{lv} Load 2", f"{lv} SGen 4"]),
            ParticipantSetup("C1", f"{lv} Bus 1", [f"{lv} Load 8"]),
            ParticipantSetup("C2", f"{lv} Bus 5", [f"{lv} Load 13"]),
        ],
        market=MarketSetup(mechanism="average"),
        dso=DsoSetup(),
    )


# --------------------------------------------------------------------------------------
# A probe: its orders and its checks
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Bounds:
    """One participant's position before a step: what its orders are scaled to.

    Attributes:
        sell_kwh: Eq. 15a, the most it may sell.
        buy_kwh: Eq. 15b, the most it may buy.
    """

    sell_kwh: float
    buy_kwh: float


@dataclass(frozen=True)
class Check:
    """One expected value of a probe against the market's.

    Attributes:
        step: The step it is about.
        name: What is checked.
        expected: The value worked out from the profiles.
        got: The market's value.
        tolerance: Largest difference that passes.
    """

    step: int
    name: str
    expected: float
    got: float
    tolerance: float = TOLERANCE

    @property
    def ok(self) -> bool:
        return abs(self.expected - self.got) <= self.tolerance


@dataclass(frozen=True)
class MarketProbe:
    """One market probe.

    Attributes:
        key: ``M1``, ``M2``, ...
        title: Short name.
        shows: The part of the market step it isolates.
        setup: The orders, in words.
        expect: What a correct market gives, in words.
        orders: The scripted orders of a step, from every participant's bounds.
        checks: The checks of a played step, from its record (profiles, tariffs and
            trades) and the previous step's clearing price.
    """

    key: str
    title: str
    shows: str
    setup: str
    expect: str
    orders: Callable[[Mapping[str, Bounds]], dict[str, OrderIntent]]
    checks: Callable[[StepRecord, float], list[Check]]


@dataclass(frozen=True)
class ProbeRun:
    """A probe played on one grid method.

    Attributes:
        probe: The probe.
        method: ``grid.method``: ``"powerflow"`` or ``"graph"``.
        records: The steps of the window.
        checks: Every check of every step.
    """

    probe: MarketProbe
    method: str
    records: tuple[StepRecord, ...]
    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


# --------------------------------------------------------------------------------------
# What the checks read: positions from the profiles, trades from the record
# --------------------------------------------------------------------------------------
def surplus(inputs: StepInputs, pid: str) -> float:
    """max(0, G − D): what a participant without battery can sell (eq. 15a)."""
    return max(0.0, inputs.generation_kwh[pid] - inputs.demand_kwh[pid])


def deficit(inputs: StepInputs, pid: str) -> float:
    """max(0, D − G): what a participant without battery can buy (eq. 15b)."""
    return max(0.0, inputs.demand_kwh[pid] - inputs.generation_kwh[pid])


def traded(
    record: StepRecord,
    stage: Optional[int] = None,
    seller: Optional[str] = None,
    buyer: Optional[str] = None,
) -> float:
    """kWh of the step's trades in ``stage`` (any without) from ``seller`` to
    ``buyer`` (anyone without)."""
    return sum(
        t.quantity
        for t in record.trades
        if (stage is None or t.stage == stage)
        and (seller is None or t.seller_id == seller)
        and (buyer is None or t.buyer_id == buyer)
    )


def price(record: StepRecord, seller: str, buyer: str) -> float:
    """The volume-weighted price of the step's trades from ``seller`` to ``buyer``;
    0 without any."""
    pair = [t for t in record.trades if t.seller_id == seller and t.buyer_id == buyer]
    volume = sum(t.quantity for t in pair)

    return sum(t.price * t.quantity for t in pair) / volume if volume else 0.0


def _sell(pid: str, kwh: float, ask: float, partner: Optional[str] = None):
    return OrderIntent(pid, False, ask, kwh, partner)


def _buy(pid: str, kwh: float, bid: float, partner: Optional[str] = None):
    return OrderIntent(pid, True, bid, kwh, partner)


def _dso_checks(record: StepRecord, sells: dict, buys: dict) -> list[Check]:
    """Stage 3: the DSO buys ``sells`` (kWh per participant) at the feed-in tariff
    and sells ``buys`` at the utility price."""
    t, i = record.step, record.inputs
    out = []

    for pid, kwh in sells.items():
        out.append(Check(t, f"DSO buys from {pid}, kWh", kwh, traded(record, 3, pid)))
        if kwh > TOLERANCE:
            out.append(
                Check(t, "... at the FiT", i.feed_in_tariff, price(record, pid, DSO_ID))
            )

    for pid, kwh in buys.items():
        got = traded(record, 3, buyer=pid)
        out.append(Check(t, f"DSO sells to {pid}, kWh", kwh, got))
        if kwh > TOLERANCE:
            out.append(
                Check(
                    t,
                    "... at the utility price",
                    i.utility_price,
                    price(record, DSO_ID, pid),
                )
            )

    return out


# --------------------------------------------------------------------------------------
# M1: stage 1, mutual preference
# --------------------------------------------------------------------------------------
M1_ASK, M1_BID = 0.12, 0.24


def _m1_orders(b: Mapping[str, Bounds]) -> dict[str, OrderIntent]:
    return {
        "PV1": _sell("PV1", b["PV1"].sell_kwh, M1_ASK, "C1"),
        "C1": _buy("C1", b["C1"].buy_kwh, M1_BID, "PV1"),
    }


def _m1_checks(record: StepRecord, _: float) -> list[Check]:
    t, i = record.step, record.inputs
    s, d = surplus(i, "PV1"), deficit(i, "C1")
    q = min(s, d)
    mid = (M1_ASK + M1_BID) / 2

    return [
        Check(
            t,
            "stage 1: PV1 → C1, kWh = min(surplus, deficit)",
            q,
            traded(record, 1, "PV1", "C1"),
        ),
        Check(t, "stage 1 price = (bid + ask) / 2", mid, price(record, "PV1", "C1")),
        Check(t, "stage 2 trades nothing, kWh", 0.0, traded(record, 2)),
        *_dso_checks(record, {"PV1": s - q}, {"C1": d - q}),
        Check(t, "clearing price = the stage 1 price", mid, record.clearing_price),
    ]


M1 = MarketProbe(
    key="M1",
    title="Stage 1: mutual preference",
    shows="Stage 1 (preferences, [P1] §3.3.2): two participants that name each "
    "other trade first, at the mechanism's price, before the double auction.",
    setup=f"PV1 sells its whole surplus at {M1_ASK} naming C1; C1 buys its whole "
    f"deficit at {M1_BID} naming PV1. PV2 and C2 do not order.",
    expect="One stage-1 trade PV1 → C1 of min(PV1's surplus, C1's deficit) at the "
    f"midpoint {(M1_ASK + M1_BID) / 2:.2f}; nothing in stage 2; the DSO buys PV1's "
    "rest at the feed-in tariff (and sells C1's rest at the utility price).",
    orders=_m1_orders,
    checks=_m1_checks,
)


# --------------------------------------------------------------------------------------
# M2: stage 1 needs both names
# --------------------------------------------------------------------------------------
M2_ASK_PV1, M2_ASK_PV2, M2_BID = 0.12, 0.16, 0.24


def _m2_orders(b: Mapping[str, Bounds]) -> dict[str, OrderIntent]:
    return {
        "PV1": _sell("PV1", b["PV1"].sell_kwh, M2_ASK_PV1, "C1"),
        "PV2": _sell("PV2", b["PV2"].sell_kwh, M2_ASK_PV2),
        "C1": _buy("C1", b["C1"].buy_kwh, M2_BID, "PV2"),
    }


def _m2_checks(record: StepRecord, _: float) -> list[Check]:
    t, i = record.step, record.inputs
    s1, s2, d = surplus(i, "PV1"), surplus(i, "PV2"), deficit(i, "C1")
    q = min(s1, d)  # the lowest ask first

    return [
        Check(t, "stage 1 trades nothing, kWh", 0.0, traded(record, 1)),
        Check(
            t, "stage 2: PV1 (lowest ask) → C1, kWh", q, traded(record, 2, "PV1", "C1")
        ),
        Check(
            t,
            "stage 2 price = (bid + ask) / 2",
            (M2_ASK_PV1 + M2_BID) / 2,
            price(record, "PV1", "C1"),
        ),
        Check(
            t, "stage 2: PV2 → C1, kWh", min(s2, d - q), traded(record, 2, "PV2", "C1")
        ),
        *_dso_checks(
            record,
            {"PV1": s1 - q, "PV2": s2 - min(s2, d - q)},
            {"C1": d - q - min(s2, d - q)},
        ),
    ]


M2 = MarketProbe(
    key="M2",
    title="Stage 1 needs both names",
    shows="Stage 1 matches only mutual names: a name that is not returned leaves the "
    "order to the double auction, which goes by price alone.",
    setup=f"PV1 sells its surplus at {M2_ASK_PV1} naming C1; PV2 sells its surplus "
    f"at {M2_ASK_PV2} naming nobody; C1 buys its deficit at {M2_BID} naming PV2. "
    "Nobody is named back.",
    expect="Nothing in stage 1. In stage 2 C1 buys from the lowest ask, PV1, "
    "min(PV1's surplus, C1's deficit), not from PV2 that it named; only what PV1 "
    "cannot cover comes from PV2. The DSO buys the sellers' rest.",
    orders=_m2_orders,
    checks=_m2_checks,
)


# --------------------------------------------------------------------------------------
# M3: double auction, price order and partial fills
# --------------------------------------------------------------------------------------
M3_ASKS = {"PV1": 0.10, "PV2": 0.14}
M3_BIDS = {"C1": 0.26, "C2": 0.22}


def _m3_orders(b: Mapping[str, Bounds]) -> dict[str, OrderIntent]:
    sells = {pid: _sell(pid, b[pid].sell_kwh, ask) for pid, ask in M3_ASKS.items()}
    buys = {pid: _buy(pid, b[pid].buy_kwh, bid) for pid, bid in M3_BIDS.items()}

    return sells | buys


def _m3_checks(record: StepRecord, _: float) -> list[Check]:
    """The auction's walk worked out for this case: C1 (highest bid) takes from PV1
    (lowest ask) first, then C2 takes PV1's rest, then from PV2."""
    t, i = record.step, record.inputs
    s1, s2 = surplus(i, "PV1"), surplus(i, "PV2")
    d1, d2 = deficit(i, "C1"), deficit(i, "C2")
    a = min(d1, s1)  # C1 <- PV1
    b = min(d2, s1 - a)  # C2 <- PV1's rest
    c = min(d2 - b, s2)  # C2 <- PV2
    expected = {
        ("PV1", "C1"): (a, (M3_ASKS["PV1"] + M3_BIDS["C1"]) / 2),
        ("PV1", "C2"): (b, (M3_ASKS["PV1"] + M3_BIDS["C2"]) / 2),
        ("PV2", "C2"): (c, (M3_ASKS["PV2"] + M3_BIDS["C2"]) / 2),
    }
    volume = a + b + c
    weighted = sum(q * p for q, p in expected.values()) / volume
    out = [
        Check(t, "case: PV1 alone covers C1 (surplus − deficit)", 1.0, float(s1 >= d1)),
        Check(t, "stage 1 trades nothing (no names), kWh", 0.0, traded(record, 1)),
        Check(
            t,
            "stage 2: PV2 → C1 (C1 is filled first), kWh",
            0.0,
            traded(record, 2, "PV2", "C1"),
        ),
    ]

    for (seller, buyer), (q, p) in expected.items():
        out.append(
            Check(
                t,
                f"stage 2: {seller} → {buyer}, kWh",
                q,
                traded(record, 2, seller, buyer),
            )
        )
        if q > TOLERANCE:
            out.append(
                Check(t, "... at (bid + ask) / 2", p, price(record, seller, buyer))
            )

    return out + [
        *_dso_checks(
            record, {"PV1": s1 - a - b, "PV2": s2 - c}, {"C1": d1 - a, "C2": d2 - b - c}
        ),
        Check(
            t,
            "clearing price = volume-weighted peer price",
            weighted,
            record.clearing_price,
        ),
    ]


M3 = MarketProbe(
    key="M3",
    title="Double auction: price order, partial fills",
    shows="Stage 2 (the double auction, [P1] §3.3.2): bids from the highest down, "
    "asks from the lowest up; a pair trades while bid >= ask, the larger order "
    "goes on, part filled, to the next. The clearing price is the volume-weighted "
    "price of the peer trades.",
    setup="PV1 sells its surplus at 0.10, PV2 at 0.14; C1 buys its deficit at 0.26, "
    "C2 at 0.22; nobody names a partner.",
    expect="C1 is filled first, from PV1; C2 takes PV1's rest, then PV2's (each pair "
    "at its own midpoint); what is left goes to the DSO. The case needs PV1's "
    "surplus to cover C1's deficit (it does in every step of the window).",
    orders=_m3_orders,
    checks=_m3_checks,
)


# --------------------------------------------------------------------------------------
# M4: the DSO clears the rest
# --------------------------------------------------------------------------------------
M4_ASK, M4_BID = 0.25, 0.15


def _m4_orders(b: Mapping[str, Bounds]) -> dict[str, OrderIntent]:
    return {
        "PV1": _sell("PV1", b["PV1"].sell_kwh, M4_ASK),
        "C1": _buy("C1", b["C1"].buy_kwh, M4_BID),
    }


def _m4_checks(record: StepRecord, previous_price: float) -> list[Check]:
    t, i = record.step, record.inputs
    s, d = surplus(i, "PV1"), deficit(i, "C1")
    revenue = i.utility_price * d - i.feed_in_tariff * s

    return [
        Check(t, "peer trades (stages 1, 2), kWh", 0.0, record.p2p_kwh),
        *_dso_checks(record, {"PV1": s}, {"C1": d}),
        Check(
            t, "DSO balance (eq. 7) = sold − bought, kWh", d - s, record.dso.balance_kwh
        ),
        Check(t, "DSO energy revenue", revenue, record.dso.energy_revenue),
        Check(
            t,
            "PV1's step profit before fees = FiT × surplus",
            i.feed_in_tariff * s,
            record.participants["PV1"].profit + record.participants["PV1"].fees,
        ),
        Check(
            t,
            "clearing price kept from the step before",
            previous_price,
            record.clearing_price,
        ),
    ]


M4 = MarketProbe(
    key="M4",
    title="The DSO clears the rest",
    shows="Stage 3 ([P1] §3.3.2): every order still open is cleared by the DSO, a "
    "sell at the feed-in tariff, a buy at the utility price; with no peer trade "
    "the clearing price stays where it was.",
    setup=f"PV1 sells its surplus at {M4_ASK}; C1 buys its deficit at {M4_BID} (bid "
    "below ask); nobody names a partner.",
    expect="No peer trade. The DSO buys PV1's whole surplus at 0.08 and sells C1's "
    "whole deficit at 0.30; its balance is C1's deficit minus PV1's surplus. The "
    "clearing price stays at the tariffs' midpoint, 0.19 (no peer trade all day).",
    orders=_m4_orders,
    checks=_m4_checks,
)

PROBES: tuple[MarketProbe, ...] = (M1, M2, M3, M4)


# --------------------------------------------------------------------------------------
# Playing a probe
# --------------------------------------------------------------------------------------
def bounds(market: LocalEnergyMarket) -> dict[str, Bounds]:
    """Every participant's eq. 15 bounds for the market's next step."""
    step = market.current_step

    return {
        pid: Bounds(p.max_sell_kwh(step), p.max_buy_kwh(step))
        for pid, p in market.participants.items()
    }


def play(probe: MarketProbe, method: str = "powerflow") -> ProbeRun:
    """Play ``probe`` on ``method``: the day up to the window with no orders, then
    the window with the probe's orders, each step checked."""
    market = LocalEnergyMarket(scenario(method))
    market.reset()

    while market.current_step < WINDOW.start:
        market.step({})

    records, checks = [], []

    for _ in WINDOW:
        previous = market.clearing_price
        record = market.step(probe.orders(bounds(market)))
        records.append(record)
        checks += probe.checks(record, previous)

    return ProbeRun(probe, method, tuple(records), tuple(checks))


def play_all(methods: tuple[str, ...] = METHODS) -> list[ProbeRun]:
    """Every probe on every method."""
    return [play(probe, method) for probe in PROBES for method in methods]


def same_market(a: ProbeRun, b: ProbeRun) -> list[Check]:
    """The market's outcome of one probe on two grid methods: the same trades
    (stage, seller, buyer, kWh, price) in every step. Only the fees may differ: the
    graph model's line loading is not the power flow's."""
    out = []

    for ra, rb in zip(a.records, b.records):
        trades_a = sorted(_trade_key(t) for t in ra.trades)
        trades_b = sorted(_trade_key(t) for t in rb.trades)
        out.append(
            Check(
                ra.step,
                f"the same trades on {a.method} and {b.method}",
                1.0,
                float(trades_a == trades_b),
            )
        )

    return out


def _trade_key(t) -> tuple:
    return t.stage, t.seller_id, t.buyer_id, round(t.quantity, 9), round(t.price, 9)


__all__ = [
    "Bounds",
    "Check",
    "MarketProbe",
    "METHODS",
    "PROBES",
    "ProbeRun",
    "WINDOW",
    "bounds",
    "play",
    "play_all",
    "same_market",
    "scenario",
]
