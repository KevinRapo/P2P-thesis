"""One run's test days step by step, shared by the Market and Grid tabs: which run, day
and policy, optionally a second run drawn dotted over it, and the charts the tab asks
for (``heldout_steps.csv``, ``heldout_agent_steps.csv``).
"""

from __future__ import annotations

from typing import Callable, Collection, Optional, Sequence, Union

import pandas as pd
from nicegui import run, ui

from studio.adapters.results_service import ResultsService
from studio.components.charts import SeriesChart
from studio.pages.results.common import POLICIES, Selection, by_number, has
from studio.theme import SERIES

ALL_DAYS = "all"  # the day selector's entry for the mean over the test days
SHARE_PARTS = ["p2p_kwh", "sold_to_dso_kwh", "bought_from_dso_kwh"]


def with_peer_share(rows: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """``rows`` (a step table) with ``peer_share``, the peer energy over all the energy
    traded, when it has the amounts."""
    if rows is None or not set(SHARE_PARTS) <= set(rows):
        return rows

    total = rows[SHARE_PARTS].sum(axis=1)

    return rows.assign(peer_share=rows.p2p_kwh / total.where(total > 0))


def mean_over_days(rows: pd.DataFrame) -> pd.DataFrame:
    """Each step's mean over the days of ``rows``."""
    return rows.groupby("step").mean(numeric_only=True).reset_index()


class StepChart(SeriesChart):
    """Some columns over the steps of a day, a colour per column. Options: ``rows``
    (the selected run's), ``other`` (the second run's, or None), ``columns``,
    ``title`` (the y axis), ``kind``: ``"line"`` (held over each step; the second run
    dotted) or ``"bars"`` (a bar per step: counts and amounts of a step; the second
    run's bar beside it, paler)."""

    height = 260
    x_title = "step"

    def draw(self) -> None:
        self.titles(y=self.o.title)
        bars = self.o.get("kind") == "bars"

        for i, column in enumerate(c for c in self.o.columns if has(self.o.rows, c)):
            color = SERIES[i % len(SERIES)]
            rows, other = self.o.rows, self.o.other
            name = f"{column} (compared)"

            if bars:
                self.bars(rows.step, rows[column], column, color)
            else:
                self.line(rows.step, rows[column], column, color, shape="hv")

            if not has(other, column):
                continue

            if bars:
                self.bars(other.step, other[column], name, color, opacity=0.45)
            else:
                self.line(other.step, other[column], name, color, "dot", "hv")


class StepView:
    """The selectors and the charts under them.

    Args:
        service: The Results service.
        labels: The ticked runs, key -> name.
        selection: What the tabs share.
        charts: ``(title, columns)`` from the step table, with ``"bars"`` as a third
            item for a bar per step (``StepChart``), or a function of the
            run's rows, the compared run's (or None) and the run's key that returns
            a chart, for a chart of its own kind.
        person_charts: The same from a participant's rows; with them a participant
            selector appears.
        details: What goes under the charts, given the participant's rows; not for
            the mean over the days.
    """

    def __init__(
        self,
        service: ResultsService,
        labels: dict[str, str],
        selection: Selection,
        charts: Sequence[Union[tuple, Callable[..., SeriesChart]]],
        person_charts: Sequence[tuple[str, list[str]]] = (),
        details: Optional[Callable[[pd.DataFrame], None]] = None,
    ) -> None:
        self.service = service
        self.selection = selection
        self.charts, self.person_charts = charts, person_charts
        self.details = details
        self._drawn = 0  # the latest draw: an older one that wakes up later stops
        first = selection.run if selection.run in labels else next(iter(labels))

        # Selector row: run | compared with | day | policy
        with ui.row().classes("w-full items-center gap-3"):
            self.run = ui.select(labels, value=first, label="Run").classes("w-96")
            self.other = ui.select(
                {"": "Nothing"} | labels, value="", label="Compare with"
            ).classes("w-96")
            self.day = ui.select([], label="Day").classes("w-40")
            self.policy = ui.select(
                POLICIES,
                value=selection.policy,
                label="Policy",
            ).classes("w-40")

        # The community's charts, then the participant picker over the participant's
        # charts (both boxes redrawn by draw)
        self.box = ui.column().classes("w-full gap-2")
        self.agent = ui.select([], label="Participant").props("use-input")
        self.agent.classes("w-64").set_visibility(bool(person_charts))
        self.person_box = ui.column().classes("w-full gap-2")

        for field in (self.run, self.other, self.day, self.policy, self.agent):
            field.on_value_change(self.draw)

        ui.timer(0.01, self.draw, once=True)

    async def _rows(self, key: str, table: str) -> Optional[pd.DataFrame]:
        return await run.io_bound(self.service.table, key, table)

    def _pick(self, field: ui.select, options: Collection, wanted=None) -> None:
        """Offer ``options`` (a list, or value -> name), keeping the choice when it is
        one of them; a new choice draws again."""
        kept = field.value if field.value in options else wanted
        kept = kept if kept in options else next(iter(options))
        field.set_options(options, value=kept)

    async def draw(self) -> None:
        self._drawn += 1
        drawn = self._drawn
        self.selection.run, self.selection.policy = self.run.value, self.policy.value
        steps = await self._rows(self.run.value, "heldout_steps")

        if drawn != self._drawn:
            return

        if steps is None:
            self.box.clear()
            self.person_box.clear()

            with self.box:
                ui.label("Not recorded: a run from before the step tables.").classes(
                    "mls-card-caption"
                )
            return

        days = sorted(steps.day.unique())
        wanted = self.selection.day if self.selection.day in days else days[0]
        self._pick(self.day, {ALL_DAYS: "All days"} | dict(zip(days, days)), wanted)
        day, policy = self.day.value, self.policy.value

        if day != ALL_DAYS:
            self.selection.day = day

        one = self._of_day(steps, day, policy)
        other = None

        if self.other.value:
            rows = await self._rows(self.other.value, "heldout_steps")

            if rows is not None:
                other = self._of_day(rows, day, policy)

        people = await self._rows(self.run.value, "heldout_agent_steps")

        if drawn != self._drawn:
            return

        if self.person_charts and people is not None:
            groups = self.service.participant_groups(self.run.value)
            names = sorted(people.agent.unique(), key=by_number)
            self._pick(
                self.agent,
                {a: f"{a} ({groups[a]})" if a in groups else a for a in names},
                self.selection.agent,
            )
            self.selection.agent = self.agent.value

        self.box.clear()
        self.person_box.clear()

        with self.box:
            if self.person_charts and people is not None:
                ui.label("The whole community").classes(
                    "text-body2 text-weight-medium"
                )

            for chart in self.charts:
                if callable(chart):
                    chart(one, other, self.run.value).show()
                else:
                    title, columns, *kind = chart
                    StepChart(
                        rows=one,
                        other=other,
                        columns=columns,
                        title=title,
                        kind=kind[0] if kind else "line",
                    ).show()

        with self.person_box:
            if self.person_charts and people is not None:
                person = self._of_day(
                    people[people.agent == self.agent.value], day, policy
                )

                for title, columns in self.person_charts:
                    StepChart(
                        rows=person, other=None, columns=columns, title=title
                    ).show()

                if self.details and day != ALL_DAYS:
                    self.details(person)

    @staticmethod
    def _of_day(rows: pd.DataFrame, day: str, policy: str) -> pd.DataFrame:
        """The ``policy``'s rows of ``day``, or each step's mean over the days; a step
        table with its ``peer_share``, over the days the ratio of their sums."""
        rows = rows[rows.policy == policy]

        if day == ALL_DAYS:
            return with_peer_share(mean_over_days(rows))

        return with_peer_share(rows[rows.day == day])
