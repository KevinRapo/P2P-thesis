"""The one network plot that both stages draw on.

Stage 1 (grid) colours the buses by voltage and shows what a clicked bus holds;
stage 2 (participants) adds the participants' buses, the flexible buses and the
selected participant onto the same plot. The plot, the loaded network and the
state they share live here, so switching stage never reloads the network.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from nicegui import run, ui

from src_thesis.platform.services.container import Services
from src_thesis.platform.services.models import NetworkSource
from src_thesis.platform.studio.components.charts import topology_figure
from src_thesis.platform.studio.components.network import busy, clicked_bus, failed

GRID, PARTICIPANTS = "grid", "participants"
CAPTIONS = {
    GRID: "Colour: element type, or voltage after a preview. Click a bus to list "
    "its elements. Pink rings: the draft's participants.",
    PARTICIPANTS: "Pink rings: participants; filled: the selected one; blue "
    "squares: buses with a generator or storage that could be a participant. "
    "Click a ringed bus to select its participant.",
}


@dataclass
class NetworkView:
    """The shared plot and what it shows.

    Attributes:
        services: The services (``grid.topology`` and ``grid.elements``).
        source: The network shown.
        participants: Participant ID to bus ID (rings).
        topology: The loaded topology; ``None`` until loaded.
        elements: The loaded elements.
        buses: Bus IDs of the network.
        bus: The bus clicked last (outlined in stage 1).
        voltages: Bus voltages of the last power-flow preview, to colour the buses.
        flexible: Buses that could become participants (squares in stage 2).
        selected: The selected participant's ID (filled in stage 2).
        stage: ``"grid"`` or ``"participants"``.
        handlers: Per stage, called with the clicked bus ID.
        on_loaded: Called after a network is loaded.
    """

    services: Services
    source: NetworkSource
    participants: dict[str, str] = field(default_factory=dict)
    topology: Any = None
    elements: list = field(default_factory=list)
    buses: list[str] = field(default_factory=list)
    bus: str | None = None
    voltages: dict[str, float] | None = None
    flexible: list[str] = field(default_factory=list)
    selected: str | None = None
    stage: str = GRID
    handlers: dict[str, Callable[[str], Awaitable[None]]] = field(default_factory=dict)
    on_loaded: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    def build(self) -> None:
        """Draw the plot's container where the caller is."""
        self.caption = ui.label(CAPTIONS[self.stage]).classes("mls-card-caption")
        self.box = ui.column().classes("w-full")

    def set_stage(self, stage: str) -> None:
        """Switch what the plot emphasises and redraw."""
        self.stage = stage
        self.caption.set_text(CAPTIONS[stage])
        self.redraw()

    async def load(self, source: NetworkSource) -> None:
        """Load a network and draw it; a spinner shows meanwhile."""
        self.source = source
        self.topology, self.bus, self.voltages = None, None, None
        busy(self.box, "Building topology …")
        try:
            topology = await run.io_bound(self.services.grid.topology, source)
            elements = await run.io_bound(self.services.grid.elements, source)
        except Exception as e:  # noqa: BLE001  show the error on the page
            failed(self.box, e)
            return
        if self.source != source:  # another network was picked meanwhile
            return
        self.topology, self.elements = topology, elements
        self.buses = [b["id"] for b in topology.buses]
        self.redraw()
        for callback in self.on_loaded:
            await callback()

    def redraw(self) -> None:
        """Draw the topology with the voltages, rings and marks of the stage."""
        if self.topology is None:
            return
        self.box.clear()
        with self.box:
            highlight = {self.bus} if self.bus and self.stage == GRID else None
            figure = topology_figure(
                self.topology,
                voltages=self.voltages,
                highlight=highlight,
                height=460,
            )
            position = {b["id"]: (b["x"], b["y"]) for b in self.topology.buses}
            taken = set(self.participants.values())
            if self.stage == PARTICIPANTS:
                free = [
                    position[bus]
                    for bus in self.flexible
                    if bus in position and bus not in taken
                ]
                figure.add_scatter(
                    x=[x for x, _ in free],
                    y=[y for _, y in free],
                    mode="markers",
                    marker={
                        "size": 13,
                        "symbol": "square-open",
                        "color": "#2563EB",
                        "line": {"width": 1.5},
                    },
                    name="flexible bus",
                    hoverinfo="skip",
                )
            at = [position[bus] for bus in taken if bus in position]
            figure.add_scatter(
                x=[x for x, _ in at],
                y=[y for _, y in at],
                mode="markers",
                marker={
                    "size": 15,
                    "color": "rgba(0,0,0,0)",
                    "line": {"color": "#DB2777", "width": 2},
                },
                name="participant bus",
                hoverinfo="skip",
            )
            chosen = self.participants.get(self.selected or "")
            if self.stage == PARTICIPANTS and chosen in position:
                x, y = position[chosen]
                figure.add_scatter(
                    x=[x],
                    y=[y],
                    mode="markers",
                    marker={"size": 15, "color": "#DB2777"},
                    name=f"selected: {self.selected}",
                    hoverinfo="name",
                )
            plot = ui.plotly(figure).classes("w-full")
            plot.on("plotly_click", self._clicked)
            if self.topology.coordinates == "generated":
                ui.label(
                    "No geodata in this network: layout generated from the feeder tree."
                ).classes("mls-card-caption")

    async def _clicked(self, event: Any) -> None:
        bus = clicked_bus(event)
        handler = self.handlers.get(self.stage)
        if bus and handler:
            await handler(bus)
