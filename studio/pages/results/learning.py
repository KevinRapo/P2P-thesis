"""Results → Learning: did it learn? Everything here is on the training days. The
training return next to the periodic evaluation (on seeds training did not use), in
return or money, with the baselines of step 0; from ``metrics.csv``
(``core/runner/results.learner_metrics``), for any environment, per module the policy
and value losses, the critic's explained variance, the entropy, the KL of each update
and the gradient norm against the run's clip; and one run's action parts over training,
over the agents and agent by agent. Every chart follows the live view.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from nicegui import ui

from studio.components.cards import placeholder, section
from studio.components.charts import SeriesChart
from studio.components.memory import remember
from studio.components.run_table import labels_of
from studio.pages.results.common import ParticipantChart, Tab, by_number
from studio.theme import MUTED, SERIES

# --------------------------------------------------------------------------------------
# Figures: the curve
# --------------------------------------------------------------------------------------
# What the curve can show: column of ``learning_curves`` -> the y axis.
CURVES = {
    "team_return_mean": "return (team)",
    "per_participant": "return (per participant)",
    "team_money": "money (team, EUR per day)",
}


VERSION = ["target", "experiment", "paradigm", "variant"]  # what the seeds share
LINES = {"key": "Run", "version": "Version (seeds pooled)"}


def _units(curves: pd.DataFrame, labels: dict[str, str], by: str) -> dict[str, list]:
    """What a line stands for, name -> its run keys: each run, or each version."""
    keys = list(dict.fromkeys(curves.key))

    if by == "key":
        return {labels[k]: [k] for k in keys}

    heads = curves.drop_duplicates("key").set_index("key")[VERSION].fillna("")
    names = heads.agg("/".join, axis=1)
    units: dict[str, list] = {}

    for key in keys:
        units.setdefault(names[key], []).append(key)

    return {f"{name} ({len(found)} seeds)": found for name, found in units.items()}


def _spread(rows: pd.DataFrame, value: str) -> pd.DataFrame:
    """A column's mean, min and max over the rows of each environment step."""
    return rows.groupby("env_steps")[value].agg(["mean", "min", "max"])


class CurveChart(SeriesChart):
    """Each run's (or version's) trained policy over environment steps, and its
    baselines at step 0, dashed in its colour (one grey level when every line has the
    same); with ``train``, in return, its training return too, dotted. A version
    pools its seeds: their mean with a band of their min to max.

    Options: ``curves``, ``training`` (``learning_curves`` / ``training_curves``),
    ``labels`` (run key -> name), ``value`` (a column of ``CURVES``), ``train``,
    ``by`` (a key of ``LINES``).
    """

    height = 380
    x_title = "environment steps"

    def draw(self) -> None:
        o = self.o

        if o.curves.empty or o.value not in o.curves:
            return

        self.titles(y=CURVES[o.value])
        units = _units(o.curves, o.labels, o.get("by", "key"))
        colors = {u: SERIES[i % len(SERIES)] for i, u in enumerate(units)}
        training = o.training if o.value in o.training else None

        for unit, keys in units.items():
            rows = o.curves[o.curves.key.isin(keys) & (o.curves.policy == "trained")]
            self._curve(rows, unit, colors[unit], markers=True)

            if o.train and training is not None and not training.empty:
                own = training[training.key.isin(keys)]
                self._curve(own, f"{unit} (training)", colors[unit], dash="dot")

        start = o.curves[(o.curves.env_steps == 0) & (o.curves.policy != "trained")]

        for policy, rows in start.groupby("policy"):
            if rows[o.value].round(9).nunique() == 1:  # the same for every line
                self.level(rows[o.value].iloc[0], f"{policy} (step 0)", color=MUTED)
                continue

            for unit, keys in units.items():
                own = rows[rows.key.isin(keys)][o.value]
                end = o.curves[o.curves.key.isin(keys)].env_steps.max()
                self.line(
                    [0, end],
                    [own.mean()] * 2,
                    f"{unit}: {policy}",
                    colors[unit],
                    dash="dash",
                    width=1,
                )

    def _curve(self, rows: pd.DataFrame, name: str, color: str, **look) -> None:
        """One line: the mean over the keys of ``rows``, with a band when it pools."""
        found = _spread(rows, self.o.value)
        pooled = rows.key.nunique() > 1
        band = (found["min"], found["max"]) if pooled else None
        self.line(found.index, found["mean"], name, color, band=band, **look)


