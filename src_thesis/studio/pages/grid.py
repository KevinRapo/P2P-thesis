"""Grid (05 §6): choose the network for the experiment and check it.

Built from the network blocks in ``components/network.py``, shared with the
Inspect page (which adds the profiles and the comparison). With the pandapower
backend, loading a network or running a power flow takes seconds, so those calls
run in a worker thread (``run.io_bound``) while the page shows a spinner.
"""

from nicegui import run, ui

from src_thesis.application.models import NetworkSource
from src_thesis.studio.components.cards import not_implemented, section
from src_thesis.studio.components.network import (
    DEFAULT_SOURCE,
    ElementsTable,
    NetworkPicker,
    busy,
    clicked_bus,
    failed,
    show_summary,
    show_topology,
)
from src_thesis.studio.layout import shell
from src_thesis.studio.state import current_draft, services


@ui.page("/build/grid")
def grid_page() -> None:
    """Grid (05 §6): pick a network, see its topology and elements, run one power
    flow, and set the draft's limits and ratings.
    """
    s = services()
    draft = current_draft()
    # Page state shared by the handlers: the topology shown, the bus selected in it
    # and the voltages of the last preview (to colour the buses).
    state: dict = {"topology": None, "bus": None, "voltages": None}

    with shell(
        "grid",
        "Grid",
        "Network for the experiment: topology, elements and a power-flow preview",
    ):
        # Row 1: network picker | topology. Row 2: elements | power-flow preview |
        # limits. Empty boxes are filled by the handlers below.
        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Network",
                "Pick a source, a voltage level and a network",
                "hub",
                classes="basis-1/3 min-w-[360px]",
            ):
                picker = NetworkPicker(
                    s,
                    NetworkSource(**draft.grid.get("source", DEFAULT_SOURCE)),
                    on_pick=lambda source: load_network(source),
                )
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
                elements = ElementsTable(s)
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
                # Placeholder: these controls show the draft's values but are not saved
                # yet ("Apply to draft" is not wired; implementation status §4).
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

        # ------------------------------------------------------------ handlers
        def redraw() -> None:
            """Redraw the topology with the current voltages and selected bus."""
            if state["topology"] is not None:
                show_topology(
                    plot_box,
                    state["topology"],
                    voltages=state["voltages"],
                    bus=state["bus"],
                    on_click=on_bus_click,
                )

        async def load_network(source: NetworkSource) -> None:
            """A network was picked: show its summary, topology and elements."""
            state.update(topology=None, bus=None, voltages=None)
            pf_box.clear()
            busy(summary_box, "Loading network …")
            busy(plot_box, "Building topology …")
            try:
                summary = await run.io_bound(s.grid.summary, source)
                topology = await run.io_bound(s.grid.topology, source)
            except Exception as e:  # noqa: BLE001  show the error on the page
                failed(summary_box, e)
                plot_box.clear()
                return
            if picker.source != source:  # another network was picked meanwhile
                return
            state["topology"] = topology
            show_summary(summary_box, summary)
            redraw()
            await elements.show(source)

        async def on_bus_click(e) -> None:
            """A bus was clicked: list its elements and outline it."""
            state["bus"] = clicked_bus(e)
            await elements.show(picker.source, state["bus"])
            redraw()

        async def run_preview() -> None:
            """Run one power flow for the chosen day and hour, show it, colour the
            buses by voltage.
            """
            preview_button.disable()
            busy(pf_box, "Running power flow …")
            try:
                result = await run.io_bound(
                    s.grid.preview_powerflow, picker.source, day.value, int(hour.value)
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
            redraw()

        picker.start()


def _percent(value: float | None) -> str:
    """A loading in percent, or ``not checked`` without line ratings."""
    return "not checked" if value is None else f"{value:.1f} %"


def _kw(value: float | None) -> str:
    """A power in kW, or ``—`` when unknown."""
    return "—" if value is None else f"{value:,.1f} kW"
