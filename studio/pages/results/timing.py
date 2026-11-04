"""Results → Learning → Timing: where a run's time goes. From ``metrics.csv`` (RLlib's
timers per progress report, ``core/runner/results.iteration_timing``) and ``run.json``
(the run's stages, ``core/runner/results.run_timings``): one training call split into
sampling in the env runners, the sampling overhead, the learner update and the rest;
each timer over training, run against run; the throughput; and each run's total time
by stage. RLlib's timers are smoothed means, so a call's parts are close, not exact.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nicegui import ui

from studio.components.cards import section
from studio.components.charts import SeriesChart, rgba
from studio.theme import SERIES

# One training call, in the order they stack: column -> what it is.
CALL_PARTS = {
    "runners_s": "Sampling in the runners",
    "sampling_overhead_s": "Sampling overhead",
    "learner_call_s_mean": "Learner update",
    "unaccounted_s": "Rest of the call",
}
# The timers a run can be compared on, nested as they are measured: the call holds the
# driver's sampling, the learner update and the rest; the sampling holds the runners'.
TIMERS = {
    "train_call_s": "whole training call",
    "sampling_s_mean": "sampling (driver's timer)",
    "runners_s": "↳ of which sampling in the runners",
    "learner_call_s_mean": "learner update",
    "unaccounted_s": "rest of the call",
}
# A run's stages, in the order they happen.
STAGES = {
    "ray_init_s": "Ray start-up",
    "build_s": "Build",
    "train_calls_s": "Training calls",
    "evaluation_s": "Evaluation",
    "checkpoint_s": "Checkpoint",
    "other_s": "Tables and statistics",
}


class CallSplitChart(SeriesChart):
    """One run's training call over environment steps, stacked: sampling in the env
    runners, the overhead around it, the learner update and the rest. With ``share``,
    each part as a share of the call.

    Options: ``timing`` (``iteration_timing``), ``key`` (the run), ``share``.
    """

    height = 340
    x_title = "environment steps"

    def draw(self) -> None:
        o = self.o
        rows = o.timing[o.timing.key == o.key].sort_values("env_steps")

        if rows.empty:
            return

        self.titles(y="share of the call (%)" if o.share else "seconds per iteration")

        for column, name in CALL_PARTS.items():
            color = SERIES[list(CALL_PARTS).index(column)]
            self.line(
                rows.env_steps,
                rows[column].fillna(0.0),
                name,
                color,
                width=0.5,
                stackgroup="call",
                fillcolor=rgba(color, 0.65),
                **({"groupnorm": "percent"} if o.share else {}),
            )


class TimerChart(SeriesChart):
    """One timer over environment steps, a line per run.

    Options: ``timing``, ``labels`` (run key -> name), ``value`` (a key of
    ``TIMERS``).
    """

    height = 340
    x_title = "environment steps"

    def draw(self) -> None:
        o = self.o

        if o.timing.empty or o.value not in o.timing:
            return

        name = TIMERS[o.value].lstrip(" ↳").removeprefix("of which ")
        self.titles(y=f"{name} (s per iteration)")

        for i, (key, rows) in enumerate(o.timing.groupby("key", sort=False)):
            rows = rows.sort_values("env_steps")
            self.line(
                rows.env_steps, rows[o.value], o.labels[key], SERIES[i % len(SERIES)]
            )


class ThroughputChart(SeriesChart):
    """Environment steps per second of training calls so far, a line per run.

    Options: ``timing``, ``labels``.
    """

    height = 300
    x_title = "environment steps"

    def draw(self) -> None:
        o = self.o
        self.titles(y="environment steps per second")

        for i, (key, rows) in enumerate(o.timing.groupby("key", sort=False)):
            rows = rows.sort_values("env_steps")
            self.line(
                rows.env_steps,
                rows.sampled_steps_per_train_s,
                o.labels[key],
                SERIES[i % len(SERIES)],
            )


class StagesChart(SeriesChart):
    """Each run's whole time by stage, bars stacked: Ray's start-up, the build, the
    training calls, the evaluations, the checkpoint and the rest.

    Options: ``stages`` (``run_timings``), ``labels``.
    """

    stacked = True
    x_title = "seconds"

    def draw(self) -> None:
        o = self.o

        if o.stages.empty:
            self.after(
                annotations=[
                    dict(
                        text="No finished run yet: a run's stages are known when it "
                        "has finished.",
                        showarrow=False,
                        xref="paper",
                        yref="paper",
                        x=0.5,
                        y=0.5,
                    )
                ]
            )
            return

        names = [o.labels[k] for k in o.stages.key]
        self.height = 60 * len(names) + 120

        for i, (column, name) in enumerate(STAGES.items()):
            self.bars(
                o.stages[column].fillna(0.0),
                names,
                name,
                SERIES[i % len(SERIES)],
                orientation="h",
            )

        self.after(yaxis=dict(autorange="reversed"), showlegend=True)


def build_timing(tab: Any, data: dict[str, Any], labels: dict[str, str]) -> None:
    """The Timing panel's cards, for ``tab`` (a ``Tab``, which refreshes them)."""
    timing: pd.DataFrame = data["timing"]

    if timing.empty:
        ui.label("The ticked runs saved no timers yet.").classes("mls-card-caption")
        return

    keys = list(dict.fromkeys(timing.key))
    options = {k: labels[k] for k in keys}

    with section(
        "Where an iteration's time goes",
        "One run's training call split into sampling in the env runners (the market "
        "and the policy), the overhead around it (waiting for the slowest runner, "
        "getting the episodes back), the learner update and the rest of the call. "
        "RLlib's timers are smoothed means, so the parts are close, not exact.",
        "pie_chart",
    ):
        chart = CallSplitChart(timing=timing, key=keys[0], share=False).show()
        tab.watch(chart, timing="timing")
        chart.memory = "results_Timing_split"

        with ui.row().classes("items-center gap-4"):
            chart.select("key", options, "Run").classes("w-96")
            chart.switch("share", "Share of the call")

    with section(
        "Time per iteration",
        "One timer for every run: what a call costs as training goes on, and which "
        "run is slower. The call is the driver's sampling, the learner update and the "
        "rest; the runners' sampling (↳) is part of the driver's, so do not add the "
        "two. Runs with larger batches or more epochs take longer "
        "per learner update.",
        "show_chart",
    ):
        chart = TimerChart(timing=timing, labels=labels, value="train_call_s").show()
        tab.watch(chart, timing="timing")
        chart.memory = "results_Timing_timer"
        with ui.row().classes("w-full items-center gap-3"):
            chart.select("value", TIMERS, "Show").classes("w-64")
            chart.hover_select().classes("w-40")

    with section(
        "Throughput",
        "Environment steps per second of training calls so far (the evaluations are "
        "not counted): what a budget costs.",
        "speed",
    ):
        chart = ThroughputChart(timing=timing, labels=labels).show()
        tab.watch(chart, timing="timing")

    with section(
        "Where a run's time went",
        "Each run's whole time by stage, from its record: Ray's start-up, building "
        "the algorithm, the training calls, the evaluations, the checkpoint and the "
        "rest (the tables and the action parts' statistics).",
        "timer",
    ):
        chart = StagesChart(stages=data["stages"], labels=labels).show()
        tab.watch(chart, stages="stages")
