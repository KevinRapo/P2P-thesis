"""Grid and participants: one page, two tabs, one plot.

Tab 1 picks the network, shows its parameters and sets the grid rules; tab 2
places the participants on the same plot and sets the time window. Both draw on
the one ``NetworkView``; each tab's own controls are built by ``grid_stage.py``
and ``participants_stage.py`` into the panels made here.

One route, ``/build/grid``. The tab last used is remembered in the browser (so a
saved change, which reloads the page, stays on its tab); a link can open a tab
with ``?tab=participants``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from nicegui import app, ui

from src_thesis.platform.services.container import Services
from src_thesis.platform.services.models import ExperimentFile, NetworkSource
from src_thesis.platform.studio.components.network import DEFAULT_SOURCE
from src_thesis.platform.studio.layout import shell
from src_thesis.platform.studio.pages.network.grid_stage import build_grid_stage
from src_thesis.platform.studio.pages.network.participants_stage import (
    build_participants_stage,
)
from src_thesis.platform.studio.pages.network.view import (
    GRID,
    PARTICIPANTS,
    NetworkView,
)
from src_thesis.platform.studio.state import current_draft, draft_network, services

STORAGE_KEY = "network_tab"
STAGES = {GRID: "1 · Grid", PARTICIPANTS: "2 · Participants"}
STAGE_HINTS = {
    GRID: "Choose the network and look at it: its elements, a power-flow preview "
    "and the rules the experiment applies to it.",
    PARTICIPANTS: "Put the agents on the network: which buses, which elements they "
    "own, their profiles and batteries, and the days the experiment covers.",
}


@dataclass
class Context:
    """What the two stages share.

    Attributes:
        s: The services.
        draft: The experiment file being edited.
        draft_source: The network saved in the draft.
        view: The shared plot.
        stage: The stage shown.
        picked: The network picked in stage 1 (saved or not).
        switch: Move to a stage.
        hooks: Called with the stage name whenever the stage changes.
    """

    s: Services
    draft: ExperimentFile
    draft_source: NetworkSource
    view: NetworkView
    stage: str
    picked: Callable[[], NetworkSource]
    switch: Callable[[str], None] = lambda stage: None
    hooks: list[Callable[[str], None]] = field(default_factory=list)


@ui.page("/build/grid")
def network_page(tab: str | None = None) -> None:
    """Grid & Participants: one page, two tabs.

    Args:
        tab: ``"grid"`` or ``"participants"``, from a link that points at one tab
            (e.g. a Validate finding). Without it the tab last used in this browser
            opens.
    """
    stage = tab if tab in STAGES else app.storage.user.get(STORAGE_KEY, GRID)
    _render(stage if stage in STAGES else GRID)


def _render(stage: str) -> None:
    s = services()
    draft = current_draft()
    draft_source = draft_network(draft, DEFAULT_SOURCE)
    with shell(
        "grid",
        "Grid & Participants",
        "Pick the network, then place the participants on it",
    ):
        view = NetworkView(
            s,
            draft_source,
            participants={p.id: p.bus for p in draft.participants if p.bus},
            stage=stage,
        )
        ctx = Context(s, draft, draft_source, view, stage, lambda: draft_source)

        # The tab bar and its panels, as on the Inspect page. The plot is shared, so
        # it sits outside the panels; two groups of panels (beside the plot and
        # below it) follow the same tabs. keep_alive=False: a hidden panel is drawn
        # again when its tab opens, so its Plotly charts are never resized while
        # invisible.
        with ui.tabs(value=stage).props("align=left no-caps").classes("w-full") as tabs:
            ui.tab(GRID, label="1 · Grid", icon="hub")
            ui.tab(PARTICIPANTS, label="2 · Participants", icon="groups")
        stage_hint = ui.label(STAGE_HINTS[stage]).classes("mls-card-caption")

        panels = {"side": {}, "below": {}}
        with ui.row().classes("w-full gap-4 items-start no-wrap"):
            with ui.column().classes("basis-2/5 min-w-[360px]"):
                with ui.tab_panels(tabs, value=stage, keep_alive=False).classes(
                    "w-full bg-transparent"
                ):
                    for key in STAGES:
                        panels["side"][key] = ui.tab_panel(key).classes("p-0 gap-4")
            with ui.column().classes("grow min-w-0 mls-card gap-2"):
                ui.label("Network").classes("mls-card-title")
                view.build()
        with ui.tab_panels(tabs, value=stage, keep_alive=False).classes(
            "w-full bg-transparent"
        ):
            for key in STAGES:
                panels["below"][key] = ui.tab_panel(key).classes("p-0 gap-4")

        def changed(key: str) -> None:
            """A tab was opened: the plot, the hint and the stage's hooks follow."""
            if key == ctx.stage:
                return
            ctx.stage = key
            app.storage.user[STORAGE_KEY] = key
            stage_hint.set_text(STAGE_HINTS[key])
            view.set_stage(key)
            for hook in ctx.hooks:
                hook(key)

        ctx.switch = tabs.set_value
        tabs.on_value_change(lambda e: changed(e.value))
        build_grid_stage(ctx, panels["side"][GRID], panels["below"][GRID])
        build_participants_stage(
            ctx, panels["side"][PARTICIPANTS], panels["below"][PARTICIPANTS]
        )
        for hook in ctx.hooks:
            hook(stage)