# --------------------------------------------------------------------------------------
# Figures: the learner
# --------------------------------------------------------------------------------------
DASHES = ["solid", "dot", "dash", "dashdot", "longdash", "longdashdot"]
# What the heatmap of an action part can show (a part has some of them).
GRID_STATISTICS = ("mean", "log_std", "entropy", "top")


class LearnerChart(SeriesChart):
    """Module metrics over environment steps: a colour per run, one line per module
    (or their mean), a dash per metric; with ``clip``, each run's gradient clip as
    a level in its colour.

    Options: ``metrics`` (``learner_metrics``), ``names`` (the metrics),
    ``labels``, ``mean`` (the mean over modules), ``clip`` (run key -> clip).
    """

    x_title = "environment steps"
    layout = {"showlegend": True}  # also with one line: which run it is

    def draw(self) -> None:
        o = self.o
        keys = list(dict.fromkeys(o.metrics.key))
        rows = o.metrics[(o.metrics.part == "") & o.metrics.metric.isin(o.names)]

        for i, key in enumerate(keys):
            color = SERIES[i % len(SERIES)]
            own = rows[rows.key == key]

            for dash, name in zip(DASHES, o.names):
                frame = own[own.metric == name]
                suffix = "" if len(o.names) == 1 else f" {name}"

                if o.mean:
                    lines = {"mean": frame.groupby("env_steps").value.mean()}
                else:
                    lines = {
                        m: f.set_index("env_steps").value
                        for m, f in frame.groupby("module")
                    }

                for module, line in lines.items():
                    name_ = f"{o.labels[key]} · {module}{suffix}"
                    self.line(line.index, line, name_, color, dash=dash, width=1.5)

            if (o.get("clip") or {}).get(key) is not None:
                self.level(o.clip[key], color=color)


def _agent_part(module: str, part: str) -> tuple[str, str]:
    """An action part's agent and name: the module and the part, or, for CTCE's
    group (``agent.part``), the agent named in the part."""
    if "." in part:
        agent, name = part.split(".", 1)
        return agent, name

    return module, part


def _part_rows(metrics: pd.DataFrame, key: str) -> pd.DataFrame:
    """Run ``key``'s action-part statistics, each row with its ``agent`` and ``base``,
    the part's name (``_agent_part``)."""
    rows = metrics[(metrics.key == key) & (metrics.part != "")]
    names = [_agent_part(m, p) for m, p in zip(rows.module, rows.part)]

    return rows.assign(agent=[a for a, _ in names], base=[b for _, b in names])


def _part_grid(rows: pd.DataFrame, part: str, metric: str) -> pd.DataFrame:
    """One statistic of one part (from ``_part_rows``): environment steps × agents."""
    found = rows[(rows.base == part) & (rows.metric == metric)]

    return found.pivot_table(index="env_steps", columns="agent", values="value")


def part_statistics(metrics: pd.DataFrame, key: str) -> dict[str, list[str]]:
    """Run ``key``'s action parts, each with the ``GRID_STATISTICS`` it has."""
    rows = _part_rows(metrics, key)

    return {
        part: [s for s in GRID_STATISTICS if s in set(found.metric)]
        for part, found in rows.groupby("base")
    }


