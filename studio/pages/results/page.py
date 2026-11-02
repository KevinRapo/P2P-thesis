"""Results: the runs ticked in the table, in four tabs, live while they train.

    Validation   how good is each version? any runs side by side, on the test days
    Learning     did it learn? training, on the training days
    Market       what did the market do? per test day, per participant, step by step
    Grid         what did the grid do? per test day, step by step

The runs are those of this PC and of each cluster's mirror, read from their
folders (``core/runner/results.py``, the notebook ``notebooks/runner/results.ipynb``
reads the same). Only the open tab is built. With *Live* on, at once and then
every 30 s, each cluster is asked which of its experiments have runs queued or
running, and the mirror of each is brought up to date (``Target.follow``: only
what training wrote since; an experiment new here appears in the table); the runs
of those experiments and of this PC's running ones are read again, once more after
they stop running (every other run stays as read; an unchanged file is not read),
and the open tab's charts redraw in place. *Refresh* above the table reads every
run again. A finished experiment not followed while it ran: Sync results on the
Runs page. The ticks, the filters, the open tab, Live and the tabs' controls are
remembered between visits (``components/memory.py``).
"""

from __future__ import annotations

import time

from nicegui import run, ui

from core.runner.results import LOCAL
from studio.adapters.results_service import ResultsService
from studio.adapters.run_service import RunService
from studio.components.cards import fill, placeholder
from studio.components.memory import remember
from studio.components.run_table import RunTable
from studio.layout import shell
from studio.pages.results.common import Selection, Tab
from studio.pages.results.grid import GridTab
from studio.pages.results.learning import LearningTab
from studio.pages.results.market import MarketTab
from studio.pages.results.validation import ValidationTab
from studio.state import services

LIVE_S = 30  # seconds between live refreshes
ACTIVE = ("queued", "running")  # runs whose experiment the live view follows


class ResultsView:
    """The run table, the live switch, the tab bar and the open tab.

    Args:
        service: The Results service.
        runs: The Runs service (it follows a cluster's experiments).
    """

    def __init__(self, service: ResultsService, runs: RunService) -> None:
        self.service = service
        self.runs = runs
        selection = Selection(open=self._open)
        self.tabs: dict[str, Tab] = {
            tab.label: tab(service, selection)
            for tab in (ValidationTab, LearningTab, MarketTab, GridTab)
        }
        self._drawn = 0  # the latest draw: an older one that finishes later stops
        self._ticking = False
        # What the last live refresh read again: read once more after it stops
        # running, so its last files (final status, held-out tables) arrive too
        self._watched: set[tuple[str, str]] = set()

        # The run table at the top, with a tick box per run: market runs only
        # (the RL probes' are on their own page)
        self.table = RunTable(service, self.show, "results", kind="market")

        # Live row: switch | when it last read the runs
        with ui.row().classes("w-full items-center gap-3"):
            self.live = ui.switch(f"Live (every {LIVE_S} s)")
            remember(self.live, "results_live")
            self.live.on_value_change(lambda e: self.tick() if e.value else None)
            self.note = ui.label().classes("mls-card-caption")

        # Tab bar; only the open tab is built, into the box under it
        with ui.tabs(value="Validation").props("align=left no-caps").classes(
            "w-full"
        ) as self.bar:
            for label, tab in self.tabs.items():
                ui.tab(label, icon=tab.icon)

        remember(self.bar, "results_tab", self.tabs)
        self.bar.on_value_change(lambda _: self.show())
        self.box = ui.column().classes("w-full gap-4")
        ui.timer(LIVE_S, self.tick)

    def _open(self, label: str) -> None:
        self.bar.value = label

    @property
    def tab(self) -> Tab:
        return self.tabs[self.bar.value]

    async def load(self) -> None:
        await self.table.load()
        await self.show()

        if self.live.value:  # remembered on: at once, not after the first wait
            await self.tick()

    async def show(self) -> None:
        """Build the open tab for the ticked runs (after a tick or a tab change)."""
        keys, tab = list(self.table.selected), self.tab
        self._drawn += 1
        drawn = self._drawn

        if not keys:
            self.box.clear()

            with self.box:
                placeholder("Tick runs in the table to see their results.", "checklist")
            return

        def build(data) -> None:
            tab.watched = []
            tab.build(keys, data)

        await fill(
            self.box,
            lambda: tab.read(keys),
            build,
            "Reading the runs …",
            current=lambda: drawn == self._drawn,
        )

    async def tick(self) -> None:
        """One live refresh: follow the active cluster experiments, read the runs
        again, redraw the open tab's charts."""
        if not self.live.value or self._ticking:
            return

        self._ticking = True

        try:
            keys = list(self.table.selected)
            active = await self._follow()
            self.service.refresh(sorted(active | self._watched))
            self._watched = active
            await self.table.load()
            tab = self.tab

            if keys and tab.watched:
                tab.update(await run.io_bound(tab.read, keys))

            self.note.set_text(
                f"Read at {time.strftime('%H:%M:%S')}"
                + (
                    " · following " + ", ".join(f"{t}/{e}" for t, e in sorted(active))
                    if active
                    else ""
                )
            )
        except Exception as error:  # noqa: BLE001  show it, try again next time
            self.note.set_text(f"Live refresh failed: {error}")
        finally:
            self._ticking = False

    async def _follow(self) -> set[tuple[str, str]]:
        """The experiments with runs queued or running, ``(target, experiment)``:
        on this PC those whose worker lives; on each cluster those it reports, each
        mirror brought up to date (it appears here if it is new)."""
        active = set()

        for target, _ in self.runs.target_names():
            for entry in await run.io_bound(self.runs.experiments, target, 0):
                if any(r.state in ACTIVE for r in entry["runs"]):
                    if target != LOCAL:
                        await run.io_bound(
                            self.runs.follow_experiment, target, entry["name"]
                        )
                    active.add((target, entry["name"]))

        return active


def page() -> None:
    """The runs, read when the page opens."""
    s = services()

    with shell(
        "results",
        "Results",
        "The ticked runs, of this PC and of the clusters. Live follows the "
        "experiments training on a cluster and reads the runs again every 30 s.",
    ):
        view = ResultsView(s.results, s.runs)
        ui.timer(0.05, view.load, once=True)
