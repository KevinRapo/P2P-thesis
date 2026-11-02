"""The network replay of the Grid tab: one run's test day on its network, a step at a
time, with a slider and a play button (``heldout_grid.csv.gz``, ``heldout_trades.csv.gz``).
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from nicegui import run, ui

from core.grid.contract import NetworkRef
from studio.adapters.results_service import ResultsService
from studio.components.charts import NetworkChart
from studio.pages.results.common import POLICIES, Selection
from studio.state import services

STEP_SECONDS = 0.6  # between two steps while playing
VOLTAGE, LOADING = "bus_voltage/", "line_loading/"


class ReplayChart(NetworkChart):
    """The network at one step. Options: those of ``NetworkChart`` (``voltages``,
    ``loading``, ``participants``), ``trades`` (``(seller, buyer, kWh, price,
    stage)``) and ``buses`` (participant -> bus)."""

    height = 480

    def draw(self) -> None:
        self.trade_links(self.o.trades, self.o.buses)


def _columns(row: pd.Series, prefix: str) -> dict[str, float]:
    """The values of a step's row whose column starts with ``prefix``, by what follows."""
    return {c[len(prefix) :]: v for c, v in row.items() if c.startswith(prefix)}


class Replay:
    """The selectors, the slider and the chart under them.

    Args:
        service: The Results service.
        labels: The ticked runs, key -> name.
        selection: What the tabs share (the run, the day and the policy).
    """

    def __init__(
        self, service: ResultsService, labels: dict[str, str], selection: Selection
    ) -> None:
        self.service, self.selection = service, selection
        self._drawn = 0  # the latest draw: an older one that wakes up later stops
        self.chart: Optional[ReplayChart] = None
        self.grid: Optional[pd.DataFrame] = None
        self.trades: Optional[pd.DataFrame] = None
        self.buses: dict[str, str] = {}
        self.last = 0
        first = selection.run if selection.run in labels else next(iter(labels))

        # Selector row: run | day | policy
        with ui.row().classes("w-full items-center gap-3"):
            self.run = ui.select(labels, value=first, label="Run").classes("w-96")
            self.day = ui.select([], label="Day").classes("w-40")
            self.policy = ui.select(
                POLICIES | {"random": "Random"}, value=selection.policy, label="Policy"
            ).classes("w-40")

        # Player row: play | slider
        with ui.row().classes("w-full items-center gap-3 no-wrap"):
            self.play = ui.button(icon="play_arrow", on_click=self._toggle).props(
                "round dense"
            )
            self.step = ui.slider(min=0, max=1, step=1, value=0).classes("grow")
            self.at = ui.label().classes("mls-card-caption")

        self.box = ui.column().classes("w-full gap-2")
        self.clock = ui.timer(STEP_SECONDS, self._advance, active=False)
        self.step.on_value_change(self._show)

        for field in (self.run, self.day, self.policy):
            field.on_value_change(self.draw)

        ui.timer(0.01, self.draw, once=True)

    # --- Reading ---------------------------------------------------------------------
    async def draw(self) -> None:
        """Read the run's tables and build the chart for its day and policy."""
        self._stop()
        self._drawn += 1
        drawn = self._drawn
        key = self.run.value
        self.selection.run, self.selection.policy = key, self.policy.value
        code, self.buses = self.service.network(key)
        self.grid = await run.io_bound(self.service.table, key, "heldout_grid")
        self.trades = await run.io_bound(self.service.table, key, "heldout_trades")
        topology = None

        if code and self.grid is not None:
            try:
                topology = await run.io_bound(
                    services().grid.topology, NetworkRef("simbench", code)
                )
            except Exception:  # noqa: BLE001  a caption is shown below
                topology = None

        if drawn != self._drawn:
            return

        self.box.clear()
        self.chart = None

        with self.box:
            if self.grid is None or self.trades is None or topology is None:
                ui.label(
                    "Not recorded: a run from before the grid and trade tables, or "
                    "without its network in the saved scenario."
                ).classes("mls-card-caption")
                return

        days = sorted(self.grid.day.unique())
        kept = self.day.value if self.day.value in days else self.selection.day
        self.day.set_options(days, value=kept if kept in days else days[0])

        if drawn != self._drawn:  # choosing the day drew again
            return

        self.selection.day = self.day.value
        self._build(topology)

    def _build(self, topology: Any) -> None:
        """The chart and the slider for the picked day and policy."""
        day, policy = self.day.value, self.policy.value
        grid = self.grid[(self.grid.day == day) & (self.grid.policy == policy)]
        trades = self.trades[(self.trades.day == day) & (self.trades.policy == policy)]
        self.rows = grid.sort_values("step").set_index("step")
        self.moves = {s: t for s, t in trades.groupby("step")}
        steps = list(self.rows.index)

        with self.box:
            if not steps:
                ui.label("This policy has no steps on this day.").classes(
                    "mls-card-caption"
                )
                return

            self.last = steps[-1]
            self.step.props(f"min={steps[0]} max={self.last}")
            self.step.value = steps[0]
            self.chart = ReplayChart(
                topology=topology,
                participants={bus: pid for pid, bus in self.buses.items()},
                buses=self.buses,
                **self._at(steps[0]),
            ).show()

        self._label()

    def _at(self, step: int) -> dict[str, Any]:
        """The chart's options for ``step``."""
        row = self.rows.loc[step]
        found = self.moves.get(step)
        trades = (
            []
            if found is None
            else list(
                zip(found.seller, found.buyer, found.kwh, found.price, found.stage)
            )
        )

        return {
            "voltages": _columns(row, VOLTAGE) or None,
            "loading": _columns(row, LOADING),
            "trades": trades,
        }

    # --- Moving ----------------------------------------------------------------------
    def _show(self) -> None:
        if self.chart is not None and int(self.step.value) in self.rows.index:
            self.chart.set(**self._at(int(self.step.value)))
            self._label()

    def _label(self) -> None:
        self.at.set_text(f"step {int(self.step.value)}")

    def _toggle(self) -> None:
        if self.clock.active:
            self._stop()
        elif self.chart is not None:
            self.clock.activate()
            self.play.props("icon=pause")

    def _stop(self) -> None:
        self.clock.deactivate()
        self.play.props("icon=play_arrow")

    def _advance(self) -> None:
        """One step on while playing; the end of the day stops it."""
        if self.chart is None or self.step.value >= self.last:
            self._stop()
            return

        self.step.value += 1
