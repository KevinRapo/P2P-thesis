"""Grid and participants: one page, two stages, one plot.

Stage 1 picks the network, shows its parameters and sets the grid rules; stage 2
places the participants on the same plot and sets the time window. Both stages
draw on the one ``NetworkView``; each stage's own controls are built by
``grid_stage.py`` and ``participants_stage.py`` into the slots made here.

Routes: ``/build/grid`` opens stage 1, ``/build/participants`` stage 2 (so a
saved change, which reloads the page, stays on its stage).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from nicegui import ui

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

ROUTES = {GRID: "/build/grid", PARTICIPANTS: "/build/participants"}
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
def grid_page() -> None:
    """Stage 1: the network."""
    _render(GRID)


@ui.page("/build/participants")
def participants_page() -> None:
    """Stage 2: the participants."""
    _render(PARTICIPANTS)


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

        toggle = ui.toggle(STAGES, value=stage).props("no-caps unelevated")
        stage_hint = ui.label(STAGE_HINTS[stage]).classes("mls-card-caption")

        with ui.row().classes("w-full gap-4 items-start no-wrap"):
            with ui.column().classes("basis-2/5 min-w-[360px] gap-4"):
                side = {k: ui.column().classes("w-full gap-4") for k in STAGES}
            with ui.column().classes("grow min-w-0 mls-card gap-2"):
                ui.label("Network").classes("mls-card-title")
                view.build()
        below = {k: ui.column().classes("w-full gap-4") for k in STAGES}

        def show(key: str) -> None:
            for k in STAGES:
                side[k].set_visibility(k == key)
                below[k].set_visibility(k == key)
            stage_hint.set_text(STAGE_HINTS[key])

        def switch(key: str) -> None:
            if key == ctx.stage:
                return
            ctx.stage = key
            if toggle.value != key:
                toggle.set_value(key)
            show(key)
            view.set_stage(key)
            ui.run_javascript(f"history.replaceState(null, '', '{ROUTES[key]}')")
            for hook in ctx.hooks:
                hook(key)

        ctx.switch = switch
        toggle.on_value_change(lambda e: switch(e.value))
        build_grid_stage(ctx, side[GRID], below[GRID])
        build_participants_stage(ctx, side[PARTICIPANTS], below[PARTICIPANTS])
        show(stage)
        for hook in ctx.hooks:
            hook(stage)
