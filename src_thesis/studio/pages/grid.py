"""Grid (05 §6): choose the network for the experiment, check it, set its rules.

Writes the draft's ``grid`` section: the network (``grid.source``), the
background elements, voltage and loading limits, line ratings, reactive power,
power-flow settings and what happens when the power flow fails. Only fields the
user changes are written (``DraftForm``).

Built from the network blocks in ``components/network.py``, shared with the
Inspect page (which adds the profiles and the comparison). With the pandapower
backend, loading a network or running a power flow takes seconds, so those calls
run in a worker thread (``run.io_bound``) while the page shows a spinner.
"""

from nicegui import run, ui

from src_thesis.application.models import NetworkSource
from src_thesis.studio.components.cards import section
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
from src_thesis.studio.forms import DraftForm
from src_thesis.studio.layout import shell
from src_thesis.studio.state import current_draft, services

BACKGROUND_HINTS = {
    "mapped_replacement": "Every element no agent owns keeps running with its own "
    "profile: a realistic feeder.",
    "scaled_background": "As above, times a factor: a stress test (e.g. Case 4 "
    "congestion).",
    "no_background": "Elements no agent owns are switched off: small, "
    "deterministic tests.",
}
RATINGS_HINTS = {
    "network": "Line and transformer ratings from the network itself.",
    "rule": "Ratings derived from the base case: its loading times the factor.",
    "file": "Ratings read from a JSON file (path).",
    "none": "No loading checks; only voltages are checked.",
}


