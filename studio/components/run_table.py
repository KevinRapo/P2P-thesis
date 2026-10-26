"""The table of runs to tick: the Results and RL probes pages.

Every run of this PC and of each cluster after *Sync results* on the Runs page
(``ResultsService.overview``). Showing and ticking are separate:

- what is shown: one or more experiments (all when none), the text filter, test-profile runs
  (``<name>--test``) or not, and *Ticked only*;
- what is ticked: each run by its box, *Tick shown* (every run the table shows now,
  on every page of it) and *Untick all*.

A ticked run stays ticked when a filter hides it, so runs of several experiments
can be compared. Nothing is read again until Refresh.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

import pandas as pd
from nicegui import app, run, ui

from studio.adapters.results_service import ResultsService

RUN_COLUMNS = [
    ("target", "Target"),
    ("experiment", "Experiment"),
    ("run", "Run"),
    ("algorithm", "Algorithm"),
    ("paradigm", "Paradigm"),
    ("seed", "Seed"),
    ("variant", "Variant"),
    ("state", "State"),
    ("heldout_trained", "Held-out: trained"),
    ("heldout_zero", "zero"),
    ("heldout_net_position", "net position"),
]


def labels_of(keys: list[str]) -> dict[str, str]:
    """A label per run key: ``experiment/run``, and ``target/experiment/run`` when
    the runs come from more than one target (so two targets' runs stay apart)."""
    targets = {key.split("/", 1)[0] for key in keys}
    return {key: key if len(targets) > 1 else key.split("/", 1)[1] for key in keys}


def cell(value: Any) -> Any:
    """A value as a table cell shows it: rounded, and empty for missing."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    if isinstance(value, float):
        return round(value, 3)

    if isinstance(value, list):
        return ", ".join(map(str, value))

    if isinstance(value, dict):
        return ", ".join(f"{k}: {cell(v)}" for k, v in value.items())

    return value


class RunTable:
    """The controls and the table of runs; ``on_change`` is awaited whenever the
    ticked runs change or the runs are read again.

    Args:
        service: The Results service.
        on_change: Called without arguments; it reads ``selected``.
        storage_key: ``app.storage.user`` key of the *Show test runs* switch.
        columns: ``(field, label)`` of the overview to show.
        read: The overview to show (default ``service.overview``).
    """

    def __init__(
        self,
        service: ResultsService,
        on_change: Callable[[], Awaitable[None]],
        storage_key: str,
        columns: list[tuple[str, str]] = RUN_COLUMNS,
        read: Optional[Callable[[], pd.DataFrame]] = None,
    ) -> None:
        self.service = service
        self.on_change = on_change
        self.storage_key = storage_key
        self.columns = columns
        self.read = read or service.overview
        self.overview = pd.DataFrame()
        self.selected: list[str] = []

        with ui.row().classes("w-full items-center gap-3"):
            ui.button("Refresh", icon="refresh", on_click=self.refresh).props(
                "flat no-caps dense"
            )
            self.experiment = (
                ui.select(
                    [],
                    label="Experiments (one or more; all when empty)",
                    on_change=lambda _: self._fill(),
                    multiple=True,
                    clearable=True,
                    value=[],
                )
                .props("use-chips")
                .classes("grow")
                .style("min-width: 260px")
            )
            self.search = (
                ui.input(placeholder="Filter runs", on_change=lambda _: self._fill())
                .props("dense clearable")
                .style("min-width: 200px")
            )
            self.show_tests = ui.switch(
                "Show test runs",
                value=app.storage.user.get(storage_key, True),
                on_change=self._tests_changed,
            )

        with ui.row().classes("w-full items-center gap-3"):
            ui.button("Tick shown", icon="done_all", on_click=self.tick_shown).props(
                "flat no-caps dense"
            ).tooltip("Tick every run the table shows now, on every page")
            ui.button("Untick all", icon="deselect", on_click=self.untick_all).props(
                "flat no-caps dense"
            ).tooltip("Untick every run, also those a filter hides")
            self.only_ticked = ui.switch(
                "Ticked only", on_change=lambda _: self._fill()
            )

        self.note = ui.label().classes("mls-card-caption")
        self.runs = (
            ui.table(
                columns=[
                    {"name": f, "label": label, "field": f, "sortable": True}
                    | {"align": "left"}
                    for f, label in columns
                ],
                rows=[],
                row_key="key",
                selection="multiple",
                pagination={"rowsPerPage": 10},
                on_select=self._selected,
            )
            .classes("w-full")
            .props("flat dense")
        )

    async def load(self) -> None:
        """Read the runs (once; ``refresh`` reads them again) and fill the table."""
        self.note.set_text("Reading the runs ...")
        self.overview = await run.io_bound(self.read)
        self._fill()

    async def refresh(self) -> None:
        """Read every run again, and draw from what is read now."""
        self.service.refresh()
        await self.load()
        await self._selected()

    def _offered(self) -> pd.DataFrame:
        """Every run that can be ticked: all, or all but the test runs."""
        table = self.overview
        if table.empty or self.show_tests.value:
            return table
        return table[~table.test]

    def visible(self) -> pd.DataFrame:
        """The runs the table shows: those offered, narrowed to the chosen
        experiments, to the filter text (in any column shown) and, with *Ticked
        only*, to the ticked runs."""
        table = self._offered()

        if table.empty:
            return table

        if self.experiment.value:
            folders = table.target + "/" + table.experiment
            table = table[folders.isin(self.experiment.value)]

        text = (self.search.value or "").strip().lower()

        if text:
            fields = [f for f, _ in self.columns if f in table]
            found = (
                table[fields]
                .astype(str)
                .apply(lambda row: text in " ".join(row).lower(), axis=1)
            )
            table = table[found]

        if self.only_ticked.value:
            table = table[table.key.isin(self.selected)]

        return table

    def _fill(self) -> None:
        offered = self._offered()
        keys = set(offered.key) if len(offered) else set()
        self.selected = [k for k in self.selected if k in keys]
        table = self.visible()
        self.runs.rows = [
            {"key": row["key"]} | {f: cell(row.get(f)) for f, _ in self.columns}
            for _, row in table.iterrows()
        ]
        self.runs.selected = [r for r in self.runs.rows if r["key"] in self.selected]
        self.runs.update()
        experiments = (
            sorted({f"{t}/{e}" for t, e in zip(offered.target, offered.experiment)})
            if len(offered)
            else []
        )
        self.experiment.set_options(experiments)
        text = f"{len(table)} of {len(offered)} runs shown"
        text += f" · {len(self.selected)} ticked"
        out_of_view = len(set(self.selected) - set(table.key if len(table) else []))

        if out_of_view:
            text += f", {out_of_view} of them hidden by the filters"
        hidden = len(self.overview) - len(offered)

        if hidden:
            text += f" ({hidden} test runs hidden)"

        if not len(self.overview):
            text = (
                "No runs yet. Runs on this PC appear here when they have files; a "
                "cluster's after Sync results on the Runs page."
            )

        self.note.set_text(text)

    async def _tests_changed(self) -> None:
        app.storage.user[self.storage_key] = bool(self.show_tests.value)
        self._fill()
        await self._selected()

    async def tick_shown(self) -> None:
        """Tick every run the table shows now (added to the ticks)."""
        shown = list(self.visible().get("key", []))
        self.selected += [k for k in shown if k not in self.selected]
        self._fill()
        await self.on_change()

    async def untick_all(self) -> None:
        """Untick every run; what is shown stays as it is."""
        self.selected = []
        self._fill()
        await self.on_change()

    async def _selected(self, _: Any = None) -> None:
        """A box ticked or unticked in the table (or the runs read again): the
        table's ticks replace those of the rows it shows; ticks of hidden rows
        stay."""
        shown = {row["key"] for row in self.runs.rows}
        ticked = [row["key"] for row in self.runs.selected]
        self.selected = [k for k in self.selected if k not in shown]
        self.selected += [k for k in ticked if k not in self.selected]
        self._fill()  # the count, and with *Ticked only* the rows unticked just now
        await self.on_change()
