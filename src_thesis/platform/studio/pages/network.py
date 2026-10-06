"""Grid & Participants (05 §6): the network and the agents placed on it.

Two tabs on one page, one network plot shared by both. "Grid" picks the network,
shows its facts and a power-flow preview and sets the grid rules (the draft's
``grid`` section); "Participants" places the agents on the same plot, edits them
and sets the time window (the draft's ``participants`` and ``time`` sections).
Only fields the user changes are written (``DraftForm``). Built from the network
blocks in ``components/network.py``, shared with the Inspect page.

Participants belong to the network saved in the draft, so the Participants tab
asks you to apply a newly picked network first. The tab last used is remembered
in the browser (a saved change reloads the page onto the same tab); a link can
open one with ``?tab=participants``.
"""

import copy
from typing import Any

from nicegui import app, events, run, ui

from src_thesis.platform.services.container import Services
from src_thesis.platform.services.models import ExperimentFile, NetworkSource
from src_thesis.platform.studio.components.cards import section
from src_thesis.platform.studio.components.charts import line_figure, topology_figure
from src_thesis.platform.studio.components.network import (
    DEFAULT_SOURCE,
    ElementsTable,
    NetworkPicker,
    busy,
    clicked_bus,
    failed,
    show_summary,
)
from src_thesis.platform.studio.components.participant_editor import (
    EditorContext,
    edit_participant,
    new_participant,
)
from src_thesis.platform.studio.forms import DraftForm, date_input, save_changes
from src_thesis.platform.studio.layout import shell
from src_thesis.platform.studio.state import current_draft, draft_network, services

GRID, PARTICIPANTS = "grid", "participants"
STORAGE_KEY = "network_tab"  # the tab last used, kept per browser
TAB_HINTS = {
    GRID: "Choose the network and look at it: its elements, a power-flow preview "
    "and the rules the experiment applies to it.",
    PARTICIPANTS: "Put the agents on the network: which buses, which elements they "
    "own, their profiles and batteries, and the days the experiment covers.",
}
PLOT_CAPTIONS = {
    GRID: "Colour: element type, or voltage after a preview. Click a bus to list "
    "its elements. Pink rings: the draft's participants.",
    PARTICIPANTS: "Pink rings: participants; filled: the selected one; blue "
    "squares: buses with a generator or storage that could be a participant. "
    "Click a ringed bus to select its participant.",
}
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
DAY_MODE_HINTS = {
    "fixed": "One day, every episode (the papers' setting).",
    "range": "Every day between start and end, in order.",
    "sampler": "Days drawn from the range that pass the filter; a share is held "
    "out for evaluation and never trained on.",
}
MONTHS = {
    i + 1: m
    for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())
}
COLUMNS = [
    ("id", "ID"),
    ("role", "Role"),
    ("bus", "Bus"),
    ("owns", "Owns"),
    ("profile", "Profiles"),
    ("scaling", "Scaling"),
    ("battery", "Battery"),
    ("check", "Check"),
]


