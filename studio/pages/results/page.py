"""Results: the runs ticked in the table, in five tabs, live while they train.

    Learning     did it learn? the learner over environment steps
    Validation   is the policy any good? against the baselines, during training and
                 on the test days, over the seeds
    Market       what did the market do? its amounts per day, per participant, and
                 one run in depth
    Grid         what did the grid do? the power flow's amounts per day
    Explore      any recorded number, with every control

The runs are those of this PC and of each cluster's mirror, read from their
folders (``core/runner/results.py``, the notebook ``notebooks/runner/results.ipynb``
reads the same). Only the open tab is built. With *Live* on, at once and then
every 10 s, each cluster is asked which of its experiments have runs queued or
running, and the mirror of each is brought up to date (``Target.follow``: only
what training wrote since; an experiment new here appears in the table); the runs
are read again (an unchanged file is not) and the open tab's charts redraw in
place. A finished experiment not followed while it ran: Sync results on the Runs
page.
"""

from __future__ import annotations

import time

from nicegui import run, ui

from core.runner.results import LOCAL
from studio.adapters.results_service import ResultsService
from studio.adapters.run_service import RunService
from studio.components.cards import placeholder
from studio.components.run_table import RunTable
from studio.layout import shell
from studio.pages.results.common import Tab
from studio.pages.results.explore import ExploreTab
from studio.pages.results.grid import GridTab
from studio.pages.results.learning import LearningTab
from studio.pages.results.market import MarketTab
from studio.pages.results.validation import ValidationTab
from studio.state import services

SHOW_TESTS = "results_show_tests"  # app.storage.user key
LIVE_S = 10  # seconds between live refreshes
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
        self.tabs: dict[str, Tab] = {
            tab.label: tab(service)
            for tab in (LearningTab, ValidationTab, MarketTab, GridTab, ExploreTab)
        }
        self._drawn = 0  # the latest draw: an older one that finishes later stops
        self._ticking = False

        # The run table at the top, with a tick box per run
        self.table = RunTable(service, self.show, SHOW_TESTS)

        # Live row: switch | when it last read the runs
        with ui.row().classes("w-full items-center gap-3"):
            self.live = ui.switch(
                f"Live (every {LIVE_S} s)",
                on_change=lambda e: self.tick() if e.value else None,
            )
            self.note = ui.label().classes("mls-card-caption")

        # Tab bar; only the open tab is built, into the box under it
        with ui.tabs(value="Validation").props("align=left no-caps").classes(
            "w-full"
        ) as self.bar:
            for label, tab in self.tabs.items():
                ui.tab(label, icon=tab.icon)

        self.bar.on_value_change(lambda _: self.show())
        self.box = ui.column().classes("w-full gap-4")
        ui.timer(LIVE_S, self.tick)

    @property
    def tab(self) -> Tab:
        return self.tabs[self.bar.value]

    async def load(self) -> None:
        await self.table.load()
        await self.show()

    async def show(self) -> None:
        """Build the open tab for the ticked runs (after a tick or a tab change)."""
        keys, tab = list(self.table.selected), self.tab
        self._drawn += 1
        drawn = self._drawn
        self.box.clear()

        with self.box:
            if not keys:
                placeholder("Tick runs in the table to see their results.", "checklist")
                return

            ui.label("Reading the runs …").classes("mls-card-caption")

        data = await run.io_bound(tab.read, keys)

        if drawn != self._drawn:  # ticked again, or another tab, meanwhile
            return

        self.box.clear()
        tab.watched = []

        with self.box:
            tab.build(keys, data)

    async def tick(self) -> None:
        """One live refresh: follow the active cluster experiments, read the runs
        again, redraw the open tab's charts."""
        if not self.live.value or self._ticking:
            return

        self._ticking = True

        try:
            keys = list(self.table.selected)
            followed = await self._follow()
            self.service.refresh()
            await self.table.load()
            tab = self.tab

            if keys and tab.watched:
                tab.update(await run.io_bound(tab.read, keys))

            self.note.set_text(
                f"Read at {time.strftime('%H:%M:%S')}"
                + (f" · following {', '.join(followed)}" if followed else "")
            )
        except Exception as error:  # noqa: BLE001  show it, try again next time
            self.note.set_text(f"Live refresh failed: {error}")
        finally:
            self._ticking = False

    async def _follow(self) -> list[str]:
        """Ask each cluster which experiments have runs queued or running, and
        bring the mirror of each up to date (it appears here if it is new); returns
        ``target/experiment`` of each."""
        followed = []

        for target, _ in self.runs.target_names():
            if target == LOCAL:
                continue

            for entry in await run.io_bound(self.runs.overview, target, 0):
                if any(r.state in ACTIVE for r in entry["runs"]):
                    await run.io_bound(self.runs.follow, target, entry["name"])
                    followed.append(f"{target}/{entry['name']}")

        return followed


def page() -> None:
    """The runs, read when the page opens."""
    s = services()

    with shell(
        "results",
        "Results",
        "The ticked runs, of this PC and of the clusters. Live follows the "
        "experiments training on a cluster and reads the runs again every 10 s.",
    ):
        view = ResultsView(s.results, s.runs)
        ui.timer(0.05, view.load, once=True)
