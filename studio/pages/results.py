"""Results: compare finished runs, and look into one of them.

The runs of this PC and of each cluster after *Sync results* on the Runs page, read
from their folders by ``core/runner/results.py`` (through ``ResultsService``; the
notebook ``notebooks/runner/results.ipynb`` reads the same). The table at the top
lists the runs; filters choose what it shows and the boxes, *Tick shown* and
*Untick all* what is ticked (``studio/components/run_table.py``). The runs ticked
there are compared in the first tab, and one of them is looked into in the second. How their learner behaved is on the
Validate → RL probes page.

Compare: the settings that differ between the runs (their full saved values), the
periodic evaluation return over environment steps, played on the training days
with seeds training did not use (not held out), with each run's own baselines (and its
training return, if asked), every held-out test day (the trained policy minus each
baseline on the same day), and each configuration over its training seeds. A run
is named by its experiment and run, and also by its target when the runs come from
more than one.

Inspect: one run's settings, test days, participants (a chosen outcome, trained
minus a baseline, per day and participant; with many participants those with the
largest difference, or those a filter names), the market and the grid per day, and,
with detailed results, the traced days step by step (read only when opened):
the market, and per participant its orders, the partner it named, whether the
choice was mutual and what it traded in the preference stage (stage 1).

Nothing is read again until Refresh: a new run or a new sync shows after it, in
every tab.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from nicegui import run, ui

from studio.adapters.results_service import ResultsService
from studio.components.cards import key_values, placeholder, section
from studio.components.charts import Chart, SeriesChart
from studio.components.run_table import RunTable, labels_of
from studio.components.run_table import cell as _cell
from studio.components.tables import data_table
from studio.layout import shell
from studio.state import services
from studio.theme import MUTED, SERIES

BASELINES = {"zero": "zero", "net_position": "net position"}
# The market and grid per test day (``heldout_episodes.csv``), as shown.
EPISODE_COLUMNS = [
    ("policy", "Policy"),
    ("day", "Day"),
    ("team_return", "Team return"),
    ("p2p_kwh", "P2P kWh"),
    ("bought_from_dso_kwh", "From DSO kWh"),
    ("sold_to_dso_kwh", "To DSO kWh"),
    ("grid_import_kwh", "Grid import kWh"),
    ("grid_export_kwh", "Grid export kWh"),
    ("grid_losses_kwh", "Grid losses kWh"),
    ("grid_violations", "Violations"),
    ("not_converged", "Not converged"),
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
MOST_PARTICIPANTS = 30  # shown at once; the rest through the filter
SHOW_TESTS = "results_show_tests"  # app.storage.user key


# --------------------------------------------------------------------------------------
# Names, cells and tables
# --------------------------------------------------------------------------------------
def _table(frame: pd.DataFrame, columns: list[tuple[str, str]]) -> ui.table:
    """A table of ``frame``'s ``columns`` (those it has), ``(field, label)``."""
    columns = [(f, label) for f, label in columns if f in frame]
    rows = [
        {"_row": i} | {f: _cell(row[f]) for f, _ in columns}
        for i, row in enumerate(frame.to_dict("records"))
    ]

    return data_table(rows, columns, row_key="_row", pagination=15)


def shown_participants(
    table: pd.DataFrame, column: str, text: str = "", most: int = MOST_PARTICIPANTS
) -> list[str]:
    """The participants the heatmap shows: those whose name contains ``text`` (all
    without), at most ``most``, the largest mean absolute ``column`` first."""
    sizes = table.groupby("agent")[column].apply(lambda v: v.abs().mean())

    if text:
        sizes = sizes[[text.lower() in str(a).lower() for a in sizes.index]]

    return list(sizes.sort_values(ascending=False).index[:most])


# --------------------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------------------
class LearningChart(SeriesChart):
    """Each run's trained policy over environment steps (evaluation; with ``train``
    also its training return, dotted), and each run's own baselines at step 0,
    dashed in its colour (one grey level when every run has the same).

    Options: ``curves``, ``training`` (``learning_curves`` / ``training_curves``),
    ``labels`` (run key -> name), ``per`` (per participant instead of the team),
    ``train`` (with the training return).
    """

    height = 380
    x_title = "environment steps"

    def draw(self) -> None:
        o = self.o
        value = "per_participant" if o.per else "team_return_mean"
        self.titles(y=f"return ({'per participant' if o.per else 'team'})")
        keys = list(dict.fromkeys(o.curves.key))
        colors = {k: SERIES[i % len(SERIES)] for i, k in enumerate(keys)}

        for key in keys:
            rows = o.curves[(o.curves.key == key) & (o.curves.policy == "trained")]
            self.line(
                rows.env_steps, rows[value], o.labels[key], colors[key], markers=True
            )

            if o.train and not o.training.empty:
                own = o.training[o.training.key == key]
                name = f"{o.labels[key]} (training)"
                self.line(own.env_steps, own[value], name, colors[key], dash="dot")

        start = o.curves[(o.curves.env_steps == 0) & (o.curves.policy != "trained")]

        for policy, rows in start.groupby("policy"):
            if rows[value].round(9).nunique() == 1:  # the same for every run
                self.level(rows[value].iloc[0], f"{policy} (step 0)")
                continue

            for _, row in rows.iterrows():
                end = o.curves[o.curves.key == row.key].env_steps.max()
                name = f"{o.labels[row.key]}: {policy}"
                y = [row[value]] * 2
                self.line([0, end], y, name, colors[row.key], dash="dash", width=1)