@ui.page("/build/grid")
def network_page(tab: str | None = None) -> None:
    """Grid & Participants (05 §6): the "Grid" tab picks and checks the network,
    the "Participants" tab places the agents on it; both draw on one plot.

    Args:
        tab: ``"grid"`` or ``"participants"``, from a link that points at one tab
            (e.g. a Validate finding). Without it the tab last used opens.
    """
    s = services()
    draft = current_draft()
    first = tab if tab in TAB_HINTS else app.storage.user.get(STORAGE_KEY, GRID)
    if first not in TAB_HINTS:
        first = GRID
    view = NetworkView(
        s,
        draft_network(draft, DEFAULT_SOURCE),
        {p.id: p.bus for p in draft.participants if p.bus},
        first,
    )
    with shell(
        "grid",
        "Grid & Participants",
        "Pick the network, then place the participants on it",
    ):
        # ui.tabs is the tab bar; ui.tab_panels holds one panel per tab. The plot is
        # shared by both tabs, so it sits outside the panels: one group of panels
        # beside it and one below it follow the same tabs.
        with ui.tabs(value=first).props("align=left no-caps").classes("w-full") as tabs:
            ui.tab(GRID, label="1 · Grid", icon="hub")
            ui.tab(PARTICIPANTS, label="2 · Participants", icon="groups")
        hint = ui.label(TAB_HINTS[first]).classes("mls-card-caption")
        # keep_alive=False: a hidden panel is removed from the browser and drawn
        # again when its tab is opened, so its Plotly charts are never resized
        # while invisible. The Python side (state, handlers) stays as it is.
        beside, under = {}, {}
        with ui.row().classes("w-full gap-4 items-start no-wrap"):
            with ui.column().classes("basis-2/5 min-w-[360px]"):
                with ui.tab_panels(tabs, value=first, keep_alive=False).classes(
                    "w-full bg-transparent"
                ):
                    for key in TAB_HINTS:
                        beside[key] = ui.tab_panel(key).classes("p-0 gap-4")
            with ui.column().classes("grow min-w-0 mls-card gap-2"):
                ui.label("Network").classes("mls-card-title")
                view.build()
        with ui.tab_panels(tabs, value=first, keep_alive=False).classes(
            "w-full bg-transparent"
        ):
            for key in TAB_HINTS:
                under[key] = ui.tab_panel(key).classes("p-0 gap-4")

        def opened(key: str) -> None:
            """A tab was opened: the plot, the hint and the tab's hooks follow."""
            if key != view.stage:
                app.storage.user[STORAGE_KEY] = key
                hint.set_text(TAB_HINTS[key])
                view.set_stage(key)
                for hook in view.hooks:
                    hook(key)

        tabs.on_value_change(lambda e: opened(e.value))
        _grid_tab(s, draft, view, beside[GRID], under[GRID], tabs.set_value)
        _participants_tab(
            s, draft, view, beside[PARTICIPANTS], under[PARTICIPANTS], tabs.set_value
        )
        for hook in view.hooks:
            hook(first)