class PartsChart(SeriesChart):
    """Every action part of one run over environment steps, in panels stacked on
    one time axis: each statistic's mean over the agents, with a band of their min to
    max, a colour per statistic:

    - a continuous part: its mean (the bounds ±1 dashed), then its log σ (solid; σ
      itself in the hover) and the share of means outside [-1, 1] (dotted, right
      axis);
    - a categorical part: its entropy (solid) and its most likely category's
      probability (dashed).

    Options: ``metrics``, ``key`` (the run), ``labels``.
    """

    TITLES = {
        "mean": "{} · mean",
        "spread": "{} · log σ, share outside [-1, 1]",
        "categorical": "{} · entropy, top probability",
    }
    # A panel's statistics: (name, dash, on the right axis).
    LINES = {
        "mean": [("mean", "solid", False)],
        "spread": [("log_std", "solid", False), ("outside", "dot", True)],
        "categorical": [("entropy", "solid", False), ("top", "dash", False)],
    }
    COLORS = dict(zip(("mean", "log_std", "outside", "entropy", "top"), SERIES))

    def draw(self) -> None:
        rows = _part_rows(self.o.metrics, self.o.key)
        panels = []  # (part, kind)

        for part, found in rows.groupby("base"):
            if "mean" in set(found.metric):
                panels += [(part, "mean"), (part, "spread")]
            else:
                panels.append((part, "categorical"))

        self.panels(
            [self.TITLES[kind].format(part) for part, kind in panels],
            right=[kind == "spread" for _, kind in panels],
        )
        self.height = 230 * len(panels) + 80
        self.after(
            title=dict(text=self.o.labels[self.o.key], font_size=13), showlegend=True
        )
        shown = set()  # statistics already in the legend

        for row, (part, kind) in enumerate(panels, start=1):
            for metric, dash, right in self.LINES[kind]:
                grid = _part_grid(rows, part, metric)

                if grid.empty:
                    continue

                mean, trace = grid.mean(axis=1), {}

                if metric == "log_std":
                    trace = dict(
                        customdata=np.exp(mean.to_numpy()),
                        hovertemplate="log σ %{y:.2f} (σ %{customdata:.4f})"
                        "<extra>%{fullData.name}</extra>",
                    )

                self.line(
                    grid.index,
                    mean,
                    metric,
                    self.COLORS[metric],
                    dash,
                    band=(grid.min(axis=1), grid.max(axis=1)),
                    group=metric,
                    legend=metric not in shown,
                    right=right,
                    row=row,
                    **trace,
                )
                shown.add(metric)

            if kind == "mean":
                self.level(-1.0, row=row)
                self.level(1.0, row=row)
            elif kind == "spread":
                self.level(0.0, dash="dot", row=row)
                self.fig.update_yaxes(
                    range=[0, 1], showgrid=False, row=row, col=1, secondary_y=True
                )

        self.fig.update_xaxes(title="environment steps", row=len(panels), col=1)


class PartGrid(ParticipantChart):
    """One statistic of one action part, agent by agent over training. Options:
    ``metrics``, ``key`` (the run), ``part``, ``metric``."""

    x_title = "environment steps"

    def draw(self) -> None:
        o = self.o
        grid = _part_grid(_part_rows(o.metrics, o.key), o.part, o.metric).T
        grid = grid.reindex(sorted(grid.index, key=by_number))
        o.update(
            rows=list(grid.index),
            columns=list(grid.columns),
            cells=grid.to_numpy(),
            title=o.metric,
            centred=o.metric == "mean",
        )
        super().draw()


