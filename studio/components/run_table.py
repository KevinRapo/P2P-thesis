"""The table of runs to tick: the Results and RL probes pages.

Every run of this PC and of each cluster after *Sync results* on the Runs page
(``ResultsService.overview``). Showing and ticking are separate:

- what is shown: the targets, the folders inside them (at every level; a folder
  includes those under it) and the experiments (each one or more, all when none,
  each offering what the one before it leaves), the text filter, test-profile runs
  (``<name>--test``) or not, and *Ticked only*;
- what is ticked: each run by its box, *Tick shown* (every run the table shows now,
  on every page of it) and *Untick all*.

A ticked run stays ticked when a filter hides it, so runs of several experiments
can be compared. Nothing is read again until Refresh. The ticks and the filters are
remembered (``memory.py``) once the runs are read: the filters' options and which
ticks still exist depend on them.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

import pandas as pd
from nicegui import run, ui

from studio.adapters.results_service import ResultsService
from studio.components.choices import checkboxes
from studio.components.memory import keep, recalled, remember
from studio.components.tables import data_table

RUN_COLUMNS = [
    ("target", "Target"),
    ("experiment", "Experiment"),
    ("run", "Run"),
    ("algorithm", "Algorithm"),
    ("paradigm", "Paradigm"),
    ("seed", "Seed"),
    ("variant", "Variant"),
    ("state", "State"),
    ("started", "Started"),
    ("money_trained", "Held-out money: trained"),
    ("money_zero", "zero"),
    ("money_net_position", "net position"),
]
TOP_LEVEL = "(top level)"  # the Folder option of experiments in no folder


def folder_of(experiments: pd.Series) -> pd.Series:
    """The folder of each experiment name (``<folder>/<experiment>``), else empty."""
    return experiments.str.rpartition("/")[0]


def with_parents(folder: str) -> list[str]:
    """A folder and the folders above it: ``a/b`` gives ``a`` and ``a/b``."""
    parts = folder.split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def offer(choice: ui.select, options: list | dict) -> None:
    """Give a multiple select new options, dropping what it no longer offers."""
    chosen = choice.value or []
    kept = [value for value in chosen if value in options]
    choice.set_options(options)

    if kept != chosen:
        choice.set_value(kept)


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
        memory: The first part of what this table's choices are kept under.
        columns: ``(field, label)`` of the overview to show.
        read: The overview to show (default ``service.overview``).
        kind: Only runs of this kind (``results.run_kind``: ``"market"`` or
            ``"probe"``), and those whose kind nothing says yet; all without.
    """

    def __init__(
        self,
        service: ResultsService,
        on_change: Callable[[], Awaitable[None]],
        memory: str,
        columns: list[tuple[str, str]] = RUN_COLUMNS,
        read: Optional[Callable[[], pd.DataFrame]] = None,
        kind: Optional[str] = None,
    ) -> None:
        self.service = service
        self.on_change = on_change
        self.memory = memory
        self._restored = False
        self.columns = columns
        self.read = read or service.overview
        self.kind = kind
        self.overview = pd.DataFrame()
        self.selected: list[str] = []

        # Filter row: Refresh | targets | folders | experiments | search | Show test runs
        with ui.row().classes("w-full items-center gap-3"):
            ui.button("Refresh", icon="refresh", on_click=self.refresh).props(
                "flat no-caps dense"
            )
            self.target = (
                checkboxes(
                    ui.select(
                        [],
                        label="Targets",
                        on_change=lambda _: self._fill(),
                        multiple=True,
                        clearable=True,
                        value=[],
                    )
                )
                .style("min-width: 140px")
            )
            self.folder = (
                checkboxes(
                    ui.select(
                        [],
                        label="Folders",
                        on_change=lambda _: self._fill(),
                        multiple=True,
                        clearable=True,
                        value=[],
                    )
                )
                .style("min-width: 140px")
            )
            self.experiment = (
                checkboxes(
                    ui.select(
                        [],
                        label="Experiments (one or more; all when empty)",
                        on_change=lambda _: self._fill(),
                        multiple=True,
                        clearable=True,
                        value=[],
                    )
                )
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
                value=recalled(f"{memory}_show_tests", True),
                on_change=self._tests_changed,
            )

        # Ticking row: Tick shown | Untick all | Ticked only
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
        self.runs = data_table(
            [], columns, row_key="key", selection="multiple", on_select=self._selected, pagination=20
        )

    async def load(self) -> None:
        """Read the runs (once; ``refresh`` reads them again) and fill the table."""
        self.note.set_text("Reading the runs ...")
        overview = await run.io_bound(self.read)

        if overview is None:  # the page closed or the server stopped during the read
            return

        self.overview = overview
        self._restore()
        self._fill()

    def _restore(self) -> None:
        """Bring back the ticks and the filters, once, after the first read: a filter
        changed before it would find no runs and drop them all."""
        if self._restored:
            return

        self._restored = True
        self.selected = list(recalled(f"{self.memory}_ticked", []))

        for control, name in (
            (self.target, "targets"),
            (self.folder, "folders"),
            (self.experiment, "experiments"),
            (self.search, "search"),
            (self.only_ticked, "ticked_only"),
        ):
            remember(control, f"{self.memory}_{name}")

    async def refresh(self) -> None:
        """Read every run again, and draw from what is read now."""
        self.service.refresh()
        await self.load()
        await self._selected()

    def _offered(self) -> pd.DataFrame:
        """Every run that can be ticked: those of the table's kind (all without),
        all of them or all but the test runs."""
        table = self.overview

        if table.empty:
            return table

        if self.kind and "kind" in table:
            table = table[(table.kind == self.kind) | table.kind.isna()]

        return table if self.show_tests.value else table[~table.test]

    def _of_targets(self, table: pd.DataFrame) -> pd.DataFrame:
        if table.empty or not self.target.value:
            return table

        return table[table.target.isin(self.target.value)]

    def _of_folders(self, table: pd.DataFrame) -> pd.DataFrame:
        if table.empty or not self.folder.value:
            return table

        chosen = set(self.folder.value)
        folders = folder_of(table.experiment)

        return table[folders.map(lambda f: bool(chosen & set(with_parents(f))))]

    def visible(self) -> pd.DataFrame:
        """The runs the table shows: those offered, narrowed to the chosen targets,
        folders and experiments, to the filter text (in any column shown) and, with
        *Ticked only*, to the ticked runs."""
        table = self._of_folders(self._of_targets(self._offered()))

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

    def _offer_choices(self, offered: pd.DataFrame) -> None:
        """Each select offers what the one before it leaves: targets, then their
        folders, then those folders' experiments."""
        offer(self.target, sorted(set(offered.target)) if len(offered) else [])
        table = self._of_targets(offered)
        folders = set(folder_of(table.experiment)) if len(table) else set()
        folders = sorted({up for folder in folders for up in with_parents(folder)})
        offer(self.folder, {folder: folder or TOP_LEVEL for folder in folders})
        table = self._of_folders(table)
        experiments = (
            sorted({f"{t}/{e}" for t, e in zip(table.target, table.experiment)})
            if len(table)
            else []
        )
        offer(self.experiment, experiments)

    def _fill(self) -> None:
        offered = self._offered()
        keys = set(offered.key) if len(offered) else set()
        self.selected = [k for k in self.selected if k in keys]

        if len(self.overview):  # with no runs read, the ticks kept stay
            keep(f"{self.memory}_ticked", list(self.selected))

        self._offer_choices(offered)
        table = self.visible()
        self.runs.rows = [
            {"key": row["key"]} | {f: cell(row.get(f)) for f, _ in self.columns}
            for row in table.to_dict("records")
        ]
        self.runs.selected = [r for r in self.runs.rows if r["key"] in self.selected]
        self.runs.update()
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
        keep(f"{self.memory}_show_tests", bool(self.show_tests.value))
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
