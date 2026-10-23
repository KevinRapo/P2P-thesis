"""Results: compare finished runs, and look into one of them.

The runs of this PC and of each cluster after *Sync results* on the Runs page, read
from their folders by ``core/runner/results.py`` (through ``ResultsService``; the
notebook ``notebooks/runner/results.ipynb`` reads the same). The table at the top
lists every run; test-profile runs (``<name>--test``) can be hidden. The runs ticked
there are compared in the first tab, and one of them is looked into in the second.

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

Nothing is read again until Refresh: a new run or a new sync shows after it, in both
tabs.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
from nicegui import app, run, ui

from studio.adapters.results_service import ResultsService
from studio.components.cards import key_values, placeholder, section
from studio.components.charts import styled
from studio.layout import shell
from studio.state import services
from studio.theme import SERIES

BASELINES = {"zero": "zero", "net_position": "net position"}
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
def labels_of(keys: list[str]) -> dict[str, str]:
    """A label per run key: ``experiment/run``, and ``target/experiment/run`` when
    the runs come from more than one target (so two targets' runs stay apart)."""
    targets = {key.split("/", 1)[0] for key in keys}
    return {key: key if len(targets) > 1 else key.split("/", 1)[1] for key in keys}


def _cell(value: Any) -> Any:
    """A value as a table cell shows it: rounded, and empty for missing."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    if isinstance(value, float):
        return round(value, 3)

    if isinstance(value, list):
        return ", ".join(map(str, value))

    if isinstance(value, dict):
        return ", ".join(f"{k}: {_cell(v)}" for k, v in value.items())

    return value


def _table(frame: pd.DataFrame, columns: list[tuple[str, str]]) -> ui.table:
    """A table of ``frame``'s ``columns`` (those it has), ``(field, label)``."""
    columns = [(f, label) for f, label in columns if f in frame]
    rows = [
        {"_row": i} | {f: _cell(row[f]) for f, _ in columns}
        for i, (_, row) in enumerate(frame.iterrows())
    ]

    return (
        ui.table(
            columns=[
                {"name": f, "label": label, "field": f, "sortable": True}
                | {"align": "left"}
                for f, label in columns
            ],
            rows=rows,
            row_key="_row",
            pagination={"rowsPerPage": 15},
        )
        .classes("w-full")
        .props("flat dense")
    )


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
def _learning_figure(
    curves: pd.DataFrame,
    training: pd.DataFrame,
    labels: dict[str, str],
    per_participant: bool,
    with_training: bool,
) -> go.Figure:
    """Each run's trained policy over environment steps (evaluation, and with
    ``with_training`` its training return, dotted), and each run's own baselines at
    step 0, dashed in its colour (one grey line when every run has the same)."""
    value = "per_participant" if per_participant else "team_return_mean"
    fig = go.Figure()
    keys = list(dict.fromkeys(curves.key))
    colors = {key: SERIES[i % len(SERIES)] for i, key in enumerate(keys)}

    for key in keys:
        rows = curves[(curves.key == key) & (curves.policy == "trained")]
        fig.add_scatter(
            x=rows.env_steps,
            y=rows[value],
            name=labels[key],
            mode="lines+markers",
            line=dict(color=colors[key]),
        )
        if with_training and not training.empty:
            own = training[training.key == key]
            fig.add_scatter(
                x=own.env_steps,
                y=own[value],
                name=f"{labels[key]} (training)",
                mode="lines",
                line=dict(color=colors[key], dash="dot"),
            )

    start = curves[(curves.env_steps == 0) & (curves.policy != "trained")]

    for policy, rows in start.groupby("policy"):
        if rows[value].round(9).nunique() == 1:  # the same for every run: one line
            fig.add_hline(
                y=rows[value].iloc[0],
                line_dash="dash",
                line_color="#94A3B8",
                annotation_text=f"{policy} (step 0)",
                annotation_position="top left",
            )
            continue
        for _, row in rows.iterrows():
            end = curves[curves.key == row.key].env_steps.max()
            fig.add_scatter(
                x=[0, end],
                y=[row[value]] * 2,
                name=f"{labels[row.key]}: {policy}",
                mode="lines",
                line=dict(color=colors[row.key], dash="dash", width=1),
            )

    label = "per participant" if per_participant else "team"

    return styled(fig, 380, f"return ({label})", "environment steps")


def _heldout_figure(days: pd.DataFrame, labels: dict[str, str]) -> go.Figure:
    """Per run, the trained policy minus each baseline on every test day."""
    fig = go.Figure()

    for i, (baseline, label) in enumerate(BASELINES.items()):
        column = f"trained_minus_{baseline}"
        if column not in days:
            continue
        fig.add_box(
            x=[labels[k] for k in days.key],
            y=days[column],
            name=f"trained − {label}",
            boxpoints="all",
            jitter=0.3,
            marker_color=SERIES[i + 1],
        )

    fig.add_hline(y=0, line_color="#94A3B8")
    fig.update_layout(boxmode="group", hovermode="closest")

    return styled(fig, 380, "difference per test day")


def _participant_figure(
    table: pd.DataFrame, column: str, agents: list[str], title: str
) -> go.Figure:
    """The ``agents`` × test days: ``column`` (trained minus a baseline)."""
    grid = table[table.agent.isin(agents)].pivot(
        index="agent", columns="day", values=column
    )
    grid = grid.reindex([a for a in agents if a in grid.index])
    limit = float(grid.abs().max().max() or 1.0)
    fig = go.Figure(
        go.Heatmap(
            z=grid.values,
            x=list(grid.columns),
            y=list(grid.index),
            colorscale="RdBu",
            zmin=-limit,
            zmax=limit,
            colorbar=dict(title=title),
        )
    )
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(autorange="reversed")  # the largest difference on top

    return styled(fig, max(260, 26 * len(grid) + 120))


def _steps_figure(steps: pd.DataFrame, columns: list[str], title: str) -> go.Figure:
    """Lines of ``columns`` over the steps of one traced day."""
    fig = go.Figure()

    for i, column in enumerate(c for c in columns if c in steps):
        fig.add_scatter(
            x=steps.step,
            y=steps[column],
            name=column,
            mode="lines+markers",
            line=dict(color=SERIES[i % len(SERIES)]),
        )

    return styled(fig, 280, title, "step")


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
class ResultsView:
    """The run table, and the Compare and Inspect tabs for the runs ticked in it.

    Args:
        service: The Results service.
    """

    def __init__(self, service: ResultsService) -> None:
        self.service = service
        self.overview = pd.DataFrame()
        self.selected: list[str] = []
        self._drawn = {"compare": 0, "inspect": 0}  # the latest draw of each tab

        with ui.row().classes("w-full items-center gap-3"):
            ui.button("Refresh", icon="refresh", on_click=self.refresh).props(
                "flat no-caps dense"
            )
            self.show_tests = ui.switch(
                "Show test runs",
                value=app.storage.user.get(SHOW_TESTS, True),
                on_change=self._tests_changed,
            )
            self.experiment = (
                ui.select(
                    [],
                    label="Tick every run of an experiment",
                    on_change=self._tick_experiment,
                    clearable=True,
                )
                .classes("grow")
                .style("min-width: 260px")
            )
            self.search = ui.input(placeholder="Filter runs").props("dense clearable")

        self.note = ui.label().classes("mls-card-caption")
        self.runs = (
            ui.table(
                columns=[
                    {"name": f, "label": label, "field": f, "sortable": True}
                    | {"align": "left"}
                    for f, label in RUN_COLUMNS
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
        self.search.bind_value_to(self.runs, "filter")

        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            ui.tab("compare", label="Compare", icon="compare_arrows")
            ui.tab("inspect", label="Inspect a run", icon="search")

        with ui.tab_panels(tabs, value="compare").classes("w-full bg-transparent"):
            with ui.tab_panel("compare").classes("p-0 gap-4"):
                self.compare = ui.column().classes("w-full gap-4")
            with ui.tab_panel("inspect").classes("p-0 gap-4"):
                with ui.row().classes("w-full items-center gap-3"):
                    self.inspected = (
                        ui.select([], label="Run", on_change=self._show_run)
                        .classes("grow")
                        .style("min-width: 320px")
                    )
                self.inspect = ui.column().classes("w-full gap-4")

    # --- The run table ---------------------------------------------------------------
    async def load(self) -> None:
        """Read the runs (once; ``refresh`` reads them again) and fill the table."""
        self.note.set_text("Reading the runs ...")
        self.overview = await run.io_bound(self.service.overview)
        self._fill()

    async def refresh(self) -> None:
        """Read every run again, and draw both tabs from what is read now."""
        self.service.refresh()
        await self.load()
        await self._selected()

    def _visible(self) -> pd.DataFrame:
        table = self.overview
        if table.empty or self.show_tests.value:
            return table
        return table[~table.test]

    def _fill(self) -> None:
        table = self._visible()
        self.runs.rows = [
            {"key": row["key"]} | {f: _cell(row.get(f)) for f, _ in RUN_COLUMNS}
            for _, row in table.iterrows()
        ]
        keys = set(table.key) if len(table) else set()
        self.runs.selected = [r for r in self.runs.rows if r["key"] in self.selected]
        self.runs.update()
        experiments = (
            sorted({f"{t}/{e}" for t, e in zip(table.target, table.experiment)})
            if len(table)
            else []
        )
        self.experiment.set_options(experiments)
        hidden = len(self.overview) - len(table)
        text = f"{len(table)} runs"

        if hidden:
            text += f" ({hidden} test runs hidden)"

        if not len(self.overview):
            text = (
                "No runs yet. Runs on this PC appear here when they have files; a "
                "cluster's after Sync results on the Runs page."
            )

        self.note.set_text(text)
        self.selected = [k for k in self.selected if k in keys]

    async def _tests_changed(self) -> None:
        app.storage.user[SHOW_TESTS] = bool(self.show_tests.value)
        self._fill()
        await self._selected()

    async def _tick_experiment(self) -> None:
        if not self.experiment.value:
            return

        target, experiment = self.experiment.value.split("/", 1)
        table = self._visible()
        chosen = (table.target == target) & (table.experiment == experiment)
        keys = list(table[chosen].key)
        self.runs.selected = [r for r in self.runs.rows if r["key"] in keys]
        self.runs.update()
        await self._selected()

    async def _selected(self, _: Any = None) -> None:
        """The ticked runs changed (or were read again): compare them, and draw the
        inspected run again, or the first one offered when it is gone."""
        self.selected = [row["key"] for row in self.runs.selected]
        options = self.selected or list(self._visible().get("key", []))
        self.inspected.set_options(options)

        if self.inspected.value not in options:
            self.inspected.set_value(options[0] if options else None)  # draws it
        else:
            await self._show_run()

        await self._show_compare()

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
                    options = {"per": False, "training": False}
                    plot = ui.plotly(
                        _learning_figure(curves, training, labels, False, False)
                    ).classes("w-full")

                    def redraw(name: str, value: bool) -> None:
                        options[name] = value
                        plot.update_figure(
                            _learning_figure(
                                curves,
                                training,
                                labels,
                                options["per"],
                                options["training"],
                            )
                        )

                    with ui.row().classes("gap-4"):
                        ui.switch(
                            "Per participant",
                            on_change=lambda e: redraw("per", bool(e.value)),
                        )
                        ui.switch(
                            "Training return (the sampled episodes while learning)",
                            on_change=lambda e: redraw("training", bool(e.value)),
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
                    ui.plotly(_heldout_figure(days, labels)).classes("w-full")

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

            with ui.row().classes("w-full items-center gap-4"):
                outcome = ui.select(outcomes, value="return", label="Outcome").classes(
                    "w-56"
                )
                baseline = ui.radio(BASELINES, value="net_position").props("inline")
                text = ui.input(placeholder="Only participants containing").props(
                    "dense clearable"
                )

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
                    ui.plotly(
                        _participant_figure(table, column, agents, title)
                    ).classes("w-full")

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
        box = ui.column().classes("w-full gap-2")

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

            with box:
                ui.plotly(
                    _steps_figure(
                        one,
                        [
                            "p2p_kwh",
                            "preference_kwh",
                            "bought_from_dso_kwh",
                            "sold_to_dso_kwh",
                        ],
                        "market kWh (preference_kwh: stage 1, part of p2p)",
                    )
                ).classes("w-full")
                ui.plotly(
                    _steps_figure(one, ["clearing_price"], "clearing price")
                ).classes("w-full")
                ui.plotly(
                    _steps_figure(
                        person, ["order_kwh", "bought_kwh", "sold_kwh"], "kWh"
                    )
                ).classes("w-full")
                ui.plotly(
                    _steps_figure(person, ["soc", "reward"], "battery and reward")
                ).classes("w-full")
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