class HeldoutChart(Chart):
    """Per run, the trained policy minus each baseline on every test day, as boxes.
    Options: ``days`` (``heldout_days``), ``labels``."""

    height = 380
    y_title = "difference per test day"
    layout = {"boxmode": "group", "hovermode": "closest"}

    def draw(self) -> None:
        for i, (baseline, label) in enumerate(BASELINES.items()):
            column = f"trained_minus_{baseline}"

            if column in self.o.days:
                self.fig.add_box(
                    x=[self.o.labels[k] for k in self.o.days.key],
                    y=self.o.days[column],
                    name=f"trained − {label}",
                    boxpoints="all",
                    jitter=0.3,
                    marker_color=SERIES[i + 1],
                )

        self.fig.add_hline(y=0, line_color=MUTED)


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


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
class ResultsView:
    """The run table, and the Compare and Inspect tabs for the runs ticked in it
    (the learner of the ticked runs: Validate → RL probes).

    Args:
        service: The Results service.
    """

    def __init__(self, service: ResultsService) -> None:
        self.service = service
        self._drawn = {"compare": 0, "inspect": 0}  # latest draws
        # The run table at the top, with a tick box per run
        self.table = RunTable(service, self._selected, SHOW_TESTS)

        # Tab bar under it: Compare | Inspect a run
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            ui.tab("compare", label="Compare", icon="compare_arrows")
            ui.tab("inspect", label="Inspect a run", icon="search")

        with ui.tab_panels(tabs, value="compare").classes("w-full bg-transparent"):
            # Compare tab: its cards are drawn by _show_compare()
            with ui.tab_panel("compare").classes("p-0 gap-4"):
                self.compare = ui.column().classes("w-full gap-4")

            # Inspect tab: the run picker, then the cards of _show_run()
            with ui.tab_panel("inspect").classes("p-0 gap-4"):
                with ui.row().classes("w-full items-center gap-3"):
                    self.inspected = (
                        ui.select([], label="Run", on_change=self._show_run)
                        .classes("grow")
                        .style("min-width: 320px")
                    )
                self.inspect = ui.column().classes("w-full gap-4")

    async def load(self) -> None:
        await self.table.load()

    async def _selected(self) -> None:
        """The ticked runs changed (or were read again): compare them, and draw the
        inspected run again, or the first one offered when it is gone."""
        options = self.selected or list(self.table.visible().get("key", []))
        self.inspected.set_options(options)

        if self.inspected.value not in options:
            self.inspected.set_value(options[0] if options else None)  # draws it
        else:
            await self._show_run()

        await self._show_compare()

    @property
    def selected(self) -> list[str]:
        return self.table.selected

    def _draw(self, tab: str) -> int:
        """A new draw of ``tab``: its number. A draw that waited for files and is no
        longer the latest leaves the tab to the newer one."""
        self._drawn[tab] += 1
        return self._drawn[tab]

    # --- Compare ---------------------------------------------------------------------
    async def _show_compare(self) -> None:
        keys = list(self.selected)
        draw = self._draw("compare")
        self.compare.clear()

        if not keys:
            with self.compare:
                placeholder("Tick runs in the table to compare them.", "checklist")
            return

        service = self.service
        differs = await run.io_bound(service.differing_settings, keys)
        curves = await run.io_bound(service.learning_curves, keys)
        training = await run.io_bound(service.training_curves, keys)
        days = await run.io_bound(service.heldout_days, keys)
        groups = await run.io_bound(service.seed_groups, keys)

        if draw != self._drawn["compare"]:  # ticked again meanwhile
            return

        labels = labels_of(keys)

        # The Compare tab's cards, top to bottom: the runs, did it learn?, the final
        # policy, consistency over seeds
        with self.compare:
            with section("The runs", f"{len(keys)} ticked", "list"):
                varying = {"seed"}  # what differs between the seeds of one grid
                shown = [d for d in differs if d not in varying]
                ui.label(
                    "Settings that differ (their full saved values): "
                    + (", ".join(shown) or "none")
                ).classes("text-body2")

                if shown:
                    ui.label(
                        "Inspect each run for its values; runs that differ in "
                        "scenario, days, budget, training settings or model are not "
                        "one configuration."
                    ).classes("mls-card-caption")

            with section(
                "Did it learn?",
                "Each run's trained policy on the periodic evaluation episodes "
                "during training: the training days, on seeds training did not "
                "use (the held-out test days are below); its baselines at step 0, "
                "dashed in its colour (one grey line when every run's is the "
                "same).",
                "show_chart",
            ):
                if curves.empty:
                    ui.label("No evaluation recorded.").classes("mls-card-caption")
                else:
                    chart = LearningChart(
                        curves=curves,
                        training=training,
                        labels=labels,
                        per=False,
                        train=False,
                    ).show()

                    # Two switches under the chart, each changing one option
                    with ui.row().classes("gap-4"):
                        chart.switch("per", "Per participant")
                        chart.switch(
                            "train",
                            "Training return (the sampled episodes while learning)",
                        )

            with section(
                "How good is the final policy?",
                "Every held-out test day: the trained policy minus each baseline on "
                "the same day (above 0: better). A run from before the per-day "
                "tables shows its means only.",
                "leaderboard",
            ):
                if days.empty:
                    ui.label("No held-out evaluation.").classes("mls-card-caption")
                else:
                    HeldoutChart(days=days, labels=labels).show()

            with section(
                "How consistent is it?",
                "Each configuration over its training seeds: the seeds' held-out "
                "means, their spread (std over seeds, 0 with one), and the settings "
                "that differ inside a group (it should be none).",
                "stacked_line_chart",
            ):
                _table(
                    groups,
                    [
                        ("target", "Target"),
                        ("experiment", "Experiment"),
                        ("algorithm", "Algorithm"),
                        ("paradigm", "Paradigm"),
                        ("variant", "Variant"),
                        ("completed", "Seeds done"),
                        ("runs", "Runs"),
                        ("mean", "Mean"),
                        ("std", "Std over seeds"),
                        ("min", "Min"),
                        ("max", "Max"),
                        ("trained_minus_zero", "− zero"),
                        ("trained_minus_net_position", "− net position"),
                        ("differs", "Differs"),
                    ],
                )

    # --- Inspect one run -------------------------------------------------------------
    async def _show_run(self) -> None:
        key = self.inspected.value
        draw = self._draw("inspect")
        self.inspect.clear()

        if not key:
            return

        service = self.service
        result = await run.io_bound(service.result, key)
        days = await run.io_bound(service.heldout_days, [key])
        episodes = await run.io_bound(service.table, key, "heldout_episodes")
        people = await run.io_bound(service.table, key, "heldout_agents")

        if draw != self._drawn["inspect"]:  # another run was picked meanwhile
            return

        # The Inspect tab's cards, top to bottom: the run, test days, participants,
        # market and grid per day, traced days
        with self.inspect:
            with section(key, "What the run was", "info"):
                shown = {k: _cell(v) for k, v in result.labels.items() if v is not None}
                state = result.state

                if state:
                    shown["state"] = state.state
                    shown["env steps"] = f"{state.env_steps:,} / {state.budget or '?'}"

                key_values(shown)

                for name, title in (
                    ("overrides", "Training settings"),
                    ("model", "Model"),
                ):
                    if result.settings.get(name):
                        # Collapsible list of the settings, inside the card
                        with ui.expansion(title, icon="tune").classes("w-full"):
                            key_values(
                                {k: _cell(v) for k, v in result.settings[name].items()}
                            )

            with section("Test days", "Team return of each policy per day", "event"):
                _table(
                    days,
                    [
                        ("day", "Day"),
                        ("trained", "Trained"),
                        ("zero", "Zero"),
                        ("net_position", "Net position"),
                        ("trained_minus_zero", "− zero"),
                        ("trained_minus_net_position", "− net position"),
                    ],
                )

            self._participants(key, people)

            with section(
                "Market and grid per day",
                "Energy and the AC power flow, summed over each day",
                "bolt",
            ):
                if episodes is None:
                    ui.label(
                        "Not recorded: a run from before the per-day tables."
                    ).classes("mls-card-caption")
                else:
                    _table(episodes, EPISODE_COLUMNS)

            self._traces(key, result.has("heldout_trace_steps"))

    def _participants(self, key: str, people: Optional[pd.DataFrame]) -> None:
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

    def _traces(self, key: str, traced: bool) -> None:
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


def page() -> None:
    """The runs, read once when the page opens."""
    with shell(
        "results",
        "Results",
        "Compare finished runs of this PC and of the clusters (after Sync results on "
        "the Runs page), and look into one of them.",
    ):
        view = ResultsView(services().results)
        ui.timer(0.05, view.load, once=True)