class NetworkView:
    """The one plot both tabs draw on, and what they mark on it.

    The Grid tab colours the buses by voltage and shows what a clicked bus holds;
    the Participants tab adds the participants' buses, the flexible buses and the
    selected participant. The loaded network and the marks live here, so switching
    tab never reloads the network.

    Args:
        services: The services (``grid.topology`` and ``grid.elements``).
        draft_source: The network saved in the draft; shown first.
        participants: Participant ID to bus ID (rings).
        stage: The tab shown.

    Attributes:
        source: The network shown.
        topology: The loaded topology; ``None`` until loaded.
        elements: The loaded elements.
        buses: Bus IDs of the network.
        bus: The bus clicked last (outlined on the Grid tab).
        voltages: Bus voltages of the last preview, to colour the buses.
        flexible: Buses that could become participants (squares).
        selected: The selected participant's ID (filled).
        picked: Returns the network picked on the Grid tab (saved or not).
        handlers: Per tab, called with the clicked bus ID.
        on_loaded: Called after a network is loaded.
        hooks: Called with the tab's name whenever a tab opens.
    """

    def __init__(
        self,
        services: Services,
        draft_source: NetworkSource,
        participants: dict[str, str],
        stage: str,
    ) -> None:
        self.services = services
        self.draft_source = draft_source
        self.source = draft_source
        self.participants = participants
        self.stage = stage
        self.topology: Any = None
        self.elements: list = []
        self.buses: list[str] = []
        self.bus: str | None = None
        self.voltages: dict[str, float] | None = None
        self.flexible: list[str] = []
        self.selected: str | None = None
        self.picked = lambda: draft_source
        self.handlers: dict = {}
        self.on_loaded: list = []
        self.hooks: list = []

    def build(self) -> None:
        """Make the plot's container where the caller is."""
        self.caption = ui.label(PLOT_CAPTIONS[self.stage]).classes("mls-card-caption")
        self.box = ui.column().classes("w-full")

    def set_stage(self, stage: str) -> None:
        """Switch what the plot emphasises and redraw."""
        self.stage = stage
        self.caption.set_text(PLOT_CAPTIONS[stage])
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
        """Draw the topology with the voltages, rings and marks of the tab."""
        if self.topology is None:
            return
        self.box.clear()
        with self.box:
            highlight = {self.bus} if self.bus and self.stage == GRID else None
            figure = topology_figure(
                self.topology, voltages=self.voltages, highlight=highlight, height=460
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


def _grid_tab(
    s: Services,
    draft: ExperimentFile,
    view: NetworkView,
    side: ui.element,
    below: ui.element,
    switch,
) -> None:
    """Tab 1: the picker and the power-flow preview beside the plot; the elements
    and the grid rules below it."""
    draft_source = view.draft_source
    # Values shown: the draft's, else the defaults (02 §3.3). Only changed fields are
    # written, so a default stays unset in the file.
    # The form view of the resolved file: the same dotted paths the controls write.
    grid = s.config.resolve(draft).to_data()["grid"]
    form = DraftForm(draft)

    with side:
        with section(
            "Network",
            "Filter by source, voltage level, category, SimBench scenario and switch "
            "state, then pick a network",
            "hub",
        ):
            picker = NetworkPicker(
                s, draft_source, on_pick=lambda source: load_network(source)
            )
            # Which network the draft uses, and whether the picked one differs.
            source_note = ui.label().classes("mls-card-caption")
            summary_box = ui.column().classes("w-full gap-1")
        with section(
            "Power-flow preview",
            "One solve on the unmodified network (no RL); colours the plot by "
            "voltage",
            "electric_bolt",
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

    with below:
        with section(
            "Elements",
            "Loads, generators and storage of the selected network",
            "list",
        ):
            elements = ElementsTable(s)

        _settings(form, grid)

        with ui.row().classes("justify-end w-full gap-2"):
            ui.button("Apply to draft", icon="save", on_click=lambda: apply()).props(
                "unelevated"
            )
            ui.button(
                "Next: participants",
                icon="arrow_forward",
                on_click=lambda: switch("participants"),
            ).props("outline")

    view.picked = lambda: picker.source
    form.track("grid.source", lambda: picker.source.model_dump())

    # ------------------------------------------------------------ handlers
    def explain_source() -> None:
        """Say whether the picked network is the draft's or a new choice."""
        if picker.source == draft_source:
            source_note.set_text(f"The draft uses this network ({draft_source.code}).")
        else:
            source_note.set_text(
                f"Not saved yet: the draft uses {draft_source.code}. "
                "Apply to draft to use this network (needed before placing "
                "participants on it)."
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
                "these names usually do not exist. Keep them to fix them in the "
                "participants stage, or remove them and place new ones there."
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
        pf_box.clear()
        busy(summary_box, "Loading network …")
        try:
            summary = await run.io_bound(s.grid.summary, source)
        except Exception as e:  # noqa: BLE001  show the error on the page
            failed(summary_box, e)
            return
        if picker.source != source:  # another network was picked meanwhile
            return
        show_summary(summary_box, summary)
        await view.load(source)
        await elements.show(source)

    async def on_bus_click(bus: str) -> None:
        """A bus was clicked: list its elements and outline it."""
        view.bus = bus
        await elements.show(picker.source, bus)
        view.redraw()

    view.handlers["grid"] = on_bus_click

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
                    ("Max trafo loading", _percent(result.max_trafo_loading_percent)),
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
                ui.label(f"… {len(result.violations) - 8} more").classes("text-caption")
            for note in result.notes:
                ui.label(note).classes("mls-card-caption")
        view.voltages = result.bus_voltage_pu or None
        view.redraw()

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


def _participants_tab(
    s: Services,
    draft: ExperimentFile,
    view: NetworkView,
    side: ui.element,
    below: ui.element,
    switch,
) -> None:
    """Tab 2: the assignment tools beside the plot; the participant table, the
    profile preview and the time window below it."""
    source = view.draft_source
    # The participants as editable data (what the dialog and the tools change);
    # every save goes through the typed file, which rejects unknown fields.
    members = [
        p.model_dump(mode="json", exclude_unset=True) for p in draft.participants
    ]
    # Network data for the checks and the editor, taken from the shared view once
    # it has loaded.
    net: dict[str, Any] = {
        "topology": None,
        "elements": [],
        "buses": [],
        "candidates": [],  # flexible buses: a generator or storage
    }
    selected: dict[str, str | None] = {"id": members[0]["id"] if members else None}
    catalogue: dict[str, Any] = {"demand": {}, "generation": {}, "csv": {}}

    def saved() -> bool:
        """Whether the network shown is the draft's; only then can participants be
        edited."""
        if view.picked() == source:
            return True
        ui.notify(
            "Apply the network in stage 1 first: participants belong to the "
            "network saved in the draft.",
            type="warning",
        )
        return False

    def save(participants: list[dict]) -> None:
        """Write the whole participant list to the draft and reload."""
        if saved():
            save_changes(draft, {"participants": participants})

    with side:
        gate = ui.label().classes("text-warning text-body2")
        with section(
            "Assignment tools",
            f"Network {source.code}. Every action saves the participant list to "
            "the draft.",
            "auto_fix_high",
        ):
            with ui.row().classes("gap-2"):
                ui.button(
                    "Add participant", icon="person_add", on_click=lambda: add()
                ).props("unelevated")
                ui.button(
                    "Import mapping",
                    icon="upload_file",
                    on_click=lambda: import_dialog(),
                ).props("outline")
                ui.button(
                    "Apply [P2] Table 6 roles",
                    icon="menu_book",
                    on_click=lambda: roles_dialog(),
                ).props("outline")
                ui.button(
                    "Remove all",
                    icon="delete_sweep",
                    on_click=lambda: confirm(
                        "Remove all participants?",
                        "The draft keeps its other settings; place or add new "
                        "participants afterwards.",
                        lambda: save([]),
                    ),
                ).props("flat color=negative")

        with section(
            "Flexible buses",
            "A bus with a generator or storage can be a participant; a bus with "
            "only regular load stays background",
            "bolt",
        ):
            rule_hint = ui.label("Loading the network …").classes("mls-card-caption")
            rule_replace = (
                ui.toggle(
                    {True: "Replace all participants", False: "Add to them"},
                    value=True,
                )
                .props("no-caps dense no-wrap")
                .classes("shrink-0")
            )
            rule_apply = ui.button(
                "Make flexible buses participants",
                icon="bolt",
                on_click=lambda: place(),
            ).props("unelevated")
            rule_apply.set_enabled(False)

    with below:
        with section(
            "Participants",
            f"{len(members)} agents; their order is the agents' order everywhere. "
            "Click a row, or a ringed bus on the plot, to select one.",
            "groups",
        ):
            table = (
                ui.table(
                    columns=[
                        {"name": f, "label": label, "field": f, "align": "left"}
                        for f, label in COLUMNS
                    ],
                    rows=_rows(members, None),
                    row_key="id",
                    pagination=10,
                )
                .classes("w-full")
                .props("flat dense")
            )
            table.add_slot(
                "body-cell-check",
                '<q-td :props="props"><span :class="props.value ? '
                "'text-negative' : 'text-positive'\">"
                "{{ props.value || 'ok' }}</span></q-td>",
            )
            with ui.row().classes("gap-1"):
                for icon, tip, action in (
                    ("edit", "Edit", lambda: edit()),
                    ("content_copy", "Duplicate", lambda: duplicate()),
                    ("arrow_upward", "Move up", lambda: move(-1)),
                    ("arrow_downward", "Move down", lambda: move(1)),
                    ("delete", "Remove", lambda: remove()),
                ):
                    ui.button(icon=icon, on_click=action).props(
                        "flat dense round"
                    ).tooltip(f"{tip} the selected participant")
                selected_label = ui.label().classes("mls-card-caption self-center")

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Profile preview",
                "Selected agent, scaled, for a week from the start of the time window",
                "show_chart",
                classes="grow basis-0 min-w-0",
            ):
                preview_box = ui.column().classes("w-full")
            _time_window(draft)

        with ui.row().classes("justify-start w-full"):
            ui.button(
                "Back: grid",
                icon="arrow_back",
                on_click=lambda: switch("grid"),
            ).props("outline")

    # ------------------------------------------------------------ handlers
    def refresh_gate(stage: str) -> None:
        """Warn when the plot shows a network the draft does not use yet."""
        gate.set_text(
            ""
            if view.picked() == source
            else f"The network picked in stage 1 is not saved yet; the draft uses "
            f"{source.code}. Apply it in stage 1 before editing participants."
        )

    view.hooks.append(refresh_gate)

    def by_id(pid: str | None) -> dict | None:
        return next((p for p in members if p["id"] == pid), None)

    def context(exclude: str | None = None) -> EditorContext:
        """What the editor may offer: the network, the profiles, the owners."""
        owners = {
            e: p["id"]
            for p in members
            if p["id"] != exclude
            for side_ in (p.get("owns") or {}).values()
            for e in side_
        }
        return EditorContext(
            buses=net["buses"],
            elements=net["elements"],
            demand_types=catalogue["demand"],
            generation_types=catalogue["generation"],
            csv_files=catalogue["csv"],
            owners=owners,
            ids={p["id"] for p in members},
        )

    def ready() -> bool:
        if not saved():
            return False
        if net["topology"] is None:
            ui.notify("The network is still loading")
            return False
        return True

    def add() -> None:
        if ready():
            edit_participant(
                new_participant(_free_number(members)),
                context(),
                lambda p: save(members + [p]),
                title="Add participant",
            )

    def edit() -> None:
        p = by_id(selected["id"])
        if p is None:
            ui.notify("Select a participant first")
        elif ready():
            edit_participant(
                p,
                context(exclude=p["id"]),
                lambda new: save([new if x["id"] == p["id"] else x for x in members]),
            )

    def duplicate() -> None:
        p = by_id(selected["id"])
        if p is None:
            ui.notify("Select a participant first")
        elif ready():
            copy_ = copy.deepcopy(p)
            copy_["id"] = f"{p['id']}_copy"
            copy_["owns"] = {"loads": [], "sgens": []}
            edit_participant(
                copy_,
                context(),
                lambda new: save(members + [new]),
                title="Duplicate participant (choose its own elements)",
            )

    def move(step: int) -> None:
        ids = [p["id"] for p in members]
        if selected["id"] not in ids:
            ui.notify("Select a participant first")
            return
        i = ids.index(selected["id"])
        j = i + step
        if 0 <= j < len(ids):
            order = list(members)
            order[i], order[j] = order[j], order[i]
            save(order)

    def remove() -> None:
        p = by_id(selected["id"])
        if p is None:
            ui.notify("Select a participant first")
            return
        confirm(
            f"Remove {p['id']}?",
            "Its owned elements go back to the background.",
            lambda: save([x for x in members if x["id"] != p["id"]]),
        )

    async def explain_rule() -> None:
        """Count the flexible buses and mark them on the plot."""
        if net["topology"] is None:
            return
        try:
            found = await run.io_bound(s.participants.placement_candidates, source)
        except ValueError as e:
            rule_hint.set_text(str(e))
            return
        net["candidates"] = found
        flexible = set(found)
        load_only = {
            e.bus
            for e in net["elements"]
            if e.element_type == "load" and e.bus not in flexible
        }
        rule_hint.set_text(
            f"{len(found)} flexible buses (a generator or storage), each becoming a "
            "participant that owns everything at its bus, with the elements' own "
            f"SimBench profiles. The {len(load_only)} other buses with load stay "
            "background."
            if found
            else "This network has no generator or storage: nothing can be a "
            "participant yet. Add one by hand, or choose another network."
        )
        rule_apply.set_enabled(bool(found))
        sync_plot()

    async def place() -> None:
        """Make the flexible buses participants and save them."""
        if not saved():
            return
        try:
            placed = await run.io_bound(s.participants.suggest_mapping, source)
        except Exception as e:  # noqa: BLE001  shown under the controls
            rule_hint.set_text(str(e))
            return
        if not rule_replace.value:
            placed = _merge(members, placed)
        save(placed)

    def import_dialog() -> None:
        if not saved():
            return
        with ui.dialog() as dialog, ui.card().classes("mls-card w-[38rem]"):
            ui.label("Import a participant mapping").classes("mls-card-title")
            ui.label(
                "JSON: a participant list in the experiment file's format (or an "
                "object with 'participants'). CSV: columns id, role, bus, loads, "
                "sgens, profile_source, demand, generation, scaling_mode, "
                "demand_target, generation_target, battery_kwh; lists separated by "
                "';'. The import replaces the current participants."
            ).classes("mls-card-caption")
            message = ui.label().classes("text-negative text-body2")

            async def received(e: events.UploadEventArguments) -> None:
                try:
                    rows = s.participants.import_mapping(
                        await e.file.read(), e.file.name
                    )
                except (ValueError, UnicodeDecodeError) as error:
                    message.set_text(str(error))
                    return
                dialog.close()
                save(rows)

            ui.upload(on_upload=received, auto_upload=True).props(
                'accept=".json,.csv"'
            ).classes("w-full")
            with ui.row().classes("justify-end w-full"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
        dialog.open()

    def roles_dialog() -> None:
        def apply() -> None:
            try:
                save(s.participants.paper_roles(draft.participants))
            except ValueError as e:
                ui.notify(str(e), type="warning")

        confirm(
            "Apply the [P2] Table 6 roles?",
            "The first eight participants become small industry, community hospital, "
            "university campus, shopping mall, residential complex, apartment "
            "building, community solar farm and parking lot: ID and role, capacity "
            "(as peak kW), battery (95 % efficiency, SoC 5–95 %) and catalogue "
            "profiles. Buses and owned elements stay. The profile types are a "
            "reconstruction: the paper does not publish its mapping (I-51).",
            apply,
        )

    def show_selected() -> None:
        """Mark the selected row, redraw the plot and the preview."""
        table.rows = _rows(members, net)
        table.selected = [r for r in table.rows if r["id"] == selected["id"]]
        table.update()
        selected_label.set_text(
            f"Selected: {selected['id']}" if selected["id"] else "No selection"
        )
        sync_plot()

    def sync_plot() -> None:
        """Give the shared plot the participants, flexible buses and selection."""
        view.participants = {p["id"]: p["bus"] for p in members if p.get("bus")}
        view.flexible = net.get("candidates", [])
        view.selected = selected["id"]
        view.redraw()

    async def preview() -> None:
        if not selected["id"]:
            preview_box.clear()
            with preview_box:
                ui.label("Add or place participants to preview them.").classes(
                    "mls-card-caption"
                )
            return
        busy(preview_box, "Reading profiles …")
        try:
            series = await run.io_bound(s.participants.preview, draft, selected["id"])
        except Exception as e:  # noqa: BLE001
            failed(preview_box, e)
            return
        preview_box.clear()
        with preview_box:
            if not series.y:
                ui.label("This participant has no demand or generation.").classes(
                    "mls-card-caption"
                )
                return
            ui.plotly(line_figure(series, height=300)).classes("w-full")

    async def select_id(pid: str) -> None:
        selected["id"] = pid
        show_selected()
        await preview()

    async def select(e: Any) -> None:
        await select_id(e.args[1]["id"])

    async def on_bus_click(bus: str) -> None:
        """A bus was clicked on the plot: select the participant that sits there."""
        owner = next((p for p in members if p.get("bus") == bus), None)
        if owner is None:
            ui.notify(f"No participant on bus {bus}")
        else:
            await select_id(owner["id"])

    view.handlers["participants"] = on_bus_click

    async def on_loaded() -> None:
        """The shared view loaded a network: take its data and show what fits."""
        net.update(
            topology=view.topology,
            elements=view.elements,
            buses=view.buses,
            candidates=[],
        )
        if view.source != source:  # a network the draft does not use yet
            sync_plot()
            return
        try:
            types = await run.io_bound(s.profiles.catalogue_types)
        except Exception as e:  # noqa: BLE001
            rule_hint.set_text(f"Profile catalogue not available: {e}")
            return
        catalogue["demand"] = {
            t.code: f"{t.code} · {t.description or t.category}"
            for t in types
            if t.table == "load"
        }
        catalogue["generation"] = {
            t.code: f"{t.code} · {t.description or t.category}"
            for t in types
            if t.table == "renewables"
        }
        catalogue["csv"] = {
            **s.profiles.data_files("data/demand"),
            **s.profiles.data_files("data/generation"),
        }
        await explain_rule()
        show_selected()
        await preview()

    view.on_loaded.append(on_loaded)

    def confirm(title: str, text: str, action: Any) -> None:
        with ui.dialog() as dialog, ui.card().classes("mls-card max-w-[34rem]"):
            ui.label(title).classes("mls-card-title")
            ui.label(text).classes("text-body2")
            with ui.row().classes("justify-end w-full"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Confirm", on_click=lambda: (dialog.close(), action())).props(
                    "unelevated"
                )
        dialog.open()

    table.on("rowClick", select)
    selected_label.set_text(
        f"Selected: {selected['id']}" if selected["id"] else "No selection"
    )


def _time_window(draft: ExperimentFile) -> None:
    """The ``time`` section: resolution, horizon and which days; with its own
    Apply and a live count of the training and evaluation days.
    """
    s = services()
    time = s.config.resolve(draft).to_data()["time"]
    days = time.get("days", {})
    flt = days.get("filter") or {}
    form = DraftForm(draft)
    bind = form.bind
    with section(
        "Time window",
        "Written to the draft's time section (02 §3.2)",
        "event",
        classes="basis-2/5 min-w-0",
    ):
        with ui.row().classes("w-full no-wrap gap-2 items-center"):
            bind(
                "time.resolution",
                ui.toggle(
                    {"hourly_aggregated": "Hourly", "native_15min": "15 min"},
                    value=time.get("resolution", "hourly_aggregated"),
                ).props("no-caps dense"),
            )
            bind(
                "time.horizon_steps",
                ui.number(
                    "Steps per episode", value=time.get("horizon_steps", 24), min=1
                ).classes("grow"),
                int,
            )
        ui.label(
            "Hourly: 24 steps make a day (the papers); 15 min: 96 steps make a day."
        ).classes("mls-card-caption")
        mode = bind(
            "time.days.mode",
            ui.select(
                {"fixed": "One fixed day", "range": "Date range", "sampler": "Sampler"},
                value=days.get("mode", "fixed"),
                label="Days",
            ).classes("w-full"),
        )
        mode_hint = ui.label().classes("mls-card-caption")
        fixed = bind("time.days.date", date_input("Date", days.get("date")))
        fixed.classes("w-full")
        with ui.row().classes("w-full no-wrap gap-2") as span:
            bind("time.days.start", date_input("Start", days.get("start"))).classes(
                "grow"
            )
            bind("time.days.end", date_input("End", days.get("end"))).classes("grow")
        with ui.row().classes("w-full no-wrap gap-2") as filters:
            day_type = ui.select(
                {"": "Any day", "workday": "Workdays", "weekend": "Weekends"},
                value=flt.get("day_type", ""),
                label="Day type",
            ).classes("grow")
            season = ui.select(
                {
                    "": "Any season",
                    "winter": "Winter",
                    "spring": "Spring",
                    "summer": "Summer",
                    "autumn": "Autumn",
                },
                value=flt.get("season", ""),
                label="Season",
            ).classes("grow")
            months = ui.select(
                MONTHS, value=list(flt.get("months", [])), label="Months", multiple=True
            ).classes("grow")
        form.track(
            "time.days.filter",
            lambda: {
                k: v
                for k, v in (
                    ("day_type", day_type.value),
                    ("season", season.value),
                    ("months", sorted(months.value or [])),
                )
                if v
            },
        )
        with ui.row().classes("w-full no-wrap gap-2"):
            bind(
                "time.days.eval_holdout",
                ui.number(
                    "Held out for evaluation",
                    value=days.get("eval_holdout", 0.2),
                    step=0.05,
                    min=0,
                    max=0.9,
                ).classes("grow"),
                float,
            )
            bind(
                "time.days.seed",
                ui.number("Split seed", value=days.get("seed", 42), step=1).classes(
                    "grow"
                ),
                int,
            )
        count = ui.label().classes("text-body2")
        with ui.row().classes("justify-end w-full"):
            ui.button("Apply to draft", icon="save", on_click=form.apply).props(
                "unelevated"
            )

    def refresh() -> None:
        """Show the fields of the chosen mode and count the days it selects."""
        mode_hint.set_text(DAY_MODE_HINTS.get(mode.value, ""))
        fixed.set_visibility(mode.value == "fixed")
        span.set_visibility(mode.value != "fixed")
        filters.set_visibility(mode.value == "sampler")
        try:
            preview_file = s.config.update(draft, form.changes())
            split = s.config.days(preview_file)
        except (ValueError, KeyError) as e:
            count.set_text(f"Selects no days yet: {e}")
            count.classes(replace="text-negative text-body2")
            return
        count.set_text(
            f"{len(split['train'])} training days · {len(split['eval'])} evaluation "
            "days" + ("" if form.changes() else " (as saved)")
        )
        count.classes(replace="text-body2")

    for control in form.elements:
        control.on_value_change(refresh)
    for control in (day_type, season, months):
        control.on_value_change(refresh)
    refresh()


def _rows(members: list[dict], net: dict[str, Any] | None) -> list[dict]:
    """Table rows, with what does not fit the network in "check"."""
    elements = {e.id: e for e in (net or {}).get("elements", [])}
    buses = set((net or {}).get("buses", []))
    rows = []
    for p in members:
        owns = p.get("owns") or {}
        owned = [e for side in owns.values() for e in side]
        profile, scaling = p.get("profile") or {}, p.get("scaling") or {}
        battery = p.get("battery")
        problems = []
        if net and net.get("topology") is not None:
            if p.get("bus") not in buses:
                problems.append("bus not in network")
            unknown = [e for e in owned if e not in elements]
            if unknown:
                problems.append(f"{len(unknown)} unknown elements")
            elsewhere = [
                e for e in owned if e in elements and elements[e].bus != p.get("bus")
            ]
            if elsewhere:
                problems.append(f"{len(elsewhere)} elements on another bus")
        rows.append(
            {
                "id": p["id"],
                "role": p.get("role", ""),
                "bus": p.get("bus", ""),
                "owns": ", ".join(owned) or "—",
                "profile": _profile_text(profile),
                "scaling": _scaling_text(scaling),
                "battery": (
                    f"{battery.get('nominal_capacity_kwh')} kWh" if battery else "—"
                ),
                "check": "; ".join(problems),
            }
        )
    return rows


def _profile_text(profile: dict) -> str:
    source = profile.get("source", "native")
    if source == "catalog":
        sides = [
            (profile.get(s) or {}).get("type") or "—" for s in ("demand", "generation")
        ]
        return f"catalog: {sides[0]} / {sides[1]}"
    return source


def _scaling_text(scaling: dict) -> str:
    mode = scaling.get("mode", "none")
    if mode == "none":
        return "—"
    unit = "kW" if mode == "peak_kw" else "kWh/a"
    return " / ".join(
        f"{scaling[s]:g} {unit}" for s in ("demand", "generation") if s in scaling
    )


def _free_number(members: list[dict]) -> int:
    """The next number for a default ``agent_NN`` ID."""
    ids = {p["id"] for p in members}
    n = len(ids) + 1
    while f"agent_{n:02d}" in ids:
        n += 1
    return n


def _merge(existing: list[dict], placed: list[dict]) -> list[dict]:
    """Placed participants added to the existing ones, skipping taken elements
    and renaming clashing IDs.
    """
    taken = {
        e for p in existing for side in (p.get("owns") or {}).values() for e in side
    }
    ids = {p["id"] for p in existing}
    out = list(existing)
    for p in placed:
        if any(e in taken for side in p["owns"].values() for e in side):
            continue
        base, n = p["id"], 2
        while p["id"] in ids:
            p = {**p, "id": f"{base}_{n}"}
            n += 1
        ids.add(p["id"])
        out.append(p)
    return out