# --------------------------------------------------------------------------------------
# The tab
# --------------------------------------------------------------------------------------
class LearningTab(Tab):
    """The return and money curves, the learner's metrics, one run's action parts."""

    label, icon = "Learning", "psychology"

    def read(self, keys: list[str]) -> dict[str, Any]:
        results = self.service.results(keys)
        return {
            "metrics": self.service.learner_metrics(keys),
            "clip": {r.key: r.settings.get("grad_clip") for r in results},
            "curves": self.service.learning_curves(keys),
            "training": self.service.training_curves(keys),
        }

    def empty(self, data: dict[str, Any]) -> bool:
        return data["metrics"].empty

    def build(self, keys: list[str], data: dict[str, Any]) -> None:
        metrics, labels = data["metrics"], labels_of(keys)

        if metrics.empty:
            placeholder("The ticked runs have no metrics yet.", "hourglass_empty")
            return

        modules = metrics[metrics.module != ""].module.nunique()
        mean = ui.switch("Mean over modules", value=modules > 3)
        remember(mean, "results_Learning_mean")
        ui.label(
            "One colour per run, one line per module (agent, or the group in CTCE)."
        ).classes("mls-card-caption")
        charts = []  # the module charts, which the mean switch changes

        with section(
            "Return",
            "The periodic evaluation on the training days, on seeds training did not "
            "use, next to the sampled episodes' return (with exploration), which is "
            "lower while the policy still explores. The baselines at step 0, dashed.",
            "show_chart",
        ):
            chart = CurveChart(
                curves=data["curves"],
                training=data["training"],
                labels=labels,
                value="team_return_mean",
                train=True,
                by="key",
            ).show()
            self.watch(chart, curves="curves", training="training")

            with ui.row().classes("items-center gap-4"):
                chart.select("value", CURVES, "Show").classes("w-64")
                chart.select("by", LINES, "Line per").classes("w-56")
                chart.switch("train", "Training return")

        # Two columns of cards, one per group of learner metrics
        with ui.grid(columns=2).classes("w-full gap-4"):
            for title, names, note in self.service.learner_groups:
                present = [n for n in names if n in set(metrics.metric)]

                if not present:
                    continue

                gradient = "gradients_default_optimizer_global_norm" in present

                with section(title, note):
                    chart = LearnerChart(
                        metrics=metrics,
                        names=present,
                        labels=labels,
                        mean=mean.value,
                        clip=data["clip"] if gradient else None,
                    ).show()
                    charts.append(self.watch(chart, metrics="metrics"))

        mean.on_value_change(lambda e: [c.set(mean=e.value) for c in charts])
        with_parts = list(dict.fromkeys(metrics[metrics.part != ""].key))
        options = {k: labels[k] for k in with_parts}

        with section(
            "Each action part",
            "Every action part of one run, read in the same fixed states every "
            "report: the mean over the agents, with a band of their min to max, of a "
            "continuous part's mean (network units: ±1 are its bounds), its log σ and "
            "the share of means outside the bounds; of a categorical part's entropy "
            "and its most likely category's probability. Under it, one statistic "
            "agent by agent.",
            "tune",
        ):
            if not options:
                ui.label("No per-part statistics in these runs.").classes(
                    "mls-card-caption"
                )
                return

            # The run picker above the charts; it changes both charts' run
            picker = ui.row().classes("w-full")
            chart = PartsChart(
                metrics=metrics, key=next(iter(options)), labels=labels
            ).show()
            self.watch(chart, metrics="metrics")
            chart.memory = "results_Learning_parts"

            with picker:
                run_picker = chart.select("key", options, "Run").classes("w-full")

            self._part_grid(metrics, run_picker)

    def _part_grid(self, metrics: pd.DataFrame, run_picker: ui.select) -> None:
        """The heatmap under the action parts and its selectors, for the picked run."""
        found = part_statistics(metrics, run_picker.value)

        # Selector row: part | statistic
        with ui.row().classes("items-center gap-3"):
            part = ui.select(list(found), value=next(iter(found)), label="Part")
            part.classes("w-40")
            remember(part, "results_Learning_grid_part")
            choices = found[part.value]
            statistic = ui.select(choices, value=choices[0], label="Statistic")
            statistic.classes("w-40")
            remember(statistic, "results_Learning_grid_statistic")

        grid = PartGrid(
            metrics=metrics,
            key=run_picker.value,
            part=part.value,
            metric=statistic.value,
        ).show()
        self.watch(grid, metrics="metrics")

        def follow() -> None:
            parts = part_statistics(grid.o.metrics, run_picker.value)
            kept = part.value if part.value in parts else next(iter(parts))
            part.set_options(list(parts), value=kept)
            names = parts[kept]
            named = statistic.value if statistic.value in names else names[0]
            statistic.set_options(names, value=named)
            grid.set(key=run_picker.value, part=kept, metric=named)

        for field in (run_picker, part, statistic):
            field.on_value_change(follow)
