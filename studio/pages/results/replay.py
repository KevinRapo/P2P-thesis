"""The network replay of the Grid tab: one run's test day on its network, a step at a
time, with a slider and a play button (``heldout_grid.csv.gz`` and
``heldout_trades.csv.gz``).
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
from studio.theme import MARKET, MUTED

STEP_SECONDS = 0.6  # between two steps while playing
VOLTAGE, LOADING = "bus_voltage/", "line_loading/"


class StepSlider(ui.slider):
    """A slider whose value the server does not send back while it is dragged: NiceGUI
    echoes every value by default, which redraws the slider under the pointer and
    leaves it holding on after the mouse is let go."""

    LOOPBACK = False


class ReplayChart(NetworkChart):
    """The network at one step, its trades on the participants' markers: a seller in
    orange, a buyer in blue, sized by the energy it traded, filled when most of it was
    with peers and hollow when with the DSO (whose trades all run to the transformer,
    so they need no line). Peer trades are drawn as lines only for the participants in
    ``focus`` (a click on one), or all of them with ``all_links``.

    Options: those of ``NetworkChart`` (``voltages``, ``loading``, ``participants``),
    ``trades`` (``(seller, buyer, kWh, price, stage)``), ``buses`` (participant ->
    bus), ``focus`` (participants), ``all_links``.
    """

    height = 480
    SIZES = (14.0, 32.0)  # a marker's size for no and for the most energy traded

    def draw(self) -> None:
        o = self.o
        focus = o.get("focus") or set()
        peers = [
            t
            for t in o.trades
            if t[4] < 3 and (o.get("all_links") or {t[0], t[1]} & focus)
        ]
        self.trade_links(peers, o.buses)
        self._traders()

    def _traders(self) -> None:
        """A marker per participant that traded: its side, energy and counterpart."""
        amounts: dict[str, dict[str, float]] = {}

        for seller, buyer, kwh, _, stage in self.o.trades:
            kind = "peer" if stage < 3 else "dso"
            amounts.setdefault(seller, {}).setdefault(f"sold_{kind}", 0.0)
            amounts[seller][f"sold_{kind}"] += kwh
            amounts.setdefault(buyer, {}).setdefault(f"bought_{kind}", 0.0)
            amounts[buyer][f"bought_{kind}"] += kwh

        people = {a: v for a, v in amounts.items() if a in self.o.buses}
        idle = [
            (b, f"{a}: no trade") for a, b in self.o.buses.items() if a not in people
        ]
        self.rings(idle, MUTED, "Participant, no trade", size=14)
        biggest = max((sum(v.values()) for v in people.values()), default=0.0) or 1.0
        low, high = self.SIZES

        groups: dict[tuple[str, bool], list] = {}  # (side, mostly peers) -> markers

        for side, verb in (("sold", "sells"), ("bought", "buys")):
            other = "bought" if side == "sold" else "sold"

            for agent, v in people.items():
                peer, dso = v.get(f"{side}_peer", 0.0), v.get(f"{side}_dso", 0.0)

                if peer + dso <= 0 or peer + dso < sum(
                    v.get(f"{other}_{k}", 0.0) for k in ("peer", "dso")
                ):
                    continue  # it mostly did the other thing

                bus = self.o.buses[agent]

                if bus in self.pos:
                    text = (
                        f"{agent} {verb} {peer + dso:.2f} kWh: {peer:.2f} with peers, "
                        f"{dso:.2f} with the DSO"
                    )
                    size = low + (high - low) * sum(v.values()) / biggest
                    groups.setdefault((side, peer >= dso), []).append((bus, size, text))

        # One legend entry each: filled with peers, hollow with the DSO
        for (side, peers), name in (
            (("sold", True), "Sold to peers"),
            (("sold", False), "Sold to the DSO"),
            (("bought", True), "Bought from peers"),
            (("bought", False), "Bought from the DSO"),
        ):
            # Every entry in the legend at every step, even with no such trader
            rows = groups.get((side, peers)) or [(None, 14.0, "")]

            self.fig.add_scatter(
                x=[self.pos[r[0]][0] if r[0] else None for r in rows],
                y=[self.pos[r[0]][1] if r[0] else None for r in rows],
                mode="markers",
                name=name,
                hoverinfo="text",
                text=[r[2] for r in rows],
                customdata=[r[0] for r in rows],  # a click: the bus
                marker=dict(
                    size=[r[1] for r in rows],
                    symbol="circle" if peers else "circle-open",
                    color=MARKET["sell" if side == "sold" else "buy"],
                    line=dict(width=3),
                    opacity=0.85,
                ),
            )


def _columns(row: pd.Series, prefix: str) -> dict[str, float]:
    """The values of a step's row whose column starts with ``prefix``, by what follows;
    none of NaN (a step whose power flow did not converge has none)."""
    return {
        c[len(prefix) :]: v for c, v in row.items() if c.startswith(prefix) and v == v
    }


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
        self.first = self.last = 0
        first = selection.run if selection.run in labels else next(iter(labels))

        # Selector row: run | day | policy
        with ui.row().classes("w-full items-center gap-3"):
            self.run = ui.select(labels, value=first, label="Run").classes("w-96")
            self.day = ui.select([], label="Day").classes("w-40")
            self.policy = ui.select(
                POLICIES | {"random": "Random"}, value=selection.policy, label="Policy"
            ).classes("w-40")

        # Player row: back | play | on | slider | all peer trades
        with ui.row().classes("w-full items-center gap-3 no-wrap"):
            ui.button(icon="skip_previous", on_click=lambda: self._move(-1)).props(
                "flat round dense"
            ).tooltip("One step back")
            self.play = ui.button(icon="play_arrow", on_click=self._toggle).props(
                "round dense"
            )
            ui.button(icon="skip_next", on_click=lambda: self._move(1)).props(
                "flat round dense"
            ).tooltip("One step on")
            self.step = StepSlider(min=0, max=1, step=1, value=0).classes("grow")
            self.at = ui.label().classes("mls-card-caption w-16")  # fixed: no resizing
            self.all_links = ui.switch("All peer trades").tooltip(
                "Every peer trade as a line; without it, a click on a participant draws "
                "its own"
            )

        self.box = ui.column().classes("w-full gap-2")
        self.clock = ui.timer(STEP_SECONDS, self._advance, active=False)
        # While the slider is dragged only its label follows; the network, a whole
        # figure to redraw, follows when it is let go (redrawing at every value of a
        # drag floods the page until it stops responding)
        self.step.on_value_change(self._label)
        self.step.on("change", self._show)

        for field in (self.run, self.day, self.policy):
            field.on_value_change(self.draw)

        self.all_links.on_value_change(
            lambda e: self.chart and self.chart.set(all_links=e.value)
        )

        ui.timer(0.01, self.draw, once=True)

    # --- Reading ---------------------------------------------------------------------
    async def draw(self) -> None:
        """Read the run's tables and build the chart for its day and policy."""
        self._stop()
        self._drawn += 1
        drawn = self._drawn
        key = self.run.value
        self.selection.run, self.selection.policy = key, self.policy.value
        code, buses = self.service.network(key)
        grid = await run.io_bound(self.service.table, key, "heldout_grid")
        trades = await run.io_bound(self.service.table, key, "heldout_trades")
        topology = None

        if code and grid is not None:
            try:
                topology = await run.io_bound(
                    services().grid.topology, NetworkRef("simbench", code)
                )
            except Exception:  # noqa: BLE001  a caption is shown below
                topology = None

        if drawn != self._drawn:
            return

        self.grid, self.trades, self.buses = grid, trades, buses
        self.box.clear()
        self.chart = None

        with self.box:
            if grid is None or trades is None or topology is None:
                ui.label(
                    "Not recorded: a run from before the grid and trade tables, or "
                    "without its network in the saved scenario."
                ).classes("mls-card-caption")
                return

        days = sorted(grid.day.unique())
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

            self.first, self.last = steps[0], steps[-1]
            # Numbers, not text: props("min=0 max=23") gives strings, which break
            # Quasar's slider as soon as it is dragged
            self.step.props.update(min=int(steps[0]), max=int(self.last))
            self.step.value = steps[0]
            self.chart = ReplayChart(
                topology=topology,
                on_bus=self._focus,
                buses=self.buses,
                focus=set(),
                all_links=self.all_links.value,
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
            "loading": _columns(row, LOADING) or None,
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

    def _focus(self, bus: str) -> None:
        """A click on a bus: its participants' peer trades as lines, or none on a
        second click."""
        if self.chart is None:
            return

        here = {pid for pid, b in self.buses.items() if b == bus}
        self.chart.set(focus=set() if here == self.chart.o.focus else here)

    def _move(self, by: int) -> None:
        """One step back or on by hand (playing stops), within the day."""
        self._stop()

        if self.chart is not None:
            self.step.value = min(max(self.step.value + by, self.first), self.last)
            self._show()

    def _advance(self) -> None:
        """One step on while playing; the end of the day stops it."""
        if self.chart is None or self.step.value >= self.last:
            self._stop()
            return

        self.step.value += 1
        self._show()
