"""Network building blocks shared by the Grid and Inspect pages.

Each block builds its own controls and fills itself through the services; pages
only place the blocks and connect them (e.g. "when the picker changes, load the
summary"). Slow service calls run in a worker thread (``run.io_bound``) while the
block shows a spinner.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import run, ui

from src_thesis.application.container import Services
from src_thesis.application.models import (
    NetworkSource,
    NetworkSummary,
    ProfileType,
    TopologyView,
)
from src_thesis.studio.components.cards import not_implemented
from src_thesis.studio.components.charts import line_figure, topology_figure
from src_thesis.studio.components.tables import data_table

SOURCE_LABELS = {
    "simbench": "SimBench",
    "pandapower_builtin": "Built-in",
    "pandapower_file": "File",
}
DEFAULT_SOURCE = {"type": "simbench", "code": "1-LV-semiurb4--0-sw"}
ELEMENT_COLUMNS = [
    ("id", "Element"),
    ("element_type", "Type"),
    ("bus", "Bus"),
    ("profile_type", "Profile"),
    ("rated_kw", "Rated kW"),
]


def busy(box: ui.element, text: str) -> None:
    """Replace a box's content with a spinner while a slow call runs."""
    box.clear()
    with box, ui.row().classes("items-center gap-2"):
        ui.spinner(size="md")
        ui.label(text).classes("mls-card-caption")


def failed(box: ui.element, error: Exception) -> None:
    """Show an error in place of a box's content."""
    box.clear()
    with box:
        ui.label(f"Failed: {error}").classes("text-negative text-body2")


def yes_no(value: bool | None, no: str = "no") -> str:
    """``yes`` / ``no`` (or the given text) for a flag; ``—`` when unknown."""
    return "—" if value is None else ("yes" if value else no)


def summary_facts(summary: NetworkSummary) -> list[tuple[str, str]]:
    """The facts of a network as (label, value) rows, shared by summary and compare."""
    info = summary.info
    return [
        ("Voltage level", info.voltage_level),
        ("Buses", str(info.buses)),
        ("Lines / trafos", f"{summary.lines} / {summary.transformers}"),
        ("Loads / sgens / storage", f"{info.loads} / {info.sgens} / {info.storage}"),
        (
            "Profiles included",
            yes_no(info.has_profiles, "no (assign from catalogue)")
            + (f" ({summary.profile_year})" if summary.profile_year else ""),
        ),
        ("Line ratings", yes_no(info.has_line_ratings, "missing")),
        ("Geodata", yes_no(info.has_geodata, "no (generated layout)")),
        ("Total load", f"{summary.total_load_kw:,.1f} kW"),
        ("Total generation", f"{summary.total_generation_kw:,.1f} kW"),
    ]


def show_summary(box: ui.element, summary: NetworkSummary) -> None:
    """Fill ``box`` with the network's name, counts and data flags."""
    box.clear()
    with box:
        ui.label(summary.info.label).classes("text-body2 text-weight-medium")
        for label, value in summary_facts(summary):
            with ui.row().classes("justify-between w-full no-wrap"):
                ui.label(label).classes("mls-card-caption")
                ui.label(value).classes("text-body2")


def show_topology(
    box: ui.element,
    topology: TopologyView,
    voltages: dict[str, float] | None = None,
    bus: str | None = None,
    on_click: Callable[[Any], Awaitable[None]] | None = None,
    height: int = 460,
) -> None:
    """Draw the topology into ``box``; a click on a bus calls ``on_click``."""
    box.clear()
    with box:
        figure = topology_figure(
            topology, voltages=voltages, highlight={bus} if bus else None, height=height
        )
        plot = ui.plotly(figure).classes("w-full")
        if on_click:
            plot.on("plotly_click", on_click)
        if topology.coordinates == "generated":
            ui.label(
                "No geodata in this network: layout generated from the feeder tree."
            ).classes("mls-card-caption")


def clicked_bus(event: Any) -> str | None:
    """The bus ID of a Plotly click event (buses carry it as ``customdata``)."""
    points = (event.args or {}).get("points") or []
    return points[0].get("customdata") if points else None


