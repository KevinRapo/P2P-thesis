"""Results → Validation: is the learned policy any good, and can that be trusted?

The trained policy against the zero and net-position baselines: on the periodic
evaluation during training (the training days, on seeds training did not use), on
every held-out test day at the end (the difference paired per day), and each
configuration over its training seeds; with the settings that differ between the
ticked runs. The evaluation and held-out charts follow the live view.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from studio.components.cards import key_values, section
from studio.components.charts import Chart, SeriesChart
from studio.components.run_table import cell, labels_of
from studio.pages.results.common import BASELINES, Tab, frame_table
from studio.theme import MUTED, SERIES

# The configurations over their seeds (``seed_groups``), as shown.
GROUP_COLUMNS = [
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
]


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


# --------------------------------------------------------------------------------------
# The tab
# --------------------------------------------------------------------------------------
class ValidationTab(Tab):
    """The runs, the evaluation during training, the held-out days, the seeds."""

    label, icon = "Validation", "verified"

    def read(self, keys: list[str]) -> dict[str, Any]:
        s = self.service
        return {
            "differs": s.differing_settings(keys),
            "results": s.results(keys),
            "curves": s.learning_curves(keys),
            "training": s.training_curves(keys),
            "days": s.heldout_days(keys),
            "groups": s.seed_groups(keys),
        }

    def build(self, keys: list[str], data: dict[str, Any]) -> None:
        labels = labels_of(keys)
        self._runs(keys, data)

        with section(
            "During training",
            "Each run's trained policy on the periodic evaluation episodes: the "
            "training days, on seeds training did not use; its baselines at step 0, "
            "dashed in its colour (one grey line when every run's is the same).",
            "show_chart",
        ):
            if data["curves"].empty:
                ui.label("No evaluation recorded yet.").classes("mls-card-caption")

            chart = LearningChart(
                curves=data["curves"],
                training=data["training"],
                labels=labels,
                per=False,
                train=False,
            ).show()
            self.watch(chart, curves="curves", training="training")

            with ui.row().classes("gap-4"):
                chart.switch("per", "Per participant")
                chart.switch(
                    "train", "Training return (the sampled episodes while learning)"
                )

        with section(
            "On the test days",
            "Every held-out test day: the trained policy minus each baseline on the "
            "same day (above 0: better). Written when a run has finished.",
            "leaderboard",
        ):
            chart = HeldoutChart(days=data["days"], labels=labels).show()
            self.watch(chart, days="days")

        with section(
            "Over the seeds",
            "Each configuration over its training seeds: the seeds' held-out means, "
            "their spread (std over seeds, 0 with one), and the settings that differ "
            "inside a group (it should be none).",
            "stacked_line_chart",
        ):
            frame_table(data["groups"], GROUP_COLUMNS)

    @staticmethod
    def _runs(keys: list[str], data: dict[str, Any]) -> None:
        """The settings that differ, and one run's settings on demand."""
        with section("The runs", f"{len(keys)} ticked", "list"):
            shown = [d for d in data["differs"] if d != "seed"]
            ui.label(
                "Settings that differ (their full saved values): "
                + (", ".join(shown) or "none")
            ).classes("text-body2")
            results = {r.key: r for r in data["results"]}

            def show(key: str) -> None:
                box.clear()
                result = results[key]
                shown = {k: cell(v) for k, v in result.labels.items() if v is not None}

                if result.state:
                    shown["state"] = result.state.state
                    shown["env steps"] = (
                        f"{result.state.env_steps:,} / {result.state.budget or '?'}"
                    )

                with box:
                    key_values(shown)

                    for name, title in (
                        ("overrides", "Training settings"),
                        ("model", "Model"),
                    ):
                        if result.settings.get(name):
                            with ui.expansion(title, icon="tune").classes("w-full"):
                                key_values(
                                    {
                                        k: cell(v)
                                        for k, v in result.settings[name].items()
                                    }
                                )

            ui.select(
                labels_of(keys),
                label="One run's settings",
                on_change=lambda e: show(e.value),
            ).classes("w-full")
            box = ui.column().classes("w-full")  # under the picker, filled by show
