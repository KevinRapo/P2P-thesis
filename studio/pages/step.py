"""Step: play the market one clearing stage at a time and watch the network.

One market step is five parts, each one click: collect the orders, stage 1
(preferences), stage 2 (double auction), stage 3 (DSO), then settlement and the
power flow. After each part the page shows the order book that is left, the trades
so far, the participants and the network.
"""

from __future__ import annotations

from typing import Any, Optional

import plotly.graph_objects as go
from nicegui import run, ui

from market.clearing import DSO_ID
from market.manager import MarketManager, StepRecord
from market.order import Trade
from services.models import NetworkSource
from studio.components.cards import section
from studio.components.charts import styled, topology_figure
from studio.components.network import busy, failed
from studio.components.tables import data_table
from studio.layout import shell
from studio.state import services

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
SELL, BUY, P2P, DSO = "#D97706", "#2563EB", "#15803D", "#64748B"


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """Controls on top, order book and network side by side, participants and the
    day below."""
    s = services()
    with shell(
        "step",
        "Step",
        "Play the market on its network one clearing stage at a time. Reset builds "
        "the market from the Grid & Participants and Market & DSO pages.",
    ):
        with section("Market step", icon="skip_next"):
            controls = ui.column().classes("w-full gap-2")
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
        with section("Trades", icon="swap_horiz"):
            trades_box = ui.column().classes("w-full")
        with section("Participants", icon="groups"):
            people_box = ui.column().classes("w-full")
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
        source = NetworkSource(type="simbench", code=m.scenario.grid.code)
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

    def next_part() -> None:
        m = s.market.manager
        if m.pending is None:
            m.start_step()
        else:
            m.advance()

    def render() -> None:
        m = s.market.manager
        _controls(controls, m, act, build, next_part)
        view = _view(m)
        for box in (book_box, network_box, trades_box, people_box, day_box, volt_box):
            box.clear()
        if m is None:
            return
        with book_box:
            if view["orders"]:
                ui.plotly(_order_book(view)).classes("w-full")
            else:
                ui.label("No orders yet.").classes("mls-card-caption")
        with network_box:
            if state["topology"] is not None:
                ui.plotly(_network(state["topology"], m, view)).classes("w-full")
        with trades_box:
            _trades_table(view["trades"])
        with people_box:
            _people_table(m, view)
        with day_box:
            if m.history:
                ui.plotly(_day_figure(m)).classes("w-full")
            else:
                ui.label("No step played yet.").classes("mls-card-caption")
        with volt_box:
            if m.history:
                ui.plotly(_voltage_figure(m)).classes("w-full")

    async def start() -> None:
        await topology()
        render()

    ui.timer(0.05, start, once=True)


# --------------------------------------------------------------------------------------
# Controls: where the step is, what the next click does
# --------------------------------------------------------------------------------------
def _position(m: MarketManager) -> int:
    """-1 before the orders, 0 orders in, 1-3 after each stage, 4 step done."""
    if m.pending is not None:
        return len(m.pending.stages)
    return 4 if m.history else -1


def _clock(m: MarketManager, step: int) -> str:
    h = m.scenario.grid.step_hours
    start, end = step * h, (step + 1) * h
    fmt = lambda x: f"{int(x) % 24:02d}:{int(round(x % 1 * 60)):02d}"  # noqa: E731
    return f"{fmt(start)}–{fmt(end)}"


