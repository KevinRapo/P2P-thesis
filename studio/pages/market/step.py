"""The Market page's Step tab: play the market one clearing stage at a time and
watch the network.

One market step is five parts, each one click: collect the orders, stage 1
(preferences), stage 2 (double auction), stage 3 (DSO), then settlement and the
power flow. After each part the page shows the order book that is left, the trades
so far, the participants and the network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from nicegui import run, ui

from core.grid.contract import NetworkRef
from core.market.clearing import DSO_ID
from core.market.lem import StepRecord
from studio.components.cards import busy, failed, section
from studio.components.charts import NetworkChart, SeriesChart
from studio.components.tables import data_table, trades_table
from studio.state import services
from studio.theme import LIMIT, MARKET

if TYPE_CHECKING:  # only to annotate what the page reads; the page never builds one
    from core.market.lem import LocalEnergyMarket

PARTS = (
    "Orders",
    "1 · Preferences",
    "2 · Double auction",
    "3 · DSO",
    "Settle + power flow",
)
NEXT = {
    0: "Stage 1: preferences",
    1: "Stage 2: double auction",
    2: "Stage 3: DSO",
    3: "Settle and run the power flow",
}
EXPLAIN = {
    -1: "Press “Collect orders”: every participant writes its order for the step.",
    0: "Orders are in. Stage 1 lets pairs that named each other trade first.",
    1: "Stage 1 done. Stage 2 is the double auction: bids from the highest price "
    "down, asks from the lowest up; every pair with bid ≥ ask trades.",
    2: "Stage 2 done. Stage 3: the DSO buys every open sell at the feed-in tariff "
    "and sells every open buy at the utility price.",
    3: "Every order is cleared. Next: batteries charge or discharge, and one power "
    "flow shows what the step does to the network.",
    4: "Step done: the network shows the voltages after the power flow.",
}
SELL, BUY, P2P, DSO = MARKET["sell"], MARKET["buy"], MARKET["p2p"], MARKET["dso"]


# --------------------------------------------------------------------------------------
# The tab
# --------------------------------------------------------------------------------------
def tab() -> None:
    """Controls on top, order book and network side by side, participants and the
    day below (built into the Market page's Step tab)."""
    s = services()

    # Every box below is empty here and filled by render() after each click

    # Top card, full width: where the step is and the buttons (_controls)
    with section("Market step", icon="skip_next"):
        controls = ui.column().classes("w-full gap-2")

    # Row: order book (left) | network with the trades (right)
    with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
        with section(
            "Order book",
            "Open orders as supply and demand curves; faint lines are the orders "
            "as submitted",
            "candlestick_chart",
            classes="grow basis-0",
        ):
            book_box = ui.column().classes("w-full")
        with section(
            "Network",
            "Rings: sellers (orange) and buyers (blue). Lines: trades between "
            "peers (green) and with the DSO (grey, to the external grid)",
            "hub",
            classes="grow basis-0",
        ):
            network_box = ui.column().classes("w-full")

    # Full-width cards: the trades table, then the participants table
    with section("Trades", icon="swap_horiz"):
        trades_box = ui.column().classes("w-full")

    with section("Participants", icon="groups"):
        people_box = ui.column().classes("w-full")

    # Bottom row: the day's volumes and prices (left) | voltages (right)
    with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
        with section(
            "The day so far",
            "Energy traded per step, and the price of the peer trades (none: no point)",
            "bar_chart",
            classes="grow basis-0",
        ):
            day_box = ui.column().classes("w-full")
        with section(
            "Network over the day",
            "Lowest and highest bus voltage after each step's power flow",
            "show_chart",
            classes="grow basis-0",
        ):
            volt_box = ui.column().classes("w-full")

    state: dict[str, Any] = {"topology": None, "code": None, "busy": False}

    async def topology() -> None:
        m = s.market.manager

        if m is None or state["code"] == m.scenario.grid.code:
            return

        busy(network_box, "Building topology …")
        source = NetworkRef("simbench", m.scenario.grid.code)

        try:
            state["topology"] = await run.io_bound(s.grid.topology, source)
            state["code"] = source.code
        except Exception as e:  # noqa: BLE001  show the error on the page
            failed(network_box, e)

    async def act(work, label: str) -> None:
        """Run ``work`` off the UI thread, then redraw."""
        if state["busy"]:
            return

        state["busy"] = True

        try:
            await run.io_bound(work)
        except Exception as e:  # noqa: BLE001  show the error on the page
            ui.notify(f"{label}: {e}", type="negative", multi_line=True)
        finally:
            state["busy"] = False

        await topology()
        render()

    def build() -> None:
        s.market.build(s.scenario.current())

    def render() -> None:
        m = s.market.manager
        _controls(controls, m, act, build)
        view = _view(m)

        for box in (book_box, network_box, trades_box, people_box, day_box, volt_box):
            box.clear()

        if m is None:
            return

        # Fill each card built in page(), in page order
        with book_box:
            if view["orders"]:
                OrderBookChart(view=view).show()
            else:
                ui.label("No orders yet.").classes("mls-card-caption")

        with network_box:
            if state["topology"] is not None:
                MarketNetworkChart(topology=state["topology"], m=m, view=view).show()

        with trades_box:
            trades_table(view["trades"])

        with people_box:
            _people_table(m, view)

        with day_box:
            if m.history:
                TradedChart(m=m).show()
            else:
                ui.label("No step played yet.").classes("mls-card-caption")

        with volt_box:
            if m.history:
                VoltageChart(m=m).show()

    async def start() -> None:
        await topology()
        render()

    ui.timer(0.05, start, once=True)


# --------------------------------------------------------------------------------------
# Controls: where the step is, what the next click does
# --------------------------------------------------------------------------------------
def _position(m: LocalEnergyMarket) -> int:
    """-1 before the orders, 0 orders in, 1-3 after each stage, 4 step done."""
    if m.pending is not None:
        return len(m.pending.stages)
    return 4 if m.history else -1


def _clock(m: LocalEnergyMarket, step: int) -> str:
    h = m.scenario.grid.step_hours
    start, end = step * h, (step + 1) * h
    fmt = lambda x: f"{int(x) % 24:02d}:{int(round(x % 1 * 60)):02d}"  # noqa: E731

    return f"{fmt(start)}–{fmt(end)}"


def _controls(box: ui.element, m: Optional[LocalEnergyMarket], act, build) -> None:
    market = services().market
    box.clear()

    with box:
        # No market yet: the scenario in one line and "Build the market"
        if m is None:
            scenario = services().scenario.current()
            n = len(scenario.participants)
            ui.label(
                f"{scenario.grid.code} · {scenario.grid.day} · {n} participants"
            ).classes("text-body2")

            if n == 0:
                ui.label(
                    "Place participants on the Grid & Participants page first."
                ).classes("text-warning text-caption")

            ui.button(
                "Build the market",
                icon="play_arrow",
                on_click=lambda: act(build, "Build"),
            ).props("unelevated no-caps").set_enabled(n > 0)

            return

        pos = _position(m)
        shown = m.pending.step if m.pending else max(0, m.current_step - 1)

        # Heading line: "Step i of n · time" | the scenario in short
        with ui.row().classes("w-full items-center gap-3"):
            ui.label(f"Step {shown + 1} of {m.n_steps} · {_clock(m, shown)}").classes(
                "text-h6"
            )
            ui.label(
                f"{m.scenario.grid.code} · {m.scenario.grid.day} · "
                f"{len(m.participants)} participants · {m.scenario.market.mechanism}"
            ).classes("mls-card-caption")

        # Progress chips through the step's parts, joined by arrows
        with ui.row().classes("w-full items-center gap-1"):
            for i, name in enumerate(PARTS):
                done = i <= pos if pos >= 0 else False
                ui.chip(
                    name,
                    icon="check_circle" if done else "radio_button_unchecked",
                ).props(
                    f"dense {'color=primary text-color=white' if done else 'outline'}"
                )
                if i < len(PARTS) - 1:
                    ui.icon("chevron_right", size="18px").classes("text-grey")

        ui.label(EXPLAIN[pos]).classes("text-body2")

        # Button row: next part | finish this step | run to the end | Reset
        with ui.row().classes("gap-2"):
            if m.done and m.pending is None:
                label = "Day complete"
            elif pos in (-1, 4):
                label = "Collect orders" if pos == -1 else "Next step: collect orders"
            else:
                label = NEXT[pos]

            ui.button(
                label,
                icon="arrow_forward",
                on_click=lambda: act(market.next_part, label),
            ).props("unelevated no-caps").set_enabled(
                not (m.done and m.pending is None)
            )
            ui.button(
                "Finish this step",
                icon="fast_forward",
                on_click=lambda: act(market.step, "Step"),
            ).props("outline no-caps").set_enabled(not m.done or m.pending is not None)
            ui.button(
                "Run to the end of the day",
                icon="last_page",
                on_click=lambda: act(market.run_to_end, "Run"),
            ).props("outline no-caps").set_enabled(not m.done)
            ui.button(
                "Reset", icon="restart_alt", on_click=lambda: act(build, "Reset")
            ).props("flat no-caps")

        ui.label(
            "Reset rebuilds the market from the current scenario and starts the day "
            "again; settings changed on the other pages apply from then on."
        ).classes("mls-card-caption")


# --------------------------------------------------------------------------------------
# What is shown: the step being played, or the last one
# --------------------------------------------------------------------------------------
def _view(m: Optional[LocalEnergyMarket]) -> dict[str, Any]:
    empty = {"orders": (), "open": (), "trades": [], "record": None, "inputs": None}

    if m is None:
        return empty

    if m.pending is not None:
        p = m.pending
        return {
            "orders": p.orders,
            "open": p.open_orders,
            "trades": p.trades,
            "record": None,
            "inputs": p.inputs,
        }

    if m.history:
        r = m.history[-1]
        return {
            "orders": r.orders,
            "open": (),
            "trades": r.trades,
            "record": r,
            "inputs": r.inputs,
        }

    return empty


# --------------------------------------------------------------------------------------
# Order book
# --------------------------------------------------------------------------------------
def _curve(orders, buy: bool) -> tuple[list[float], list[float]]:
    """Cumulative quantity and price, as a step curve: demand from the highest bid
    down, supply from the lowest ask up."""
    side = sorted(
        (o for o in orders if o.is_buy == buy),
        key=lambda o: -o.price if buy else o.price,
    )
    xs, ys, total = [0.0], [], 0.0

    for o in side:
        total += o.quantity
        xs.append(total)
        ys.append(o.price)

    if ys:
        ys.append(ys[-1])

    return xs, ys


class OrderBookChart(SeriesChart):
    """Supply and demand as step curves (each with its own x: cumulative kWh): the
    orders as submitted faint, those still open bold; the DSO's prices as levels.
    Options: ``view`` (``_view``)."""

    height = 360
    x_title = "cumulative kWh"
    y_title = "price per kWh"
    layout = {"hovermode": "closest"}

    def draw(self) -> None:
        view = self.o.view

        for orders, faint in ((view["orders"], True), (view["open"], False)):
            for buy, color, name in (
                (True, BUY, "Demand (bids)"),
                (False, SELL, "Supply (asks)"),
            ):
                xs, ys = _curve(orders, buy)

                if len(xs) >= 2:
                    self.line(
                        xs,
                        ys,
                        name + (" · submitted" if faint else " · open"),
                        color=color,
                        shape="hv",
                        width=1 if faint else 3,
                        dash="dot" if faint else "solid",
                        opacity=0.45 if faint else 1.0,
                    )

        if view["inputs"] is not None:
            self.level(view["inputs"].feed_in_tariff, "Feed-in tariff", color=DSO)
            self.level(view["inputs"].utility_price, "Utility price", color=DSO)


# --------------------------------------------------------------------------------------
# Network: participants, trades, voltages
# --------------------------------------------------------------------------------------
class MarketNetworkChart(NetworkChart):
    """The network after the step's power flow (voltages, buses outside their
    limits), the participants ringed, the trades as links and the orders as rings.
    Options: ``topology``, ``m`` (the market), ``view`` (``_view``)."""

    height = 480

    def __init__(self, **options) -> None:
        record: Optional[StepRecord] = options["view"]["record"]
        grid = record.grid if record else None
        super().__init__(
            voltages=dict(grid.bus_voltage_pu) if grid and grid.converged else None,
            violating=(
                {v.element_id for v in grid.violations if v.element_type == "bus"}
                if grid
                else None
            ),
            highlight={p.bus for p in options["m"].participants.values()},
            **options,
        )

    def draw(self) -> None:
        m, view = self.o.m, self.o.view
        ext = self.o.topology.external_grid_bus
        bus_of = {pid: p.bus for pid, p in m.participants.items()}

        def bus(agent: str) -> str:
            """An agent's bus; the DSO's is the external grid."""
            return ext if agent == DSO_ID else bus_of.get(agent, ext)

        for stages, color, name, dash in (
            ((1, 2), P2P, "Peer trade", "solid"),
            ((3,), DSO, "DSO trade", "dash"),
        ):
            links = [
                (
                    bus(t.seller_id),
                    bus(t.buyer_id),
                    t.quantity,
                    f"{t.seller_id} → {t.buyer_id}: {t.quantity:.2f} kWh at "
                    f"{t.price:.3f}",
                )
                for t in view["trades"]
                if t.stage in stages
            ]
            self.links(links, color, name, dash)

        for buy, color, name in ((False, SELL, "Seller"), (True, BUY, "Buyer")):
            verb = "buys" if buy else "sells"
            rings = [
                (
                    o.location,
                    f"{o.agent_id} {verb} {o.quantity:.2f} kWh at {o.price:.3f}",
                )
                for o in view["orders"]
                if o.is_buy == buy
            ]
            self.rings(rings, color, name)


# --------------------------------------------------------------------------------------
# Tables: trades and participants
# --------------------------------------------------------------------------------------
def _people_table(m: LocalEnergyMarket, view: dict) -> None:
    inputs = view["inputs"]

    if inputs is None:
        ui.label(
            "Collect the orders of the first step to see the participants."
        ).classes("mls-card-caption")
        return

    orders = {o.agent_id: o for o in view["orders"]}
    record: Optional[StepRecord] = view["record"]
    trades = view["trades"]
    rows = []

    for pid, p in m.participants.items():
        o = orders.get(pid)
        out = record.participants.get(pid) if record else None
        soc = out.soc_kwh if out else (p.battery.energy_kwh if p.battery else None)
        rows.append(
            {
                "id": pid,
                "bus": p.bus,
                "gen": round(inputs.generation_kwh[pid], 2),
                "dem": round(inputs.demand_kwh[pid], 2),
                "order": (
                    f"{'buy' if o.is_buy else 'sell'} {o.quantity:.2f} @ {o.price:.3f}"
                    if o
                    else "—"
                ),
                "bought": round(
                    sum(t.quantity for t in trades if t.buyer_id == pid), 2
                ),
                "sold": round(sum(t.quantity for t in trades if t.seller_id == pid), 2),
                "battery": (
                    "—" if soc is None else f"{soc:.1f} / {p.battery.capacity_kwh:g}"
                ),
                "external": round(out.external_kwh, 2) if out else "",
                "profit": round(out.profit, 3) if out else "",
                "total": round(p.profit, 3),
            }
        )

    data_table(
        rows,
        [
            ("id", "Participant"),
            ("bus", "Bus"),
            ("gen", "Generation kWh"),
            ("dem", "Demand kWh"),
            ("order", "Order"),
            ("bought", "Bought"),
            ("sold", "Sold"),
            ("battery", "Battery kWh"),
            ("external", "Untraded kWh"),
            ("profit", "Step profit"),
            ("total", "Profit so far"),
        ],
        pagination=15,
    )
    ui.label(
        "Battery shows the energy stored after the step. Untraded is what no trade "
        "covered (+ exported, − imported): 0 when orders match what happened. "
        "Profit = sales − purchases (paper eq. 14)."
    ).classes("mls-card-caption")


# --------------------------------------------------------------------------------------
# The day: volumes, prices, voltages
# --------------------------------------------------------------------------------------
class TradedChart(SeriesChart):
    """Energy traded per step (stacked bars), the clearing price on the right.
    Options: ``m`` (the market)."""

    y_title = "kWh"
    right_title = "price per kWh"
    stacked = True

    def draw(self) -> None:
        h = self.o.m.history
        x = [_clock(self.o.m, r.step)[:5] for r in h]
        self.bars(x, [r.p2p_kwh for r in h], "Peer to peer", color=P2P)
        self.bars(x, [r.dso_kwh for r in h], "With the DSO", color=DSO)
        price = [r.clearing_price if r.p2p_kwh > 0 else None for r in h]
        self.line(x, price, "Clearing price", color=SELL, markers=True, right=True)


class VoltageChart(SeriesChart):
    """The lowest and highest bus voltage after each step, with the limits.
    Options: ``m`` (the market)."""

    y_title = "V (pu)"

    def draw(self) -> None:
        m = self.o.m
        x = [_clock(m, r.step)[:5] for r in m.history]
        highest = [r.grid.max_voltage_pu for r in m.history]
        lowest = [r.grid.min_voltage_pu for r in m.history]
        self.line(x, highest, "Highest V", color=SELL, markers=True)
        self.line(x, lowest, "Lowest V", color=BUY, markers=True)

        for v in (m.scenario.grid.v_min_pu, m.scenario.grid.v_max_pu):
            self.level(v, color=LIMIT)
