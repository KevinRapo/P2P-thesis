"""Results → Learning: did it learn? Everything here is on the training days. The
training return next to the periodic evaluation (on seeds training did not use), in
return or money, with the baselines of step 0; from ``metrics.csv``
(``core/runner/results.learner_metrics``), for any environment, per module the policy
and value losses, the critic's explained variance, the entropy, the KL of each update
and the gradient norm against the run's clip; and one run's action parts, each one's
distribution over training. Every chart follows the live view.
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
from studio.pages.results.common import Tab
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


class CurveChart(SeriesChart):
    """Each run's trained policy over environment steps, and its baselines at step 0,
    dashed in its colour (one grey level when every run has the same); with
    ``train``, in return, its training return too, dotted.

    Options: ``curves``, ``training`` (``learning_curves`` / ``training_curves``),
    ``labels`` (run key -> name), ``value`` (a column of ``CURVES``), ``train``.
    """

    height = 380
    x_title = "environment steps"

    def draw(self) -> None:
        o = self.o

        if o.curves.empty or o.value not in o.curves:
            return

        self.titles(y=CURVES[o.value])
        keys = list(dict.fromkeys(o.curves.key))
        colors = {k: SERIES[i % len(SERIES)] for i, k in enumerate(keys)}

        for key in keys:
            rows = o.curves[(o.curves.key == key) & (o.curves.policy == "trained")]
            self.line(
                rows.env_steps, rows[o.value], o.labels[key], colors[key], markers=True
            )

            if o.train and o.value in o.training and not o.training.empty:
                own = o.training[o.training.key == key]
                name = f"{o.labels[key]} (training)"
                self.line(own.env_steps, own[o.value], name, colors[key], dash="dot")

        start = o.curves[(o.curves.env_steps == 0) & (o.curves.policy != "trained")]

        for policy, rows in start.groupby("policy"):
            if rows[o.value].round(9).nunique() == 1:  # the same for every run
                self.level(rows[o.value].iloc[0], f"{policy} (step 0)", color=MUTED)
                continue

            for _, row in rows.iterrows():
                end = o.curves[o.curves.key == row.key].env_steps.max()
                name = f"{o.labels[row.key]}: {policy}"
                y = [row[o.value]] * 2
                self.line([0, end], y, name, colors[row.key], dash="dash", width=1)


# --------------------------------------------------------------------------------------
# Figures: the learner
# --------------------------------------------------------------------------------------
DASHES = ["solid", "dot", "dash", "dashdot", "longdash", "longdashdot"]


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


class PartsChart(SeriesChart):
    """Every action part of one run over environment steps, in panels stacked on
    one time axis, a colour per agent (the same in every panel):

    - a continuous part: its mean with a band of ±σ (the bounds ±1 dashed), then
      its log σ (solid; σ itself in the hover) and the share of means outside
      [-1, 1] (dotted, right axis);
    - a categorical part: its entropy (solid) and its most likely category's
      probability (dashed).

    Options: ``metrics``, ``key`` (the run), ``labels``.
    """

    TITLES = {
        "mean": "{} · mean ± σ",
        "spread": "{} · log σ, share outside [-1, 1]",
        "categorical": "{} · entropy, top probability",
    }

    def draw(self) -> None:
        metrics, key = self.o.metrics, self.o.key
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

        self.panels(
            [self.TITLES[kind].format(part) for part, kind in panels],
            right=[kind == "spread" for _, kind in panels],
        )
        self.height = 230 * len(panels) + 80
        self.after(title=dict(text=self.o.labels[key], font_size=13), showlegend=True)
        shown = set()  # agents already in the legend

        for row, (part, kind) in enumerate(panels, start=1):
            for agent, stats in series[part].items():
                look = dict(color=colors[agent], group=agent, row=row)
                look["legend"] = agent not in shown
                shown.add(agent)

                if kind == "mean":
                    mean, sigma = stats["mean"], stats["log_std"].pipe(np.exp)
                    band = (mean - sigma, mean + sigma)
                    self.line(mean.index, mean, agent, band=band, **look)
                elif kind == "spread":
                    log_std = stats["log_std"]
                    self.line(
                        log_std.index,
                        log_std,
                        agent,
                        customdata=np.exp(log_std.to_numpy()),
                        hovertemplate="log σ %{y:.2f} (σ %{customdata:.4f})"
                        "<extra>%{fullData.name}</extra>",
                        **look,
                    )

                    if "outside" in stats:
                        look["legend"] = False
                        out = stats["outside"]
                        self.line(out.index, out, agent, dash="dot", right=True, **look)
                else:
                    for name, dash in (("entropy", "solid"), ("top", "dash")):
                        if name in stats:
                            values = stats[name]
                            self.line(values.index, values, agent, dash=dash, **look)
                            look["legend"] = False

            if kind == "mean":
                self.level(-1.0, row=row)
                self.level(1.0, row=row)
            elif kind == "spread":
                self.level(0.0, dash="dot", row=row)
                self.fig.update_yaxes(
                    range=[0, 1], showgrid=False, row=row, col=1, secondary_y=True
                )

        self.fig.update_xaxes(title="environment steps", row=len(panels), col=1)


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
            ).show()
            self.watch(chart, curves="curves", training="training")

            with ui.row().classes("items-center gap-4"):
                chart.select("value", CURVES, "Show").classes("w-64")
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
            "Every action part of one run, every agent in its own colour, read in "
            "the same fixed states every report: a continuous part's mean ± σ "
            "(network units: ±1 are its bounds), then its log σ and the share of "
            "means outside the bounds; a categorical part's entropy and its most "
            "likely category's probability.",
            "tune",
        ):
            if not options:
                ui.label("No per-part statistics in these runs.").classes(
                    "mls-card-caption"
                )
                return

            # The run picker above the chart; it changes the chart's run
            picker = ui.row().classes("w-full")
            chart = PartsChart(
                metrics=metrics, key=next(iter(options)), labels=labels
            ).show()
            self.watch(chart, metrics="metrics")
            chart.memory = "results_Learning_parts"

            with picker:
                chart.select("key", options, "Run").classes("w-full")