def _controls(
    box: ui.element, m: Optional[MarketManager], act, build, next_part
) -> None:
    box.clear()
    with box:
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
        with ui.row().classes("w-full items-center gap-3"):
            ui.label(f"Step {shown + 1} of {m.n_steps} · {_clock(m, shown)}").classes(
                "text-h6"
            )
            ui.label(
                f"{m.scenario.grid.code} · {m.scenario.grid.day} · "
                f"{len(m.participants)} participants · {m.scenario.market.mechanism}"
            ).classes("mls-card-caption")
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
        with ui.row().classes("gap-2"):
            if m.done and m.pending is None:
                label = "Day complete"
            elif pos in (-1, 4):
                label = "Collect orders" if pos == -1 else "Next step: collect orders"
            else:
                label = NEXT[pos]
            ui.button(
                label, icon="arrow_forward", on_click=lambda: act(next_part, label)
            ).props("unelevated no-caps").set_enabled(
                not (m.done and m.pending is None)
            )
            ui.button(
                "Finish this step",
                icon="fast_forward",
                on_click=lambda: act(m.step, "Step"),
            ).props("outline no-caps").set_enabled(not m.done or m.pending is not None)
            ui.button(
                "Run to the end of the day",
                icon="last_page",
                on_click=lambda: act(m.run_to_end, "Run"),
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
def _view(m: Optional[MarketManager]) -> dict[str, Any]:
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


def _order_book(view: dict) -> go.Figure:
    fig = go.Figure()
    inputs = view["inputs"]
    for orders, faint in ((view["orders"], True), (view["open"], False)):
        for buy, color, name in (
            (True, BUY, "Demand (bids)"),
            (False, SELL, "Supply (asks)"),
        ):
            xs, ys = _curve(orders, buy)
            if len(xs) < 2:
                continue
            fig.add_scatter(
                x=xs,
                y=ys,
                mode="lines",
                line_shape="hv",
                name=name + (" · submitted" if faint else " · open"),
                line=dict(
                    color=color,
                    width=1 if faint else 3,
                    dash="dot" if faint else "solid",
                ),
                opacity=0.45 if faint else 1.0,
            )
    if inputs is not None:
        for price, name in (
            (inputs.feed_in_tariff, "Feed-in tariff"),
            (inputs.utility_price, "Utility price"),
        ):
            fig.add_hline(
                y=price,
                line=dict(color=DSO, dash="dash", width=1),
                annotation_text=name,
                annotation_position="top left",
            )
    fig = styled(fig, 360, "price per kWh", "cumulative kWh")
    fig.update_layout(hovermode="closest")
    return fig


# --------------------------------------------------------------------------------------
# Network: participants, trades, voltages
# --------------------------------------------------------------------------------------
def _network(topology, m: MarketManager, view: dict) -> go.Figure:
    record: Optional[StepRecord] = view["record"]
    voltages = (
        dict(record.grid.bus_voltage_pu) if record and record.grid.converged else None
    )
    violating = (
        {v.element_id for v in record.grid.violations if v.element_type == "bus"}
        if record
        else None
    )
    buses = {p.bus for p in m.participants.values()}
    fig = topology_figure(
        topology, voltages=voltages, highlight=buses, height=480, violating=violating
    )
    pos = {b["id"]: (b["x"], b["y"]) for b in topology.buses}
    bus_of = {pid: p.bus for pid, p in m.participants.items()}
    ext = topology.external_grid_bus

    def segment(trades: list[Trade], color: str, dash: str, name: str) -> None:
        if not trades:
            return
        biggest = max(t.quantity for t in trades) or 1.0
        for n, t in enumerate(trades):
            a = bus_of.get(t.seller_id, ext) if t.seller_id != DSO_ID else ext
            b = bus_of.get(t.buyer_id, ext) if t.buyer_id != DSO_ID else ext
            if a not in pos or b not in pos:
                continue
            (x0, y0), (x1, y1) = pos[a], pos[b]
            fig.add_scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line=dict(color=color, width=1.5 + 5 * t.quantity / biggest, dash=dash),
                opacity=0.8,
                name=name,
                legendgroup=name,
                showlegend=n == 0,
                hoverinfo="text",
                text=f"{t.seller_id} → {t.buyer_id}: {t.quantity:.2f} kWh at {t.price:.3f}",
            )

    trades = view["trades"]
    segment([t for t in trades if t.stage < 3], P2P, "solid", "Peer trade")
    segment([t for t in trades if t.stage == 3], DSO, "dash", "DSO trade")
    for buy, color, name in ((False, SELL, "Seller"), (True, BUY, "Buyer")):
        group = [o for o in view["orders"] if o.is_buy == buy and o.location in pos]
        if group:
            fig.add_scatter(
                x=[pos[o.location][0] for o in group],
                y=[pos[o.location][1] for o in group],
                mode="markers",
                name=name,
                hoverinfo="text",
                text=[
                    f"{o.agent_id} {'buys' if buy else 'sells'} {o.quantity:.2f} kWh "
                    f"at {o.price:.3f}"
                    for o in group
                ],
                marker=dict(
                    size=20, symbol="circle-open", color=color, line=dict(width=3)
                ),
            )
    return fig


