"""Grid (05 §4.2): choose and understand the network before placing agents.

All data comes from ``GridCatalogService``. With the pandapower backend, loading
a network or running a power flow takes seconds, so those calls run in a worker
thread (``run.io_bound``) while the page shows a spinner.
"""

from nicegui import run, ui

from src_thesis_reference.application.models import NetworkSource

from ..components import data_table, not_implemented, section, topology_figure
from ..layout import shell
from ..state import current_draft, services

_SOURCE_LABELS = {
    "simbench": "SimBench",
    "pandapower_builtin": "Built-in",
    "pandapower_file": "File",
}
_DEFAULT_SOURCE = {"type": "simbench", "code": "1-LV-semiurb4--0-sw"}
_ELEMENT_COLUMNS = [
    ("id", "Element"),
    ("element_type", "Type"),
    ("bus", "Bus"),
    ("profile_type", "Profile"),
    ("rated_kw", "Rated kW"),
]


def _yes_no(value: bool | None, no: str = "no") -> str:
    return "—" if value is None else ("yes" if value else no)


@ui.page("/build/grid")
def grid_page() -> None:
    s = services()
    draft = current_draft()
    selected = NetworkSource(**draft.grid.get("source", _DEFAULT_SOURCE))
    state: dict = {"source": selected, "bus": None, "voltages": None, "networks": []}

    with shell(
        "grid",
        "Grid",
        f"Network source, topology, elements and a single power-flow preview "
        f"({s.grid_backend} backend)",
    ):
        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Network",
                "Pick a source, a voltage level and a network",
                "hub",
                classes="basis-1/3 min-w-[360px]",
            ):
                source_toggle = ui.toggle(_SOURCE_LABELS, value=selected.type).props(
                    "no-caps dense"
                )
                level_select = ui.select([], label="Voltage level").classes("w-full")
                network_select = (
                    ui.select({}, label="Network", with_input=True)
                    .classes("w-full")
                    .props("options-dense")
                )
                upload = ui.upload(
                    label="pandapower JSON",
                    auto_upload=True,
                    on_upload=lambda: not_implemented("Upload network"),
                ).classes("w-full")
                upload.set_visibility(False)
                summary_box = ui.column().classes("w-full gap-1")

            with section(
                "Topology",
                "Colour = element type, or voltage after a preview. "
                "Click a bus to list its elements.",
                "account_tree",
                classes="grow",
            ):
                plot_box = ui.column().classes("w-full")

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Elements",
                "Loads, generators and storage of the selected network",
                "list",
                classes="grow basis-0",
            ):
                with ui.row().classes("items-center gap-2"):
                    bus_label = ui.label("All buses").classes("mls-card-caption")
                    clear_bus = ui.button(
                        "Show all", icon="close", on_click=lambda: select_bus(None)
                    ).props("flat dense")
                    clear_bus.set_visibility(False)
                elements_box = ui.column().classes("w-full")
            with section(
                "Power-flow preview",
                "One solve on the unmodified network (no RL)",
                "electric_bolt",
                classes="basis-1/3 min-w-0",
            ):
                with ui.input("Day", value="2016-06-15").classes("w-full") as day:
                    with ui.menu().props("no-parent-event") as menu:
                        with ui.date(mask="YYYY-MM-DD").bind_value(day):
                            with ui.row().classes("justify-end"):
                                ui.button("Close", on_click=menu.close).props("flat")
                    with day.add_slot("append"):
                        ui.icon("edit_calendar").on("click", menu.open).classes(
                            "cursor-pointer"
                        )
                ui.label("Hour of the day").classes("mls-card-caption")
                hour = ui.slider(min=0, max=23, value=12).props("label-always")
                preview_button = ui.button(
                    "Run preview", icon="play_arrow", on_click=lambda: run_preview()
                ).props("unelevated")
                pf_box = ui.column().classes("w-full gap-1")
            with section(
                "Limits and ratings",
                "Written to the draft's grid section",
                "tune",
                classes="basis-1/4 min-w-0",
            ):
                limits = draft.grid.get("limits", {})
                ui.number(
                    "V min (pu)", value=limits.get("v_min_pu", 0.95), step=0.01
                ).classes("w-full")
                ui.number(
                    "V max (pu)", value=limits.get("v_max_pu", 1.05), step=0.01
                ).classes("w-full")
                ui.number(
                    "Line max (%)", value=limits.get("line_max_percent", 100)
                ).classes("w-full")
                ui.select(
                    ["network", "rule", "file", "none"],
                    value=draft.grid.get("ratings", {}).get("source", "network"),
                    label="Line ratings source",
                ).classes("w-full")
                ui.button(
                    "Apply to draft",
                    icon="save",
                    on_click=lambda: not_implemented("Apply limits"),
                ).props("flat")

        # ------------------------------------------------------------ helpers
        def busy(box: ui.column, text: str) -> None:
            box.clear()
            with box, ui.row().classes("items-center gap-2"):
                ui.spinner(size="md")
                ui.label(text).classes("mls-card-caption")

        def failed(box: ui.column, error: Exception) -> None:
            box.clear()
            with box:
                ui.label(f"Failed: {error}").classes("text-negative text-body2")

        def show_summary(summary) -> None:
            info = summary.info
            rows = [
                ("Voltage level", info.voltage_level),
                (
                    "Buses / lines / trafos",
                    f"{info.buses} / {summary.lines} / {summary.transformers}",
                ),
                (
                    "Loads / sgens / storage",
                    f"{info.loads} / {info.sgens} / {info.storage}",
                ),
                (
                    "Profiles included",
                    _yes_no(info.has_profiles, "no (assign from catalogue)")
                    + (f" ({summary.profile_year})" if summary.profile_year else ""),
                ),
                ("Line ratings", _yes_no(info.has_line_ratings, "missing")),
                ("Geodata", _yes_no(info.has_geodata, "no (generated layout)")),
                (
                    "Total load / generation",
                    f"{summary.total_load_kw:,.1f} / "
                    f"{summary.total_generation_kw:,.1f} kW",
                ),
            ]
            summary_box.clear()
            with summary_box:
                ui.label(info.label).classes("text-body2 text-weight-medium")
                for label, value in rows:
                    with ui.row().classes("justify-between w-full no-wrap"):
                        ui.label(label).classes("mls-card-caption")
                        ui.label(str(value)).classes("text-body2")

        def show_topology(topology) -> None:
            plot_box.clear()
            with plot_box:
                figure = topology_figure(
                    topology,
                    voltages=state["voltages"],
                    highlight={state["bus"]} if state["bus"] else None,
                    height=460,
                )
                plot = ui.plotly(figure).classes("w-full")
                plot.on("plotly_click", on_bus_click)
                if topology.coordinates == "generated":
                    ui.label(
                        "No geodata in this network: layout generated from the "
                        "feeder tree."
                    ).classes("mls-card-caption")

        def show_elements(rows) -> None:
            elements_box.clear()
            with elements_box:
                if not rows:
                    ui.label("No loads, generators or storage.").classes(
                        "mls-card-caption"
                    )
                    return
                data_table(
                    [e.model_dump() for e in rows], _ELEMENT_COLUMNS, pagination=10
                )

        # ------------------------------------------------------------ actions
        async def load_network() -> None:
            source = state["source"]
            busy(summary_box, "Loading network …")
            busy(plot_box, "Building topology …")
            elements_box.clear()
            try:
                summary = await run.io_bound(s.grid.summary, source)
                topology = await run.io_bound(s.grid.topology, source)
                rows = await run.io_bound(s.grid.elements, source, state["bus"])
            except Exception as e:  # noqa: BLE001  show the error on the page
                failed(summary_box, e)
                plot_box.clear()
                return
            if state["source"] != source:  # the user picked another network
                return
            state["topology"] = topology
            show_summary(summary)
            show_topology(topology)
            show_elements(rows)

        async def select_bus(bus: str | None) -> None:
            state["bus"] = bus
            bus_label.set_text(f"Bus {bus}" if bus else "All buses")
            clear_bus.set_visibility(bus is not None)
            rows = await run.io_bound(s.grid.elements, state["source"], bus)
            show_elements(rows)
            if "topology" in state:
                show_topology(state["topology"])

        async def on_bus_click(e) -> None:
            points = (e.args or {}).get("points") or []
            if points and points[0].get("customdata"):
                await select_bus(points[0]["customdata"])

        async def run_preview() -> None:
            preview_button.disable()
            busy(pf_box, "Running power flow …")
            try:
                result = await run.io_bound(
                    s.grid.preview_powerflow,
                    state["source"],
                    day.value,
                    int(hour.value),
                )
            except Exception as e:  # noqa: BLE001
                failed(pf_box, e)
                return
            finally:
                preview_button.enable()
            pf_box.clear()
            with pf_box:
                ui.label("converged" if result.converged else "NOT converged").classes(
                    "text-positive" if result.converged else "text-negative"
                )
                if result.converged:
                    facts = [
                        (
                            "Voltage",
                            f"{result.min_voltage_pu:.3f} – "
                            f"{result.max_voltage_pu:.3f} pu",
                        ),
                        ("Max line loading", _percent(result.max_line_loading_percent)),
                        (
                            "Max trafo loading",
                            _percent(result.max_trafo_loading_percent),
                        ),
                        ("Losses", _kw(result.losses_kw)),
                        ("External grid", _kw(result.external_grid_kw)),
                        ("Violations", str(len(result.violations))),
                    ]
                    for label, value in facts:
                        with ui.row().classes("justify-between w-full no-wrap"):
                            ui.label(label).classes("mls-card-caption")
                            ui.label(value).classes("text-body2")
                for v in result.violations[:8]:
                    ui.label(v).classes("text-negative text-caption")
                if len(result.violations) > 8:
                    ui.label(f"… {len(result.violations) - 8} more").classes(
                        "text-caption"
                    )
                for note in result.notes:
                    ui.label(note).classes("mls-card-caption")
            state["voltages"] = result.bus_voltage_pu or None
            if "topology" in state:
                show_topology(state["topology"])

        def fill_networks() -> None:
            level = level_select.value
            options = {
                n.source.code: n.label
                for n in state["networks"]
                if level is None or n.voltage_level == level
            }
            network_select.set_options(options)
            code = state["source"].code
            network_select.value = (
                code if code in options else next(iter(options), None)
            )

        async def on_source(_=None) -> None:
            source_type = source_toggle.value
            upload.set_visibility(source_type == "pandapower_file")
            busy(summary_box, "Reading catalog …")
            state["networks"] = await run.io_bound(s.grid.list_networks, source_type)
            levels = list(dict.fromkeys(n.voltage_level for n in state["networks"]))
            level_select.set_options(levels)
            current = state["source"].code
            match = next(
                (n for n in state["networks"] if n.source.code == current), None
            )
            level_select.value = (
                match.voltage_level if match else next(iter(levels), None)
            )
            fill_networks()
            if not state["networks"]:
                summary_box.clear()
                with summary_box:
                    ui.label("No networks for this source yet.").classes(
                        "mls-card-caption"
                    )

        async def on_network(e) -> None:
            if not e.value:
                return
            state["source"] = NetworkSource(type=source_toggle.value, code=e.value)
            state["bus"], state["voltages"] = None, None
            state.pop("topology", None)
            bus_label.set_text("All buses")
            clear_bus.set_visibility(False)
            pf_box.clear()
            await load_network()

        source_toggle.on_value_change(on_source)
        level_select.on_value_change(lambda: fill_networks())
        network_select.on_value_change(on_network)
        ui.timer(0.1, on_source, once=True)


def _percent(value: float | None) -> str:
    return "not checked" if value is None else f"{value:.1f} %"


def _kw(value: float | None) -> str:
    return "—" if value is None else f"{value:,.1f} kW"
