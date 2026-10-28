"""Results → Market: what did the market do?

Every market amount of the played days (``core/runner/results.day_metrics``):
peer-to-peer energy and its stage-1 (preference) part, energy sold to and bought
from the DSO, the team return; during training (the evaluation days, over
environment steps) and on the held-out test days. Per participant: the same
amounts for each participant (``participant_metrics``). One run: each participant
against a baseline per test day, and with detailed results its traced days step
by step. The charts follow the live view.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from nicegui import run, ui

from studio.adapters.results_service import ResultsService
from studio.components.cards import section
from studio.components.charts import Chart, SeriesChart
from studio.components.run_table import labels_of
from studio.pages.results.common import BASELINES, BY, Tab, metric_card

# The market amounts of the per-day tables, in the order offered.
MARKET_METRICS = [
    "p2p_kwh",
    "preference_kwh",
    "bought_from_dso_kwh",
    "sold_to_dso_kwh",
    "team_return",
]
# The amounts per participant, in the order offered.
PARTICIPANT_METRICS = [
    "return",
    "bill",
    "profit",
    "bought_kwh",
    "sold_kwh",
    "preference_kwh",
    "deferred_demand_kwh",
    "deferred_supply_kwh",
]
# A participant's orders and partner choice in a traced day (``heldout_trace_agents``).
TRACE_COLUMNS = [
    ("step", "Step"),
    ("side", "Side"),
    ("order_kwh", "Order kWh"),
    ("order_price", "Price"),
    ("partner", "Partner"),
    ("partner_mutual", "Mutual"),
    ("preference_kwh", "Stage 1 kWh"),
    ("bought_kwh", "Bought kWh"),
    ("sold_kwh", "Sold kWh"),
    ("reward", "Reward"),
]
# The participant outcomes of ``heldout_agents.csv`` the Participants view offers.
OUTCOMES = {
    "return": "Return",
    "profit": "Profit",
    "bill": "Bill",
    "bought_kwh": "Bought kWh",
    "sold_kwh": "Sold kWh",
    "preference_kwh": "Stage 1 (preference) kWh",
    "deferred_demand_kwh": "Deferred demand kWh",
    "deferred_supply_kwh": "Deferred supply kWh",
}
OUTCOMES = {m: m.replace("_", " ") for m in PARTICIPANT_METRICS}
MOST_PARTICIPANTS = 30  # shown at once; the rest through the filter


# --------------------------------------------------------------------------------------
# One run: participants against a baseline, traced days
# --------------------------------------------------------------------------------------
def shown_participants(
    table: pd.DataFrame, column: str, text: str = "", most: int = MOST_PARTICIPANTS
) -> list[str]:
    """The participants the heatmap shows: those whose name contains ``text`` (all
    without), at most ``most``, the largest mean absolute ``column`` first."""
    sizes = table.groupby("agent")[column].apply(lambda v: v.abs().mean())

    if text:
        sizes = sizes[[text.lower() in str(a).lower() for a in sizes.index]]

    return list(sizes.sort_values(ascending=False).index[:most])


class ParticipantChart(Chart):
    """The ``agents`` × test days: ``column`` (trained minus a baseline), red to
    blue around 0, the largest difference on top. Options: ``table``, ``column``,
    ``agents``, ``title`` (the colour bar's)."""

    layout = {"hovermode": "closest"}

    def draw(self) -> None:
        o = self.o
        grid = o.table[o.table.agent.isin(o.agents)].pivot(
            index="agent", columns="day", values=o.column
        )
        grid = grid.reindex([a for a in o.agents if a in grid.index])
        limit = float(grid.abs().max().max() or 1.0)
        self.height = max(260, 26 * len(grid) + 120)
        self.fig.add_heatmap(
            z=grid.values,
            x=list(grid.columns),
            y=list(grid.index),
            colorscale="RdBu",
            zmin=-limit,
            zmax=limit,
            colorbar=dict(title=o.title),
        )
        self.fig.update_yaxes(autorange="reversed")


class TraceChart(SeriesChart):
    """Lines of some columns over the steps of one traced day. Options: ``steps``
    (the rows of that day), ``columns``, ``title`` (the y axis)."""

    height = 280
    x_title = "step"

    def draw(self) -> None:
        self.titles(y=self.o.title)

        for column in (c for c in self.o.columns if c in self.o.steps):
            self.line(self.o.steps.step, self.o.steps[column], column, markers=True)


class OneRun:
    """One run's participants and traced days (read when the run is picked)."""

    def __init__(self, service: ResultsService) -> None:
        self.service = service

    def participants(self, key: str, people: Optional[pd.DataFrame]) -> None:
        with section(
            "Participants",
            "An outcome of the trained policy minus the same of a baseline, per "
            "participant and test day (blue: higher for the trained policy). A "
            "better team total can hide participants that lose. With many "
            f"participants, the {MOST_PARTICIPANTS} with the largest difference, or "
            "those the filter names.",
            "groups",
        ):
            if people is None:
                ui.label(
                    "Not recorded: a run from before the per-participant tables."
                ).classes("mls-card-caption")
                return

            outcomes = {k: v for k, v in OUTCOMES.items() if k in people}

            # Filter row: outcome | baseline | participant name filter
            with ui.row().classes("w-full items-center gap-4"):
                outcome = ui.select(outcomes, value="return", label="Outcome").classes(
                    "w-56"
                )
                baseline = ui.radio(BASELINES, value="net_position").props("inline")
                text = ui.input(placeholder="Only participants containing").props(
                    "dense clearable"
                )

            # The chart under the filters, redrawn by draw()
            box = ui.column().classes("w-full gap-1")

            async def draw() -> None:
                table = await run.io_bound(
                    self.service.participant_days, key, outcome.value
                )
                column = f"trained_minus_{baseline.value}"
                box.clear()

                with box:
                    if table.empty or column not in table:
                        ui.label("Nothing to show.").classes("mls-card-caption")
                        return

                    agents = shown_participants(table, column, text.value or "")
                    total = table.agent.nunique()
                    ui.label(f"{len(agents)} of {total} participants").classes(
                        "mls-card-caption"
                    )
                    title = (
                        f"{OUTCOMES[outcome.value]}:<br>trained −<br>"
                        + BASELINES[baseline.value]
                    )
                    ParticipantChart(
                        table=table, column=column, agents=agents, title=title
                    ).show()

            for field in (outcome, baseline, text):
                field.on_value_change(draw)

            ui.timer(0.01, draw, once=True)

    def traces(self, key: str, traced: bool) -> None:
        with section(
            "Traced days",
            'Step by step, with results_detail "detailed" (its trace_days)',
            "timeline",
        ):
            if not traced:
                ui.label(
                    'None: the run was not started with "results_detail": '
                    '"detailed".'
                ).classes("mls-card-caption")
                return

            # Empty until the button below is clicked, then the trace view
            box = ui.column().classes("w-full gap-2")

            async def open_traces() -> None:
                button.props("loading")
                steps = await run.io_bound(
                    self.service.table, key, "heldout_trace_steps"
                )
                agents = await run.io_bound(
                    self.service.table, key, "heldout_trace_agents"
                )
                button.delete()

                with box:
                    self._trace_view(steps, agents)

            button = ui.button(
                "Show the traced days", icon="timeline", on_click=open_traces
            ).props("outline no-caps dense")

    def _trace_view(self, steps: pd.DataFrame, agents: pd.DataFrame) -> None:
        # Charts and table, redrawn by draw(). Created before the selector row, so
        # they are shown above it
        box = ui.column().classes("w-full gap-2")

        # Selector row: day | policy | participant
        with ui.row().classes("w-full items-center gap-3"):
            day = ui.select(sorted(steps.day.unique()), label="Day")
            policy = ui.select(list(steps.policy.unique()), label="Policy")
            agent = ui.select(sorted(agents.agent.unique()), label="Participant")
            agent.props("use-input")  # type to find one of many

        for field in (day, policy, agent):
            field.set_value(field.options[0])

        def draw() -> None:
            box.clear()
            one = steps[(steps.day == day.value) & (steps.policy == policy.value)]
            person = agents[
                (agents.day == day.value)
                & (agents.policy == policy.value)
                & (agents.agent == agent.value)
            ]

            # Top to bottom: market kWh, clearing price, the participant's kWh,
            # battery and reward, then its orders and partners table
            with box:
                market = ["p2p_kwh", "preference_kwh"]
                market += ["bought_from_dso_kwh", "sold_to_dso_kwh"]
                for rows, columns, title in (
                    (one, market, "market kWh (preference_kwh: stage 1, part of p2p)"),
                    (one, ["clearing_price"], "clearing price"),
                    (person, ["order_kwh", "bought_kwh", "sold_kwh"], "kWh"),
                    (person, ["soc", "reward"], "battery and reward"),
                ):
                    TraceChart(steps=rows, columns=columns, title=title).show()

                shown = [(f, label) for f, label in TRACE_COLUMNS if f in person]

                if "partner" in person:
                    ui.label(
                        "Orders and partners: the partner named (a participant, DSO "
                        "or none), whether it named this participant back on the "
                        "other side (1/0), and the energy traded in stage 1"
                    ).classes("mls-card-caption")
                    ui.table(
                        columns=[
                            {"name": f, "label": label, "field": f, "align": "left"}
                            for f, label in shown
                        ],
                        rows=person[[f for f, _ in shown]]
                        .round(4)
                        .astype(object)
                        .where(person[[f for f, _ in shown]].notna(), "")
                        .to_dict("records"),
                        row_key="step",
                    ).props("dense flat").classes("w-full")

        for field in (day, policy, agent):
            field.on_value_change(draw)

        draw()


# --------------------------------------------------------------------------------------
# The tab
# --------------------------------------------------------------------------------------
class MarketTab(Tab):
    """The market per day during training and on the test days, per participant,
    and one run in depth."""

    label, icon = "Market", "storefront"

    def read(self, keys: list[str]) -> dict[str, Any]:
        return {
            "days": self.service.day_metrics(keys),
            "people": self.service.participant_metrics(keys),
        }

    def build(self, keys: list[str], data: dict[str, Any]) -> None:
        labels = labels_of(keys)
        common = dict(data=data, labels=labels)
        metric_card(
            self,
            "During training",
            "On the evaluation days (training days, unseen seeds), over environment "
            "steps: the mean over the days played at each point",
            "days",
            metrics=MARKET_METRICS,
            phase="evaluation",
            **common,
        )
        metric_card(
            self,
            "On the test days",
            "Each held-out test day, at the end of training",
            "days",
            metrics=MARKET_METRICS,
            phase="heldout",
            **common,
        )
        metric_card(
            self,
            "Per participant",
            "The same per participant on the test days; a line per participant "
            "with 'A line per: Participant'",
            "people",
            metrics=PARTICIPANT_METRICS,
            by=BY | {"agent": "Participant"},
            phase="heldout",
            **common,
        )

        with section("One run", "Its participants and traced days", "search"):
            one = OneRun(self.service)

            def show(key: Optional[str]) -> None:
                box.clear()

                if key:
                    with box:
                        people = self.service.table(key, "heldout_agents")
                        one.participants(key, people)
                        traced = self.service.result(key).has("heldout_trace_steps")
                        one.traces(key, traced)

            ui.select(labels, label="Run", on_change=lambda e: show(e.value)).classes(
                "w-full"
            )
            box = ui.column().classes("w-full gap-4")  # under the picker
