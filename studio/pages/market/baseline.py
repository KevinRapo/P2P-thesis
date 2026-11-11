"""The Market page's Baseline tab: the scenario played with the bidding rule over a
window of days, before any learning.

Every participant follows the market's rule without its noise, the evaluation's
``net_position`` baseline (``core/market/baseline.py``), on the scenario as the
Scenario page left it. The tab shows how stressed the network gets (loading, voltages,
violations), which fees that triggers and what the rule earns, and the network at the
step with the highest line loading. A sweep tries several values of one scaling factor
(``grid.load_scale``, ``generation_scale``, ``storage_scale``, MP-4i) without saving
them; *Use in the scenario* saves the one picked.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nicegui import run, ui

from core.grid.contract import NetworkRef
from core.market import baseline
from studio.components.cards import busy, failed, key_values, section
from studio.components.charts import NetworkChart, SeriesChart, VoltageChart
from studio.components.tables import data_table
from studio.state import services
from studio.theme import MARKET

MAX_DAYS = 31  # longer windows: core.market.baseline from a notebook
FACTORS = {
    "": "No sweep: the scenario as it is",
    "generation_scale": "Generation ×",
    "load_scale": "Load ×",
    "storage_scale": "Storage ×",
}
SUMMARY = [
    ("line_max_percent", "Line max (%)"),
    ("line_p95_percent", "Line p95 (%)"),
    ("trafo_max_percent", "Trafo max (%)"),
    ("voltage_min_pu", "V min (pu)"),
    ("voltage_max_pu", "V max (pu)"),
    ("steps_violated", "Steps violated"),
    ("grid_losses_kwh", "Losses (kWh)"),
    ("fees", "Fees"),
    ("team_money", "Team money"),
]


class LoadingChart(SeriesChart):
    """The highest line and transformer loading after each step, 100 % marked.
    Options: ``x``, ``line``, ``trafo`` (percent per step)."""

    y_title = "loading (%)"
    height = 300

    def draw(self) -> None:
        self.line(self.o.x, self.o.line, "Highest line", color=MARKET["sell"])
        self.line(self.o.x, self.o.trafo, "Transformer", color=MARKET["buy"])
        self.level(100.0)


def tab() -> None:
    """Controls on top; the sweep's table; the window over time and the network at
    its worst step."""
    s = services()
    state: dict[str, Any] = {"busy": False, "done": 0, "total": 0, "result": None}

    with section(
        "Baseline",
        "The scenario played with the market's bidding rule (no noise, no partners): "
        "how the network copes before any learning",
        "timeline",
    ):
        scenario_label = ui.label().classes("mls-card-caption")

        with ui.row().classes("w-full items-end gap-3"):
            start = ui.input("From (YYYY-MM-DD)").classes("w-44")
            end = ui.input("To (YYYY-MM-DD)").classes("w-44")
            factor = ui.select(FACTORS, value="", label="Sweep").classes("w-72")
            values = ui.input("Values", value="1, 1.5, 2, 3").classes("w-48")
            play_button = ui.button("Play", icon="play_arrow").props("unelevated no-caps")

        progress = ui.linear_progress(value=0, show_value=False).classes("w-full")
        progress.visible = False

    with section("Overview", "One row per value of the sweep", "table_rows"):
        table_box = ui.column().classes("w-full")

    with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
        with section("Over the window", icon="show_chart", classes="grow basis-0"):
            time_box = ui.column().classes("w-full")
        with section(
            "The network at its worst step",
            "Lines coloured by loading, buses by voltage, at the step with the highest "
            "line loading",
            "hub",
            classes="grow basis-0",
        ):
            network_box = ui.column().classes("w-full")

    def describe() -> None:
        sc = s.scenario.current()
        g = sc.grid
        scenario_label.text = (
            f"{s.scenario.shown_name()}: {len(sc.participants)} participants on "
            f"{g.code}; load ×{g.load_scale:g}, generation ×{g.generation_scale:g}, "
            f"storage ×{g.storage_scale:g}"
        )
        if not start.value:
            start.value = end.value = g.day

    def window() -> list[str]:
        days = [str(d.date()) for d in pd.date_range(start.value, end.value)]
        if not days:
            raise ValueError("the window is empty: 'From' is after 'To'")
        if len(days) > MAX_DAYS:
            raise ValueError(f"at most {MAX_DAYS} days here; longer from a notebook")
        return days

    def tick(done: int, total: int) -> None:
        state["done"], state["total"] = done, total

    def poll() -> None:
        if state["total"]:
            progress.value = state["done"] / state["total"]

    ui.timer(0.5, poll)

    async def play() -> None:
        if state["busy"]:
            return

        try:
            days = window()
            numbers = [float(v) for v in values.value.split(",")] if factor.value else []
        except ValueError as error:
            ui.notify(str(error), type="negative")
            return

        state.update(busy=True, done=0, total=0)
        progress.visible, progress.value = True, 0
        scenario = s.scenario.current()
        busy(table_box, "Playing the window …")

        try:
            if factor.value:
                table = await run.io_bound(
                    baseline.sweep, scenario, days, f"grid.{factor.value}", numbers, tick
                )
            else:
                table = None

            result = await run.io_bound(baseline.play, scenario, days, tick)
            source = NetworkRef("simbench", scenario.grid.code)
            topology = await run.io_bound(s.grid.topology, source)
        except Exception as error:  # noqa: BLE001  show the error on the page
            failed(table_box, error)
            return
        finally:
            state["busy"] = False
            progress.visible = False

        state["result"] = result
        render(table, result, topology, scenario)

    def use(value: float) -> None:
        setattr(s.scenario.current().grid, factor.value, value)
        s.scenario.save()
        ui.notify(f"{FACTORS[factor.value]}{value:g} saved in the scenario")
        describe()

    def render(table, result, topology, scenario) -> None:
        for box in (table_box, time_box, network_box):
            box.clear()

        with table_box:
            if table is None:
                key_values(
                    {label: _shown(result.summary()[key]) for key, label in SUMMARY}
                )
            else:
                name = f"grid.{factor.value}"
                rows = [
                    {"id": i, "value": f"×{r[name]:g}"}
                    | {key: _shown(r[key]) for key, _ in SUMMARY}
                    for i, r in table.iterrows()
                ]
                data_table(rows, [("value", FACTORS[factor.value])] + SUMMARY)
                with ui.row().classes("items-end gap-2"):
                    pick = ui.select(
                        {float(v): f"×{v:g}" for v in table[name]}, label="Value"
                    ).classes("w-32")
                    ui.button(
                        "Use in the scenario",
                        on_click=lambda: pick.value is not None and use(pick.value),
                    ).props("outline no-caps")
                ui.label(
                    "Over time and the network below: the scenario's own values."
                ).classes("mls-card-caption")

        steps = result.steps
        x = [
            f"{d} {int(h):02d}:{round(h % 1 * 60):02d}"
            for d, h in zip(steps.day, steps.hour)
        ]

        with time_box:
            LoadingChart(
                x=x,
                line=steps.max_line_loading_percent.tolist(),
                trafo=steps.max_trafo_loading_percent.tolist(),
            ).show()
            g = scenario.grid
            VoltageChart(
                x=x,
                highest=steps.max_voltage_pu.tolist(),
                lowest=steps.min_voltage_pu.tolist(),
                limits=[g.v_min_pu, g.v_max_pu],
            ).show()

        with network_box:
            worst = result.worst_step()
            if worst is None:
                ui.label("No converged step.").classes("mls-card-caption")
            else:
                row = steps.iloc[worst]
                ui.label(f"{row.day}, step {int(row.step)}").classes("mls-card-caption")
                NetworkChart(
                    topology=topology,
                    loading=result.line_loading.iloc[worst].dropna().to_dict(),
                    voltages=result.bus_voltage.iloc[worst].dropna().to_dict(),
                ).show()

    play_button.on_click(play)
    describe()


def _shown(value: Any) -> str:
    """A number as the tables show it."""
    if isinstance(value, (int,)) or (isinstance(value, float) and value.is_integer()):
        return f"{value:g}"
    return f"{value:.3f}" if isinstance(value, float) else str(value)