class NetworkPicker:
    """Source toggle, voltage level and network dropdowns.

    Args:
        services: The services (``grid.list_networks`` fills the dropdowns).
        initial: The network shown first.
        on_pick: Called with the picked ``NetworkSource`` (also for ``initial``).
        allow_file: Show the "File" source and its (not yet working) upload.
    """

    def __init__(
        self,
        services: Services,
        initial: NetworkSource,
        on_pick: Callable[[NetworkSource], Awaitable[None]],
        allow_file: bool = True,
    ) -> None:
        self.services = services
        self.source = initial
        self.on_pick = on_pick
        self.networks: list = []
        labels = dict(SOURCE_LABELS)
        if not allow_file:
            labels.pop("pandapower_file")
        self.toggle = ui.toggle(labels, value=initial.type).props("no-caps dense")
        self.level = ui.select([], label="Voltage level").classes("w-full")
        self.network = (
            ui.select({}, label="Network", with_input=True)
            .classes("w-full")
            .props("options-dense")
        )
        # Only shown for the "File" source; uploading is not implemented yet.
        self.upload = ui.upload(
            label="pandapower JSON",
            auto_upload=True,
            on_upload=lambda: not_implemented("Upload network"),
        ).classes("w-full")
        self.upload.set_visibility(False)
        self.status = ui.column().classes("w-full gap-1")
        self.toggle.on_value_change(self._on_source)
        self.level.on_value_change(lambda: self._fill_networks())
        self.network.on_value_change(self._on_network)

    def start(self) -> None:
        """Fill the dropdowns once the page is built (loads ``initial``)."""
        ui.timer(0.1, self._on_source, once=True)

    async def _on_source(self, _: Any = None) -> None:
        source_type = self.toggle.value
        self.upload.set_visibility(source_type == "pandapower_file")
        busy(self.status, "Reading catalog …")
        self.networks = await run.io_bound(
            self.services.grid.list_networks, source_type
        )
        self.status.clear()
        levels = list(dict.fromkeys(n.voltage_level for n in self.networks))
        self.level.set_options(levels)
        match = next(
            (n for n in self.networks if n.source.code == self.source.code), None
        )
        self.level.value = match.voltage_level if match else next(iter(levels), None)
        self._fill_networks()
        if not self.networks:
            with self.status:
                ui.label("No networks for this source yet.").classes("mls-card-caption")

    def _fill_networks(self) -> None:
        options = {
            n.source.code: n.label
            for n in self.networks
            if self.level.value is None or n.voltage_level == self.level.value
        }
        self.network.set_options(options)
        code = self.source.code
        self.network.value = code if code in options else next(iter(options), None)

    async def _on_network(self, e: Any) -> None:
        if not e.value:
            return
        self.source = NetworkSource(type=self.toggle.value, code=e.value)
        await self.on_pick(self.source)


class ElementsTable:
    """The network's loads, generators and storage, optionally for one bus.

    Args:
        services: The services (``grid.elements``).
    """

    def __init__(self, services: Services) -> None:
        self.services = services
        self.source: NetworkSource | None = None
        self.bus: str | None = None
        with ui.row().classes("items-center gap-2"):
            self.label = ui.label("All buses").classes("mls-card-caption")
            self.clear_button = ui.button(
                "Show all", icon="close", on_click=lambda: self.show(self.source, None)
            ).props("flat dense")
            self.clear_button.set_visibility(False)
        self.box = ui.column().classes("w-full")

    async def show(self, source: NetworkSource | None, bus: str | None = None) -> None:
        """Load and show the elements of ``source`` (all, or those on ``bus``)."""
        self.source, self.bus = source, bus
        self.label.set_text(f"Bus {bus}" if bus else "All buses")
        self.clear_button.set_visibility(bus is not None)
        if source is None:
            self.box.clear()
            return
        busy(self.box, "Reading elements …")
        try:
            rows = await run.io_bound(self.services.grid.elements, source, bus)
        except Exception as e:  # noqa: BLE001  show the error on the page
            failed(self.box, e)
            return
        self.box.clear()
        with self.box:
            if not rows:
                ui.label("No loads, generators or storage.").classes("mls-card-caption")
                return
            data_table([r.model_dump() for r in rows], ELEMENT_COLUMNS, pagination=10)


