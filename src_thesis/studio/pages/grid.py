"""Grid (05 §4.2): choose and understand the network before placing agents."""

from nicegui import ui

from src_thesis.application.models import NetworkSource

from ..components import data_table, not_implemented, section, topology_figure
from ..layout import shell
from ..state import current_draft, services

_SOURCE_LABELS = {
    "simbench": "SimBench",
    "pandapower_builtin": "pandapower built-in",
    "pandapower_file": "pandapower file",
}


@ui.page("/build/grid")
def grid_page() -> None:
    s = services()
    draft = current_draft()
    with shell(
        "grid",
        "Grid",
        "Network source, topology, elements and a single power-flow preview",
    ):
        selected = draft.grid.get(
            "source", {"type": "simbench", "code": "1-LV-semiurb4--0-sw"}
        )
        state = {"source": NetworkSource(**selected)}

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Network",
                "Pick a source and a network",
                "hub",
                classes="basis-1/3 min-w-[360px]",
            ):
                source_toggle = ui.toggle(
                    _SOURCE_LABELS, value=state["source"].type
                ).props("no-caps dense")
                network_select = ui.select({}, label="Network").classes("w-full")

                def refresh_networks() -> None:
                    networks = s.grid.list_networks(source_type=source_toggle.value)
                    network_select.options = {
                        n.source.code: f"{n.label}  ·  {n.source.code}"
                        for n in networks
                    }
                    network_select.value = (
                        state["source"].code
                        if state["source"].code in network_select.options
                        else next(iter(network_select.options), None)
                    )
                    network_select.update()

                source_toggle.on_value_change(lambda: refresh_networks())
                if source_toggle.value == "pandapower_file":
                    ui.upload(
                        label="pandapower JSON",
                        auto_upload=True,
                        on_upload=lambda: not_implemented("Upload network"),
                    ).classes("w-full")
                summary_box = ui.column().classes("w-full gap-1")

            with section(
                "Topology",
                "Colour = element type, or voltage after a preview",
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
                elements_box = ui.column().classes("w-full")
            with section(
                "Power-flow preview",
                "One solve on the unmodified network (no RL)",
                "electric_bolt",
                classes="basis-1/3 min-w-0",
            ):
                day = ui.input("Day", value="2016-06-15").classes("w-full")
                step = ui.slider(min=0, max=23, value=18).props("label-always")
                pf_box = ui.column().classes("w-full gap-1")
                ui.button(
                    "Run preview", icon="play_arrow", on_click=lambda: run_preview()
                ).props("unelevated")
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

        def show(voltages: dict[str, float] | None = None) -> None:
            source = state["source"]
            summary = s.grid.summary(source)
            summary_box.clear()
            with summary_box:
                for label, value in [
                    ("Voltage level", summary.info.voltage_level),
                    ("Buses", summary.info.buses),
                    (
                        "Loads / sgens / storage",
                        f"{summary.info.loads} / {summary.info.sgens} / {summary.info.storage}",
                    ),
                    (
                        "Profiles included",
                        (
                            "yes"
                            if summary.info.has_profiles
                            else "no (assign from catalogue)"
                        ),
                    ),
                    (
                        "Line ratings",
                        "yes" if summary.info.has_line_ratings else "missing",
                    ),
                    (
                        "Total load / generation",
                        f"{summary.total_load_kw} / {summary.total_generation_kw} kW",
                    ),
                ]:
                    with ui.row().classes("justify-between w-full"):
                        ui.label(label).classes("mls-card-caption")
                        ui.label(str(value)).classes("text-body2")
            plot_box.clear()
            with plot_box:
                ui.plotly(
                    topology_figure(s.grid.topology(source), voltages=voltages)
                ).classes("w-full")
            elements_box.clear()
            with elements_box:
                rows = [e.model_dump() for e in s.grid.elements(source)]
                data_table(
                    rows,
                    [
                        ("id", "Element"),
                        ("element_type", "Type"),
                        ("bus", "Bus"),
                        ("profile_type", "Profile"),
                        ("rated_kw", "Rated kW"),
                    ],
                    pagination=8,
                )

        def run_preview() -> None:
            result = s.grid.preview_powerflow(
                state["source"], day.value, int(step.value)
            )
            pf_box.clear()
            with pf_box:
                ui.label("converged" if result.converged else "NOT converged").classes(
                    "text-positive" if result.converged else "text-negative"
                )
                ui.label(
                    f"V: {result.min_voltage_pu:.3f} – {result.max_voltage_pu:.3f} pu"
                ).classes("text-body2")
                ui.label(
                    f"max line loading: {result.max_line_loading_percent} %"
                ).classes("text-body2")
                ui.label(f"violations: {len(result.violations)}").classes("text-body2")
            show(result.bus_voltage_pu)

        def on_network(e) -> None:
            if e.value:
                state["source"] = NetworkSource(type=source_toggle.value, code=e.value)
                show()

        network_select.on_value_change(on_network)
        refresh_networks()
        show()