@ui.page("/build/grid")
def grid_page() -> None:
    """Grid (05 §6): pick a network, see its topology and elements, run one power
    flow, and set the draft's limits and ratings.
    """
    s = services()
    draft = current_draft()
    # Values shown: the draft's, else the defaults (02 §3.3). Only changed fields are
    # written, so a default stays unset in the file.
    grid = s.config.resolve(draft).grid
    form = DraftForm(draft)
    draft_source = NetworkSource(**draft.grid.get("source", DEFAULT_SOURCE))
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
                    draft_source,
                    on_pick=lambda source: load_network(source),
                )
                # Which network the draft uses, and whether the picked one differs.
                source_note = ui.label().classes("mls-card-caption")
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

        _settings(form, grid)

        with ui.row().classes("justify-end w-full gap-2"):
            ui.button("Apply to draft", icon="save", on_click=lambda: apply()).props(
                "unelevated"
            )

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

        form.track("grid.source", lambda: picker.source.model_dump())

        def explain_source() -> None:
            """Say whether the picked network is the draft's or a new choice."""
            if picker.source == draft_source:
                source_note.set_text(
                    f"The draft uses this network ({draft_source.code})."
                )
            else:
                source_note.set_text(
                    f"Not saved yet: the draft uses {draft_source.code}. "
                    "Apply to draft to use this network."
                )

        def apply() -> None:
            """Save the changes; ask first if the network changes under the agents."""
            changes = form.changes()
            if not changes:
                ui.notify("No changes to apply")
                return
            if "grid.source" not in changes or not draft.participants:
                form.save(changes)
                return
            with ui.dialog() as dialog, ui.card().classes("mls-card max-w-[34rem]"):
                ui.label("Change the network?").classes("mls-card-title")
                ui.label(
                    f"The draft's {len(draft.participants)} participants sit on buses "
                    f"of {draft_source.code} and own its elements. On another network "
                    "these names usually do not exist. Keep them to fix them on the "
                    "Participants page, or remove them and place new ones there."
                ).classes("text-body2")
                with ui.row().classes("justify-end w-full gap-2"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button(
                        "Keep participants",
                        on_click=lambda: (dialog.close(), form.save(changes)),
                    ).props("outline")
                    ui.button(
                        "Remove participants",
                        on_click=lambda: (
                            dialog.close(),
                            form.save({**changes, "participants": []}),
                        ),
                    ).props("unelevated color=negative")
            dialog.open()

        async def load_network(source: NetworkSource) -> None:
            """A network was picked: show its summary, topology and elements."""
            explain_source()
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


def _hint(text: str = "") -> ui.label:
    """A short explanation under a control."""
    return ui.label(text).classes("mls-card-caption")


def _settings(form: DraftForm, grid: dict) -> None:
    """The draft's grid rules: background, limits, ratings, reactive power, power
    flow and assessment, each bound to its path in ``grid``.
    """
    bind = form.bind
    background, limits = grid.get("background", {}), grid.get("limits", {})
    ratings, reactive = grid.get("ratings", {}), grid.get("reactive", {})
    power_flow, assessment = grid.get("power_flow", {}), grid.get("assessment", {})
    with section(
        "Grid rules for the experiment",
        "Written to the draft's grid section (02 §3.3); empty fields use the default",
        "tune",
    ):
        with ui.row().classes("w-full gap-6 items-start no-wrap"):
            with ui.column().classes("grow basis-0 min-w-0 gap-1"):
                ui.label("Background elements").classes("text-weight-medium")
                mode = bind(
                    "grid.background.mode",
                    ui.select(
                        {
                            "mapped_replacement": "Mapped replacement",
                            "scaled_background": "Scaled background",
                            "no_background": "No background",
                        },
                        value=background.get("mode", "mapped_replacement"),
                        label="Elements no agent owns",
                    ).classes("w-full"),
                )
                mode_hint = _hint()
                scale = bind(
                    "grid.background.scale",
                    ui.number(
                        "Background factor",
                        value=background.get("scale", 1.0),
                        step=0.1,
                        min=0,
                    ).classes("w-full"),
                    float,
                )
                bind(
                    "grid.background.profiles",
                    ui.select(
                        {
                            "native": "Their own profiles",
                            "static": "Static element values",
                            "catalog": "Catalogue profiles by load type",
                        },
                        value=background.get("profiles", "native"),
                        label="Background profiles",
                    ).classes("w-full"),
                )
                _hint(
                    "For networks without profiles (pandapower built-ins): static "
                    "values or SimBench catalogue profiles."
                )

            with ui.column().classes("grow basis-0 min-w-0 gap-1"):
                ui.label("Limits").classes("text-weight-medium")
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "grid.limits.v_min_pu",
                        ui.number(
                            "V min (pu)", value=limits.get("v_min_pu"), step=0.01
                        ).classes("grow"),
                        float,
                    )
                    bind(
                        "grid.limits.v_max_pu",
                        ui.number(
                            "V max (pu)", value=limits.get("v_max_pu"), step=0.01
                        ).classes("grow"),
                        float,
                    )
                _hint(
                    "Empty: each bus's own limits from the network, else 0.95–1.05 "
                    "(D-15)."
                )
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "grid.limits.line_max_percent",
                        ui.number(
                            "Line max (%)", value=limits.get("line_max_percent", 100)
                        ).classes("grow"),
                        float,
                    )
                    bind(
                        "grid.limits.trafo_max_percent",
                        ui.number(
                            "Trafo max (%)", value=limits.get("trafo_max_percent", 100)
                        ).classes("grow"),
                        float,
                    )
                _hint("Loading above these counts as a violation.")

            with ui.column().classes("grow basis-0 min-w-0 gap-1"):
                ui.label("Ratings and reactive power").classes("text-weight-medium")
                rating = bind(
                    "grid.ratings.source",
                    ui.select(
                        {
                            "network": "From the network",
                            "rule": "Rule: base case × factor",
                            "file": "From a file",
                            "none": "None (no loading checks)",
                        },
                        value=ratings.get("source", "network"),
                        label="Line and transformer ratings",
                    ).classes("w-full"),
                )
                rating_hint = _hint()
                rule = ratings.get("rule") or {}
                factor = ui.number(
                    "Rule factor", value=rule.get("factor", 1.5), step=0.1, min=0
                ).classes("w-full")
                form.track(
                    "grid.ratings.rule",
                    lambda: (
                        {"type": "base_case_margin", "factor": float(factor.value or 0)}
                        if rating.value == "rule"
                        else ratings.get("rule")
                    ),
                )
                ratings_file = bind(
                    "grid.ratings.path",
                    ui.input("Ratings file", value=ratings.get("path", "")).classes(
                        "w-full"
                    ),
                )
                bind(
                    "grid.reactive.load",
                    ui.select(
                        {
                            "profile_ratio": "Keep the profile's q/p",
                            "fixed_pf": "Fixed power factor",
                        },
                        value=reactive.get("load", "profile_ratio"),
                        label="Reactive power of loads",
                    ).classes("w-full"),
                )
                bind(
                    "grid.reactive.fallback_pf",
                    ui.number(
                        "Power factor (fixed, or when p = 0)",
                        value=reactive.get("fallback_pf", 0.95),
                        step=0.01,
                        min=0,
                        max=1,
                    ).classes("w-full"),
                    float,
                )

            with ui.column().classes("grow basis-0 min-w-0 gap-1"):
                ui.label("Power flow and failures").classes("text-weight-medium")
                bind(
                    "grid.power_flow.algorithm",
                    ui.select(
                        {
                            "nr": "Newton-Raphson",
                            "iwamoto_nr": "Iwamoto Newton-Raphson",
                            "bfsw": "Backward/forward sweep",
                            "gs": "Gauss-Seidel",
                            "fdbx": "Fast decoupled (BX)",
                            "fdxb": "Fast decoupled (XB)",
                        },
                        value=power_flow.get("algorithm", "nr"),
                        label="Algorithm (pandapower runpp)",
                    ).classes("w-full"),
                )
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "grid.power_flow.tolerance_mva",
                        ui.number(
                            "Tolerance (MVA)",
                            value=power_flow.get("tolerance_mva"),
                            format="%.0e",
                        ).classes("grow"),
                        float,
                    )
                    bind(
                        "grid.power_flow.max_iteration",
                        ui.number(
                            "Max iterations", value=power_flow.get("max_iteration")
                        ).classes("grow"),
                        int,
                    )
                _hint("Empty: pandapower's defaults.")
                bind(
                    "grid.power_flow.init",
                    ui.select(
                        {
                            "results": "Previous step's results",
                            "auto": "Automatic",
                            "flat": "Flat start",
                            "dc": "DC power flow",
                        },
                        value=power_flow.get("init", "results"),
                        label="Start values",
                    ).classes("w-full"),
                )
                failure = bind(
                    "grid.assessment.non_convergence",
                    ui.select(
                        {
                            "truncate_episode": "End the episode",
                            "fail_run": "Fail the run",
                        },
                        value=assessment.get("non_convergence", "truncate_episode"),
                        label="When the power flow fails (D-12)",
                    ).classes("w-full"),
                )
                penalty = bind(
                    "grid.assessment.non_convergence_penalty",
                    ui.number(
                        "Penalty when the episode ends",
                        value=assessment.get("non_convergence_penalty"),
                    ).classes("w-full"),
                    float,
                )

    def explain() -> None:
        """Show the explanation and the fields that fit the current choices."""
        mode_hint.set_text(BACKGROUND_HINTS.get(mode.value, ""))
        scale.set_visibility(mode.value == "scaled_background")
        rating_hint.set_text(RATINGS_HINTS.get(rating.value, ""))
        factor.set_visibility(rating.value == "rule")
        ratings_file.set_visibility(rating.value == "file")
        penalty.set_visibility(failure.value == "truncate_episode")

    for control in (mode, rating, failure):
        control.on_value_change(explain)
    explain()
