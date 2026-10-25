"""Results: compare finished runs, and look into one of them.

The runs of this PC and of each cluster after *Sync results* on the Runs page, read
from their folders by ``core/runner/results.py`` (through ``ResultsService``; the
notebook ``notebooks/runner/results.ipynb`` reads the same). The table at the top
lists every run; test-profile runs (``<name>--test``) can be hidden. Choosing one
experiment shows only its runs and ticks all of them; *Ticked only* shows only the
ticked runs; *Clear* unticks everything and shows every run again. The runs ticked
there are compared in the first tab, one of them is looked into in the second, and
their learner is shown in the third.

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

Learning: how the ticked runs' learner behaved, from their ``metrics.csv``
(``core/runner/results.learner_metrics``), for any environment: the training
return; per module the policy and value losses, the critic's explained variance,
the entropy, the KL of each update and the gradient norm against the run's clip;
and one action part at a time, its distribution over training.

Nothing is read again until Refresh: a new run or a new sync shows after it, in
every tab.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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


DASHES = ["solid", "dot", "dash", "dashdot", "longdash", "longdashdot"]


def _learner_figure(
    metrics: pd.DataFrame,
    names: list[str],
    labels: dict[str, str],
    mean_over_modules: bool,
    clip: Optional[dict[str, float]] = None,
) -> go.Figure:
    """The module metrics ``names`` over environment steps: a colour per run, one
    line per module (or their mean), a dash per metric; ``clip`` draws each run's
    gradient clip as a dashed level."""
    fig = go.Figure()
    keys = list(dict.fromkeys(metrics.key))
    colors = {key: SERIES[i % len(SERIES)] for i, key in enumerate(keys)}
    rows = metrics[(metrics.part == "") & metrics.metric.isin(names)]

    for key in keys:
        own = rows[rows.key == key]
        for dash, name in zip(DASHES, names):
            frame = own[own.metric == name]
            if frame.empty:
                continue

            if mean_over_modules:
                lines = {"mean": frame.groupby("env_steps").value.mean().reset_index()}
            else:
                lines = {m: f for m, f in frame.groupby("module")}

            for module, line in lines.items():
                suffix = "" if len(names) == 1 else f" {name}"
                fig.add_scatter(
                    x=line.env_steps,
                    y=line.value,
                    name=f"{labels[key]} · {module}{suffix}",
                    mode="lines",
                    line=dict(color=colors[key], dash=dash, width=1.5),
                )

        if clip and clip.get(key) is not None:
            fig.add_hline(y=clip[key], line_dash="dash", line_color=colors[key])

    fig.update_layout(showlegend=True)  # also with one line: which run it is

    return styled(fig, 300, "", "environment steps")


def _agent_part(module: str, part: str) -> tuple[str, str]:
    """An action part's agent and name: the module and the part, or, for CTCE's
    group (``agent.part``), the agent named in the part."""
    if "." in part:
        agent, name = part.split(".", 1)
        return agent, name

    return module, part


def _part_series(
    metrics: pd.DataFrame, key: str, part: str
) -> dict[str, dict[str, pd.Series]]:
    """Per agent, the statistics of action part ``part`` of run ``key`` over
    environment steps: ``{agent: {metric: series}}``."""
    rows = metrics[(metrics.key == key) & (metrics.part != "")]
    found: dict[str, dict[str, pd.Series]] = {}

    for (module, name, metric), frame in rows.groupby(["module", "part", "metric"]):
        agent, base = _agent_part(module, name)
        if base == part:
            found.setdefault(agent, {})[metric] = frame.set_index("env_steps").value

    return found


def _rgba(color: str, alpha: float) -> str:
    """A ``#rrggbb`` colour with transparency."""
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))

    return f"rgba({r},{g},{b},{alpha})"