class ProfileInspector:
    """The network's SimBench profiles: a selectable table and a plot.

    Values are factors of an element's rated power (1.0 = rated power).

    Args:
        services: The services (``profiles.profile_types`` / ``profile_series``).
    """

    def __init__(self, services: Services) -> None:
        self.services = services
        self.source: NetworkSource | None = None
        self.selected: list[str] = []
        with ui.row().classes("w-full gap-4 items-start no-wrap"):
            self.table_box = ui.column().classes("basis-1/2 min-w-0")
            with ui.column().classes("grow basis-0 min-w-0 gap-2"):
                with ui.row().classes("items-center gap-3 w-full"):
                    with ui.input("Start day", value="2016-06-15").classes(
                        "w-36"
                    ) as self.day:
                        with ui.menu().props("no-parent-event") as menu:
                            with ui.date(mask="YYYY-MM-DD").bind_value(self.day):
                                with ui.row().classes("justify-end"):
                                    ui.button("Close", on_click=menu.close).props(
                                        "flat"
                                    )
                        with self.day.add_slot("append"):
                            ui.icon("edit_calendar").on("click", menu.open).classes(
                                "cursor-pointer"
                            )
                    self.span = ui.select(
                        {1: "1 day", 7: "1 week", 28: "4 weeks", 366: "1 year"},
                        value=7,
                        label="Window",
                    ).classes("w-28")
                    self.resolution = ui.toggle(
                        {"15min": "15 min", "hourly": "hourly", "daily": "daily"},
                        value="hourly",
                    ).props("no-caps dense")
                    self.quantity = (
                        ui.toggle({"p": "P", "q": "Q"}, value="p")
                        .props("no-caps dense")
                        .tooltip("Active or reactive power; only loads have Q")
                    )
                self.plot_box = ui.column().classes("w-full")
        for control in (self.day, self.span, self.resolution, self.quantity):
            control.on_value_change(lambda: self.plot())

    async def show(self, source: NetworkSource) -> None:
        """Load the profile list of ``source``; plot the first two profiles."""
        self.source = source
        busy(self.table_box, "Reading profiles …")
        self.plot_box.clear()
        try:
            types = await run.io_bound(self.services.profiles.profile_types, source)
        except Exception as e:  # noqa: BLE001
            failed(self.table_box, e)
            return
        if self.source != source:  # another network was picked meanwhile
            return
        self.table_box.clear()
        with self.table_box:
            if not types:
                ui.label(
                    "This network ships no profiles (pandapower built-in networks "
                    "have none; SimBench networks do)."
                ).classes("mls-card-caption")
                self.selected = []
                return
            rows = profile_rows(types)
            table = (
                ui.table(
                    columns=[
                        {
                            "name": k,
                            "label": k.capitalize(),
                            "field": k,
                            "align": "left",
                            "sortable": True,
                        }
                        for k in rows[0]
                    ],
                    rows=rows,
                    row_key="code",
                    selection="multiple",
                    pagination=10,
                )
                .classes("w-full")
                .props("flat dense")
            )
            table.selected = rows[:2]
            table.on_select(lambda e: self.plot([r["code"] for r in e.selection]))
        await self.plot([r["code"] for r in rows[:2]])

    async def plot(self, codes: list[str] | None = None) -> None:
        """Plot the selected profiles over the chosen window and resolution."""
        if codes is not None:
            self.selected = codes
        if self.source is None:
            return
        if not self.selected:
            self.plot_box.clear()
            with self.plot_box:
                ui.label("Select profiles in the table.").classes("mls-card-caption")
            return
        busy(self.plot_box, "Reading profiles …")
        try:
            series = await run.io_bound(
                self.services.profiles.profile_series,
                self.source,
                self.selected,
                self.day.value,
                int(self.span.value),
                self.resolution.value,
                self.quantity.value,
            )
        except Exception as e:  # noqa: BLE001
            failed(self.plot_box, e)
            return
        self.plot_box.clear()
        with self.plot_box:
            if not series.y:
                ui.label(
                    "No values: reactive power (Q) exists only for load profiles."
                ).classes("mls-card-caption")
                return
            ui.plotly(line_figure(series, height=340)).classes("w-full")


def profile_rows(types: list[ProfileType]) -> list[dict]:
    """Table rows for profile types."""
    return [
        {
            "code": p.code,
            "category": p.category,
            "table": p.table,
            "quantities": "/".join(q.upper() for q in p.quantities),
            "elements": p.elements,
            "mean": p.mean,
            "peak": p.peak,
        }
        for p in types
    ]
