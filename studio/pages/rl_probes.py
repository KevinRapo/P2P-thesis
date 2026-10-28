"""RL probes: how the learner of the ticked runs behaved, and for a probe run what
the probe is and what it scored.

The runs are picked in the same table as on the Results page
(``studio/components/run_table.py``), with two more columns for a probe run: its
probe and its result. Moved here from the Results page's Learning tab (26 Oct
2026), so the probes and the learner they check are read in one place.

Probes: for the ticked probe runs, a summary (probe × paradigm, each run's result:
PASS or FAIL with its worst error over its tolerance, or 8b's share of coordinating
pairs), then one probe run at a time: what the probe tests, its setup, the exact
answer, what a correct learner shows, the market feature it stands for
(``core/runner/probe_runs.py``), and its checks (``checks.csv``: expected
against what the trained networks give). A run is scored by
``probe_check.score_to_file``; an unscored run shows its learner only.

Learning: from the ticked runs' ``metrics.csv``
(``core/runner/results.learner_metrics``), for any environment: the training
return; per module the policy and value losses, the critic's explained variance,
the entropy, the KL of each update and the gradient norm against the run's clip;
and one action part at a time, its distribution over training.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from nicegui import run, ui

from core.runner.probe_runs import ProbeRunInfo
from studio.adapters.results_service import ResultsService
from studio.adapters.validation_service import ValidationService
from studio.components.cards import key_values, placeholder, section
from studio.components.charts import styled
from studio.components.run_table import RUN_COLUMNS, RunTable, labels_of
from studio.components.tables import data_table
from studio.layout import shell
from studio.state import services
from studio.theme import SERIES

SHOW_TESTS = "rl_probes_show_tests"  # app.storage.user key
# The run table's columns: what the run was, its probe and result, its state.
COLUMNS = RUN_COLUMNS[:7] + [("probe", "Probe"), ("result", "Result"), RUN_COLUMNS[7]]


# --------------------------------------------------------------------------------------
# Figures: the learner
# --------------------------------------------------------------------------------------
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


# --------------------------------------------------------------------------------------
# The probes: a summary of the ticked probe runs, one run's probe and checks
# --------------------------------------------------------------------------------------
def _result_text(info: ProbeRunInfo) -> str:
    """``PASS 0.42``, ``FAIL 2.66``, ``share 0.50`` (8b), or ``not scored``."""
    if info.result is None:
        return "not scored"

    if info.result == "MEASURED":
        return f"share {info.worst:.2f}"

    return f"{info.result} {info.worst:.2f}"


def _probe_order(probe: str) -> tuple[int, str]:
    return int(probe.rstrip("ab")), probe


def _summary(found: dict[str, ProbeRunInfo]) -> None:
    """Probe × paradigm: every ticked run's result, by seed (and budget scale)."""
    cells: dict[tuple[str, str], list[tuple[float, int, str]]] = {}
    names = {}

    for info in found.values():
        tag = f"s{info.seed}" + ("" if info.scale == 1 else f" ×{info.scale:g}")
        cells.setdefault((info.probe, info.paradigm), []).append(
            (info.scale, info.seed, f"{_result_text(info)} ({tag})")
        )
        names[info.probe] = info.about.name if info.about else ""

    paradigms = sorted({p for _, p in cells})
    rows = [
        {"probe": f"{probe} · {names[probe]}"}
        | {
            p: " · ".join(text for *_, text in sorted(cells.get((probe, p), [])))
            for p in paradigms
        }
        for probe in sorted(names, key=_probe_order)
    ]
    data_table(
        rows,
        [("probe", "Probe")] + [(p, p.upper()) for p in paradigms],
        row_key="probe",
        pagination=15,
    )
    ui.label(
        "PASS or FAIL with the worst error over its tolerance (above 1 fails; inf: "
        "a wrong category); 8b: the share of pairs that coordinate (measured, not "
        "judged). ×2, ×4: an escalated run with that many times the budget."
    ).classes("mls-card-caption")


