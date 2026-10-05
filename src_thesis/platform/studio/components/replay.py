"""Replay of a simulated run: market and network, step by step.

Reads the run folder through ``ResultService``; a run that is still going is
followed (the replay reloads and, with "follow", jumps to the newest step).
"""

from dataclasses import dataclass
from typing import Callable

from nicegui import ui

from src_thesis.platform.studio.components.cards import section
from src_thesis.platform.studio.components.charts import topology_figure
from src_thesis.platform.studio.components.tables import data_table
from src_thesis.platform.studio.state import services

SPEEDS = {"0.5×": 0.5, "1×": 1.0, "2×": 2.0, "4×": 4.0}
AGENT_COLUMNS = [
    ("agent", "Agent"),
    ("generation", "Generation kWh"),
    ("demand", "Demand kWh"),
    ("sold", "Sold kWh"),
    ("bought", "Bought kWh"),
    ("battery", "Battery kWh"),
    ("net", "Net to grid kWh"),
]
ORDER_COLUMNS = [
    ("agent", "Agent"),
    ("side", "Side"),
    ("price", "Price"),
    ("quantity", "kWh"),
]
TRADE_COLUMNS = [
    ("buyer", "Buyer"),
    ("seller", "Seller"),
    ("price", "Price"),
    ("quantity", "kWh"),
    ("loss", "Loss kWh"),
    ("distance", "Distance"),
]


@dataclass
class ReplayHandle:
    """What a page can do with a replay.

    Attributes:
        jump: Move to a ``(day, step)``.
    """

    jump: Callable[[str, int], None]