def _parts_figure(metrics: pd.DataFrame, key: str, label: str) -> go.Figure:
    """Every action part of one run over environment steps, in panels stacked on
    one time axis, a colour per agent (the same in every panel):

    - a continuous part: its mean with a band of ±σ (the bounds ±1 dashed), then
      its log σ (solid; σ itself in the hover) and the share of means outside
      [-1, 1] (dotted, right axis);
    - a categorical part: its entropy (solid) and its most likely category's
      probability (dashed).
    """
    rows = metrics[(metrics.key == key) & (metrics.part != "")]
    parts = sorted({_agent_part(m, p)[1] for m, p in zip(rows.module, rows.part)})
    series = {part: _part_series(metrics, key, part) for part in parts}
    agents = list(dict.fromkeys(a for s in series.values() for a in s))
    colors = {a: SERIES[i % len(SERIES)] for i, a in enumerate(agents)}
    panels = []  # (part, kind)

    for part in parts:
        if any("mean" in s for s in series[part].values()):
            panels += [(part, "mean"), (part, "spread")]
        else:
            panels.append((part, "categorical"))

    titles = {
        "mean": "{} · mean ± σ",
        "spread": "{} · log σ, share outside [-1, 1]",
        "categorical": "{} · entropy, top probability",
    }
    fig = make_subplots(
        rows=len(panels),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=[titles[kind].format(part) for part, kind in panels],
        specs=[[{"secondary_y": kind == "spread"}] for _, kind in panels],
    )
    shown = set()  # agents already in the legend

    def legend(agent: str) -> bool:
        first = agent not in shown
        shown.add(agent)
        return first

    for row, (part, kind) in enumerate(panels, start=1):
        for agent, stats in series[part].items():
            color = colors[agent]
            common = dict(legendgroup=agent, name=agent, mode="lines")

            if kind == "mean":
                mean, sigma = stats["mean"], stats["log_std"].pipe(np.exp)
                steps = list(mean.index)
                fig.add_scatter(
                    x=steps + steps[::-1],
                    y=list(mean + sigma) + list((mean - sigma)[::-1]),
                    fill="toself",
                    fillcolor=_rgba(color, 0.12),
                    line=dict(width=0),
                    legendgroup=agent,
                    showlegend=False,
                    hoverinfo="skip",
                    row=row,
                    col=1,
                )
                fig.add_scatter(
                    x=steps,
                    y=mean,
                    line=dict(color=color),
                    showlegend=legend(agent),
                    row=row,
                    col=1,
                    **common,
                )
            elif kind == "spread":
                log_std = stats["log_std"]
                fig.add_scatter(
                    x=list(log_std.index),
                    y=log_std,
                    line=dict(color=color),
                    showlegend=legend(agent),
                    customdata=np.exp(log_std.to_numpy()),
                    hovertemplate="log σ %{y:.2f} (σ %{customdata:.4f})"
                    "<extra>%{fullData.name}</extra>",
                    row=row,
                    col=1,
                    **common,
                )
                if "outside" in stats:
                    fig.add_scatter(
                        x=list(stats["outside"].index),
                        y=stats["outside"],
                        line=dict(color=color, dash="dot"),
                        showlegend=False,
                        row=row,
                        col=1,
                        secondary_y=True,
                        **common,
                    )
            else:
                for name, dash in (("entropy", "solid"), ("top", "dash")):
                    if name in stats:
                        fig.add_scatter(
                            x=list(stats[name].index),
                            y=stats[name],
                            line=dict(color=color, dash=dash),
                            showlegend=legend(agent),
                            row=row,
                            col=1,
                            **common,
                        )

        if kind == "mean":
            for bound in (-1.0, 1.0):
                fig.add_hline(
                    y=bound, line_dash="dash", line_color="#94A3B8", row=row, col=1
                )
        elif kind == "spread":
            fig.add_hline(y=0, line_dash="dot", line_color="#94A3B8", row=row, col=1)
            fig.update_yaxes(
                range=[0, 1], showgrid=False, row=row, col=1, secondary_y=True
            )

    fig = styled(fig, 230 * len(panels) + 80, "", "")
    fig.update_xaxes(title="environment steps", row=len(panels), col=1)
    fig.update_layout(
        title=dict(text=label, font_size=13), showlegend=True, hovermode="x unified"
    )

    return fig


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
        self._drawn = {"compare": 0, "inspect": 0, "learning": 0}  # latest draws

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
                    label="One experiment (shows and ticks its runs)",
                    on_change=self._experiment_changed,
                    clearable=True,
                )
                .classes("grow")
                .style("min-width: 260px")
            )
            self.only_ticked = ui.switch(
                "Ticked only", on_change=lambda _: self._fill()
            )
            ui.button("Clear", icon="deselect", on_click=self.clear).props(
                "flat no-caps dense"
            ).tooltip("Untick every run, and show them all again")
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
            ui.tab("learning", label="Learning", icon="psychology")

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
            with ui.tab_panel("learning").classes("p-0 gap-4"):
                self.learning = ui.column().classes("w-full gap-4")

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

    def _offered(self) -> pd.DataFrame:
        """Every run that can be ticked: all, or all but the test runs."""
        table = self.overview
        if table.empty or self.show_tests.value:
            return table
        return table[~table.test]

    def _visible(self) -> pd.DataFrame:
        """The runs the table shows: those offered, narrowed to the chosen
        experiment and, with *Ticked only*, to the ticked runs."""
        table = self._offered()

        if table.empty:
            return table

        if self.experiment.value:
            target, experiment = self.experiment.value.split("/", 1)
            table = table[(table.target == target) & (table.experiment == experiment)]

        if self.only_ticked.value:
            table = table[table.key.isin(self.selected)]

        return table

    def _fill(self) -> None:
        offered = self._offered()
        keys = set(offered.key) if len(offered) else set()
        self.selected = [k for k in self.selected if k in keys]
        table = self._visible()
        self.runs.rows = [
            {"key": row["key"]} | {f: _cell(row.get(f)) for f, _ in RUN_COLUMNS}
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
        app.storage.user[SHOW_TESTS] = bool(self.show_tests.value)
        self._fill()
        await self._selected()

    async def _experiment_changed(self) -> None:
        """An experiment chosen: show only its runs and tick all of them (the ticks
        are replaced). Cleared: show every run again, the ticks kept."""
        if self.experiment.value:
            target, experiment = self.experiment.value.split("/", 1)
            table = self._offered()
            chosen = (table.target == target) & (table.experiment == experiment)
            self.selected = list(table[chosen].key)

        self._fill()
        await self._selected()

    async def clear(self) -> None:
        """Untick every run and show them all: no experiment, not *Ticked only*."""
        self.selected = []
        self.only_ticked.value = False  # its own redraw of the table is cheap

        if self.experiment.value:
            self.experiment.set_value(None)  # redraws the table and the tabs
            return

        self._fill()
        await self._selected()

    async def _selected(self, _: Any = None) -> None:
        """The ticked runs changed (or were read again): compare them, and draw the
        inspected run again, or the first one offered when it is gone."""
        self.selected = [row["key"] for row in self.runs.selected]
        self._fill()  # the count, and with *Ticked only* the rows unticked just now
        options = self.selected or list(self._visible().get("key", []))
        self.inspected.set_options(options)

        if self.inspected.value not in options:
            self.inspected.set_value(options[0] if options else None)  # draws it
        else:
            await self._show_run()

        await self._show_compare()
        await self._show_learning()

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

    # --- Learning: the learner of the ticked runs -------------------------------------
    async def _show_learning(self) -> None:
        keys = list(self.selected)
        draw = self._draw("learning")
        self.learning.clear()

        if not keys:
            with self.learning:
                placeholder("Tick runs in the table to see how they learned.", "school")

            return

        metrics = await run.io_bound(self.service.learner_metrics, keys)
        results = await run.io_bound(self.service.results, keys)

        if draw != self._drawn["learning"]:  # ticked again meanwhile
            return

        labels = labels_of(keys)
        clip = {r.key: r.settings.get("grad_clip") for r in results}

        with self.learning:
            if metrics.empty:
                placeholder("The ticked runs have no metrics yet.", "hourglass_empty")
                return

            modules = metrics[metrics.module != ""].module.nunique()
            mean = ui.switch("Mean over modules", value=modules > 3)
            ui.label(
                "One colour per run, one line per module (agent, or the group in "
                "CTCE). Read from each run's metrics.csv; a run from before 25 Oct "
                "has no per-part statistics, gradient norm or KL."
            ).classes("mls-card-caption")
            figures = []

            with section(
                "Training return",
                "The sampled episodes' team return while learning (with exploration).",
                "show_chart",
            ):
                fig = _learner_figure(metrics, ["team_return_mean"], labels, True)
                ui.plotly(fig).classes("w-full")

            with ui.grid(columns=2).classes("w-full gap-4"):
                for title, names, note in self.service.learner_groups:
                    present = [n for n in names if n in set(metrics.metric)]
                    if not present:
                        continue
                    gradient = "gradients_default_optimizer_global_norm" in present
                    has = set(metrics[metrics.metric.isin(present)].key)
                    missing = [labels[k] for k in keys if k not in has]
                    with section(title, note):
                        if missing:
                            ui.label(
                                "Not recorded in: "
                                + ", ".join(missing)
                                + " (trained before this metric was logged, or "
                                "with it switched off)"
                            ).classes("mls-card-caption")
                        plot = ui.plotly(
                            _learner_figure(
                                metrics,
                                present,
                                labels,
                                mean.value,
                                clip if gradient else None,
                            )
                        ).classes("w-full")
                        figures.append((plot, present, gradient))

            def redraw() -> None:
                for plot, present, gradient in figures:
                    plot.update_figure(
                        _learner_figure(
                            metrics,
                            present,
                            labels,
                            mean.value,
                            clip if gradient else None,
                        )
                    )

            mean.on_value_change(lambda _: redraw())
            with_parts = list(dict.fromkeys(metrics[metrics.part != ""].key))
            options = {k: labels[k] for k in with_parts}

            with section(
                "Each action part",
                "Every action part of one run, every agent in its own colour, read "
                "in the same fixed states every report: a continuous part's mean "
                "± σ (network units: ±1 are its bounds), then its log σ and the "
                "share of means outside the bounds; a categorical part's entropy "
                "and its most likely category's probability.",
                "tune",
            ):
                if not options:
                    ui.label("No per-part statistics in these runs.").classes(
                        "mls-card-caption"
                    )
                    return

                chosen = ui.select(
                    options, value=next(iter(options)), label="Run"
                ).classes("w-full")
                parts_plot = ui.plotly(go.Figure()).classes("w-full")

                def show_parts() -> None:
                    key = chosen.value
                    parts_plot.update_figure(_parts_figure(metrics, key, labels[key]))

                chosen.on_value_change(lambda _: show_parts())
                show_parts()

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