def _probe_card(label: str, info: ProbeRunInfo) -> None:
    about = info.about

    # One card: what the probe tests, then its check table and a note
    with section(
        f"Probe {info.probe}" + (f" · {about.name}" if about else ""),
        f"{label}: {info.paradigm.upper()}, seed {info.seed}"
        + ("" if info.scale == 1 else f", ×{info.scale:g} budget")
        + f" · {_result_text(info)}",
        "science",
    ):
        if about:
            key_values(
                {
                    "Tests": about.tests,
                    "Setup": about.setup,
                    "Exact answer": about.answer,
                    "A correct learner": about.expect,
                    "In the market": about.market,
                }
            )

        if info.checks is None:
            ui.label(
                "Not scored yet: probe_check.score_to_file writes its checks."
            ).classes("mls-card-caption")
            return

        rows = [
            {
                "n": n,
                "state": row.state,
                "output": row.output,
                "expected": round(float(row.expected), 4),
                "got": round(float(row.got), 4),
                "tolerance": round(float(row.tolerance), 4),
                "result": "PASS" if bool(row.ok) else "FAIL",
                "result_color": "positive" if bool(row.ok) else "negative",
            }
            for n, row in enumerate(info.checks.itertuples())
        ]
        data_table(
            rows,
            [
                ("state", "State"),
                ("output", "Output"),
                ("expected", "Expected"),
                ("got", "Trained network"),
                ("tolerance", "Tolerance"),
                ("result", "Result"),
            ],
            row_key="n",
            pagination=15,
            badge_columns={"result": "result_color"},
        )
        ui.label(
            "Read from the trained networks in the probe's check states, not from "
            "the return. A tolerance of 0 is a category, which must be exact."
        ).classes("mls-card-caption")


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
class ProbesView:
    """The run table, the ticked probe runs, and the learner of the ticked runs.

    Args:
        service: The Results service.
        validation: The Validation service (the probe runs' probe and score).
    """

    def __init__(self, service: ResultsService, validation: ValidationService) -> None:
        self.service = service
        self.validation = validation
        self._drawn = {"probes": 0, "learning": 0}  # latest draws

        # The run table at the top, with a tick box per run
        self.table = RunTable(
            service,
            self._selected,
            SHOW_TESTS,
            columns=COLUMNS,
            read=validation.rl_overview,
        )

        # Tab bar under it: Probes | Learning
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            ui.tab("probes", label="Probes", icon="science")
            ui.tab("learning", label="Learning", icon="psychology")

        with ui.tab_panels(tabs, value="probes").classes("w-full bg-transparent"):
            # Probes tab: drawn by _show_probes()
            with ui.tab_panel("probes").classes("p-0 gap-4"):
                self.probes = ui.column().classes("w-full gap-4")

            # Learning tab: drawn by _show_learning()
            with ui.tab_panel("learning").classes("p-0 gap-4"):
                self.learning = ui.column().classes("w-full gap-4")

    async def load(self) -> None:
        await self.table.load()
        await self._selected()  # the placeholders

    @property
    def selected(self) -> list[str]:
        return self.table.selected

    async def _selected(self) -> None:
        await self._show_probes()
        await self._show_learning()

    def _draw(self, tab: str) -> int:
        """A new draw of ``tab``: its number. A draw that waited for files and is no
        longer the latest leaves the tab to the newer one."""
        self._drawn[tab] += 1
        return self._drawn[tab]

    # --- Probes: the ticked probe runs ------------------------------------------------
    async def _show_probes(self) -> None:
        keys = list(self.selected)
        draw = self._draw("probes")
        self.probes.clear()
        found = await run.io_bound(self.validation.probe_runs, keys)

        if draw != self._drawn["probes"]:  # ticked again meanwhile
            return

        # The Probes tab, top to bottom: summary card, probe-run picker, that run's
        # probe card
        with self.probes:
            if not found:
                placeholder(
                    "Tick probe runs in the table (an experiment probes_<preset>) to "
                    "see their probes and checks; any run's learner is in the "
                    "Learning tab.",
                    "science",
                )
                return

            labels = labels_of(list(found))

            with section(
                "The ticked probe runs",
                f"{len(found)} of {len(keys)} ticked runs are probe runs",
                "grid_view",
            ):
                _summary(found)

            order = sorted(
                found,
                key=lambda k: (
                    _probe_order(found[k].probe),
                    found[k].paradigm,
                    found[k].seed,
                    found[k].scale,
                ),
            )
            options = {k: f"{labels[k]} · {_result_text(found[k])}" for k in order}
            chosen = ui.select(options, value=order[0], label="Probe run").classes(
                "w-full"
            )
            # The chosen run's probe card, redrawn by show()
            card = ui.column().classes("w-full")

            def show() -> None:
                card.clear()

                with card:
                    _probe_card(labels[chosen.value], found[chosen.value])

            chosen.on_value_change(lambda _: show())
            show()

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

        # The Learning tab, top to bottom: the mean switch with a note, training
        # return, a two-column grid of learner charts, the action parts
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

            # Two columns of cards, one per group of learner metrics
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


def page() -> None:
    """The runs, read once when the page opens."""
    s = services()

    with shell(
        "rl_probes",
        "RL probes",
        "The RL probes' runs: what each probe is and what it scored, and how the "
        "learner of any ticked run behaved. Runs of the clusters after Sync results "
        "on the Runs page.",
    ):
        view = ProbesView(s.results, s.validation)
        ui.timer(0.05, view.load, once=True)
