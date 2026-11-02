"""One run's test days step by step, shared by the Market and Grid tabs: which run, day
and policy, optionally a second run drawn dotted over it, and the charts the tab asks
for (``heldout_steps.csv``, ``heldout_agent_steps.csv``).
"""

from __future__ import annotations

from typing import Callable, Collection, Optional, Sequence

import pandas as pd
from nicegui import run, ui

from studio.adapters.results_service import ResultsService
from studio.components.charts import SeriesChart
from studio.pages.results.common import POLICIES, Selection, by_number
from studio.theme import SERIES


class StepChart(SeriesChart):
    """Some columns over the steps of a day, a colour per column. Options: ``rows``
    (the selected run's), ``other`` (the second run's, dotted, or None), ``columns``,
    ``title`` (the y axis)."""

    height = 260
    x_title = "step"

    def draw(self) -> None:
        self.titles(y=self.o.title)

        for i, column in enumerate(c for c in self.o.columns if c in self.o.rows):
            color = SERIES[i % len(SERIES)]
            rows = self.o.rows
            self.line(rows.step, rows[column], column, color, shape="hv")

            if self.o.other is not None and column in self.o.other:
                other = self.o.other
                name = f"{column} (compared)"
                self.line(other.step, other[column], name, color, "dot", "hv")


class StepView:
    """The selectors and the charts under them.

    Args:
        service: The Results service.
        labels: The ticked runs, key -> name.
        selection: What the tabs share.
        charts: ``(title, columns)`` from the step table.
        person_charts: The same from a participant's rows; with them a participant
            selector appears.
        details: What goes under the charts, given the participant's rows.
    """

    def __init__(
        self,
        service: ResultsService,
        labels: dict[str, str],
        selection: Selection,
        charts: Sequence[tuple[str, list[str]]],
        person_charts: Sequence[tuple[str, list[str]]] = (),
        details: Optional[Callable[[pd.DataFrame], None]] = None,
    ) -> None:
        self.service = service
        self.selection = selection
        self.charts, self.person_charts = charts, person_charts
        self.details = details
        self._drawn = 0  # the latest draw: an older one that wakes up later stops
        first = selection.run if selection.run in labels else next(iter(labels))

        # Selector row: run | compared with | day | policy | participant
        with ui.row().classes("w-full items-center gap-3"):
            self.run = ui.select(labels, value=first, label="Run").classes("w-96")
            self.other = ui.select(
                {"": "Nothing"} | labels, value="", label="Compare with"
            ).classes("w-96")
            self.day = ui.select([], label="Day").classes("w-40")
            self.policy = ui.select(
                POLICIES | {"random": "Random"},
                value=selection.policy,
                label="Policy",
            ).classes("w-40")
            self.agent = ui.select([], label="Participant").props("use-input")
            self.agent.set_visibility(bool(person_charts))

        self.box = ui.column().classes("w-full gap-2")  # the charts, redrawn by draw

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

            with self.box:
                ui.label("Not recorded: a run from before the step tables.").classes(
                    "mls-card-caption"
                )
            return

        self._pick(self.day, sorted(steps.day.unique()), self.selection.day)
        self.selection.day = self.day.value
        day, policy = self.day.value, self.policy.value
        one = steps[(steps.day == day) & (steps.policy == policy)]
        other = None

        if self.other.value:
            rows = await self._rows(self.other.value, "heldout_steps")

            if rows is not None:
                other = rows[(rows.day == day) & (rows.policy == policy)]

        people = await self._rows(self.run.value, "heldout_agent_steps")

        if drawn != self._drawn:
            return

        if self.person_charts and people is not None:
            groups = self.service.participant_groups(self.run.value)
            names = sorted(people.agent.unique(), key=by_number)
            self._pick(
                self.agent,
                {a: f"{a} ({groups[a]})" if a in groups else a for a in names},
            )

        self.box.clear()

        with self.box:
            for title, columns in self.charts:
                StepChart(rows=one, other=other, columns=columns, title=title).show()

            if self.person_charts and people is not None:
                person = people[
                    (people.day == day)
                    & (people.policy == policy)
                    & (people.agent == self.agent.value)
                ]

                for title, columns in self.person_charts:
                    StepChart(
                        rows=person, other=None, columns=columns, title=title
                    ).show()

                if self.details:
                    self.details(person)