# --------------------------------------------------------------------------------------
# Tables: trades and participants
# --------------------------------------------------------------------------------------
STAGE_LABELS = {1: "1 · Preferences", 2: "2 · Double auction", 3: "3 · DSO"}


def _trades_table(trades: list[Trade]) -> None:
    if not trades:
        ui.label("No trades yet in this step.").classes("mls-card-caption")
        return
    rows = [
        {
            "n": n,
            "stage": STAGE_LABELS.get(t.stage, str(t.stage)),
            "seller": t.seller_id,
            "buyer": t.buyer_id,
            "kwh": round(t.quantity, 3),
            "price": round(t.price, 4),
            "value": round(t.quantity * t.price, 4),
        }
        for n, t in enumerate(trades, start=1)
    ]
    data_table(
        rows,
        [
            ("stage", "Stage"),
            ("seller", "Seller"),
            ("buyer", "Buyer"),
            ("kwh", "kWh"),
            ("price", "Price"),
            ("value", "Value"),
        ],
        row_key="n",
        pagination=10,
    )
    p2p = sum(t.quantity for t in trades if t.stage < 3)
    dso = sum(t.quantity for t in trades if t.stage == 3)
    ui.label(f"Peer to peer {p2p:.2f} kWh · with the DSO {dso:.2f} kWh").classes(
        "mls-card-caption"
    )


def _people_table(m: MarketManager, view: dict) -> None:
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
        soc = out.soc_kwh if out else m.energy_kwh.get(pid)
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
                "total": round(m.profit.get(pid, 0.0), 3),
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
def _day_figure(m: MarketManager) -> go.Figure:
    x = [_clock(m, r.step)[:5] for r in m.history]
    fig = go.Figure()
    fig.add_bar(
        x=x, y=[r.p2p_kwh for r in m.history], name="Peer to peer", marker_color=P2P
    )
    fig.add_bar(
        x=x, y=[r.dso_kwh for r in m.history], name="With the DSO", marker_color=DSO
    )
    fig.add_scatter(
        x=x,
        y=[r.clearing_price if r.p2p_kwh > 0 else None for r in m.history],
        name="Clearing price",
        yaxis="y2",
        mode="lines+markers",
        line=dict(color=SELL),
    )
    fig = styled(fig, 300, "kWh")
    fig.update_layout(
        barmode="stack",
        yaxis2=dict(
            title="price per kWh", overlaying="y", side="right", showgrid=False
        ),
    )
    return fig


def _voltage_figure(m: MarketManager) -> go.Figure:
    x = [_clock(m, r.step)[:5] for r in m.history]
    g = m.scenario.grid
    fig = go.Figure()
    fig.add_scatter(
        x=x,
        y=[r.grid.max_voltage_pu for r in m.history],
        name="Highest V",
        mode="lines+markers",
        line=dict(color=SELL),
    )
    fig.add_scatter(
        x=x,
        y=[r.grid.min_voltage_pu for r in m.history],
        name="Lowest V",
        mode="lines+markers",
        line=dict(color=BUY),
    )
    for v in (g.v_min_pu, g.v_max_pu):
        fig.add_hline(y=v, line=dict(color="#DC2626", dash="dash", width=1))
    return styled(fig, 300, "V (pu)")