def _clock(step: int, step_hours: float) -> str:
    minutes = round(step * step_hours * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def replay(run_id: str, live: bool = False) -> ReplayHandle:
    """Draw the replay of ``run_id`` where the caller is.

    Args:
        run_id: The run.
        live: Keep reloading, because the run may still be going.
    """
    s = services()
    state = {"records": [], "topology": None, "index": 0, "ended": not live}
    severities = {c.id: c.severity for c in s.results.checks(run_id)}

    with ui.row().classes("w-full items-center gap-3 no-wrap"):
        play = ui.button(icon="play_arrow").props("round dense unelevated")
        speed = ui.select(list(SPEEDS), value="1×", label="Speed").classes("w-24")
        slider = ui.slider(min=0, max=1, step=1, value=0).classes("grow")
        clock = ui.label("no steps yet").classes("mls-mono")
        follow = ui.switch("Follow", value=live).props("dense")
        if not live:
            follow.set_visibility(False)
    ui.label(
        "Play steps through the day. Colour of a bus is its voltage (green = "
        "inside the limits); a red outline marks a bus outside them, amber the "
        "participants."
    ).classes("mls-card-caption")

    with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
        with section("Network", icon="hub", classes="basis-1/2 min-w-0"):
            plot = ui.plotly(topology_figure_empty()).classes("w-full")
            grid_text = ui.label("").classes("text-body2")
            violations_box = ui.column().classes("w-full gap-0")
        with ui.column().classes("basis-1/2 min-w-0 gap-3"):
            with section("Market", icon="storefront"):
                prices = ui.label("").classes("text-body2")
                agents = data_table([], AGENT_COLUMNS, row_key="agent", pagination=0)
            with section("Orders and trades", icon="swap_horiz"):
                orders = data_table([], ORDER_COLUMNS, row_key="agent", pagination=0)
                trades = data_table([], TRADE_COLUMNS, row_key="key", pagination=6)
            with section("Checks at this step", icon="rule"):
                findings = ui.column().classes("w-full gap-0")

    def show() -> None:
        records = state["records"]
        if not records:
            return
        i = min(state["index"], len(records) - 1)
        r = records[i]
        topology = state["topology"]
        hours = topology.step_hours if topology else 1.0
        clock.set_text(f"{r['day']}  {_clock(r['step'], hours)}  (step {r['step']})")
        a = r.get("assessment") or {}
        bad = {
            v["element_id"]
            for v in a.get("violations", [])
            if v["element_type"] == "bus" and v["element_id"]
        }
        if topology:
            plot.update_figure(
                topology_figure(
                    topology.topology,
                    voltages=a.get("bus_voltage_pu") or None,
                    highlight=set(topology.participants.values()),
                    violating=bad,
                    height=420,
                )
            )
        if a and a.get("converged"):
            line = a.get("max_line_loading_percent")
            grid_text.set_text(
                f"voltage {a['min_voltage_pu']:.4f} – {a['max_voltage_pu']:.4f} pu"
                + (f" · max line loading {line:.0f} %" if line is not None else "")
                + f" · from upstream {a['external_grid_kwh']:.1f} kWh"
            )
        elif a:
            grid_text.set_text("power flow did not converge")
        else:
            grid_text.set_text("no power flow in this run")
        violations_box.clear()
        with violations_box:
            for v in a.get("violations", [])[:6]:
                ui.label(
                    f"{v['code']} {v.get('element_id') or ''} "
                    + (
                        f"{v['observed']:.3f} vs {v['limit']:.3f}"
                        if v.get("observed")
                        else ""
                    )
                ).classes("text-negative text-caption")
        k = r.get("kpis", {})
        prices.set_text(
            f"feed-in {k.get('fit', 0):.3g} · utility {k.get('utility', 0):.3g} · "
            f"clearing {k.get('clearing', 0):.3g}"
        )
        agents.rows = [
            {
                "agent": agent,
                "generation": round(v["generation_kwh"], 2),
                "demand": round(v["demand_kwh"], 2),
                "sold": round(v["sold_kwh"], 2),
                "bought": round(v["bought_kwh"], 2),
                "battery": "—" if v.get("soc_kwh") is None else round(v["soc_kwh"], 2),
                "net": round(v["production_kwh"] - v["consumption_kwh"], 2),
            }
            for agent, v in r["settlement"].items()
        ]
        agents.update()
        orders.rows = [
            {
                "agent": o["agent_id"],
                "side": "buy" if o["is_buy"] else "sell",
                "price": round(o["price"], 3),
                "quantity": round(o["quantity_kwh"], 2),
            }
            for o in r["orders"]
        ]
        orders.update()
        trades.rows = [
            {
                "key": n,
                "buyer": t["buyer_id"],
                "seller": t["seller_id"],
                "price": round(t["price"], 3),
                "quantity": round(t["quantity_kwh"], 3),
                "loss": round(t["loss_kwh"], 3),
                "distance": round(t["distance"], 1),
            }
            for n, t in enumerate(r["trades"])
        ]
        trades.update()
        findings.clear()
        with findings:
            if not r.get("checks"):
                ui.label("all checks passed at this step").classes("text-positive")
            for f in r.get("checks", []):
                kind = severities.get(f["check"], "invariant")
                ui.label(f"{kind.replace('_', ' ')}: {f['message']}").classes(
                    "text-caption "
                    + ("text-negative" if kind == "invariant" else "text-warning")
                )

    def load() -> None:
        state["records"] = s.results.replay(run_id)
        if state["topology"] is None:
            state["topology"] = s.results.topology(run_id)
        n = len(state["records"])
        slider.props(f"max={max(n - 1, 1)}")
        if n and follow.value and live and not state["ended"]:
            state["index"] = n - 1
            slider.set_value(n - 1)
        if live and not state["ended"]:
            status = s.experiments.snapshot(run_id).summary.state.value
            if status in ("COMPLETED", "FAILED", "CANCELLED"):
                state["ended"] = True
                severities.update({c.id: c.severity for c in s.results.checks(run_id)})
        show()

    def on_slide() -> None:
        state["index"] = int(slider.value)
        show()

    def advance() -> None:
        records = state["records"]
        if state["index"] + 1 < len(records):
            slider.set_value(state["index"] + 1)
        else:
            toggle(False)

    timer = ui.timer(0.8, advance, active=False)

    def toggle(on: bool | None = None) -> None:
        on = (not timer.active) if on is None else on
        timer.active = on
        play.props(f"icon={'pause' if on else 'play_arrow'}")
        if on:
            follow.set_value(False)

    def set_speed() -> None:
        timer.interval = 0.8 / SPEEDS[speed.value]

    def jump(day: str, step: int) -> None:
        for n, r in enumerate(state["records"]):
            if r["day"] == day and r["step"] == step:
                follow.set_value(False)
                slider.set_value(n)
                return

    play.on_click(lambda: toggle())
    speed.on_value_change(lambda: set_speed())
    slider.on_value_change(lambda: on_slide())
    load()
    if live:
        ui.timer(1.5, load)
    return ReplayHandle(jump)


def topology_figure_empty():
    """An empty figure shown until the first step is loaded."""
    import plotly.graph_objects as go

    return go.Figure().update_layout(height=420, margin=dict(l=0, r=0, t=0, b=0))
