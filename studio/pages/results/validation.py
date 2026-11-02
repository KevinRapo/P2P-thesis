"""Results → Validation: how good is each version on the test days?

The tab opened first: any ticked runs in one table, a row per what the reader picks and
a column per headline indicator (``core/runner/indicators.py``), as values, against
each run's own baseline, or as differences from a reference row; and the gain per test
day. A row opens in Market or Grid, on its median seed.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nicegui import ui

from core.runner import indicators
from core.runner.indicators import INDICATORS
from studio.components.cards import key_values, section
from studio.components.charts import Chart
from studio.components.memory import remember
from studio.components.run_table import cell, labels_of
from studio.components.tables import data_table
from studio.pages.results.common import BASELINES, Tab
from studio.theme import MUTED, SERIES

HEADLINES = {i.name: i for i in INDICATORS if i.headline}
# What a row can stand for, in the order offered.
ROWS = {
    "key": "Run",
    "experiment": "Experiment",
    "variant": "Variant",
    "paradigm": "Paradigm",
    "reward": "Reward",
    "observation": "Observation",
    "prices": "Prices",
    "peer_charge": "Peer charge",
    "network": "Network",
    "grid_method": "Grid method",
}
VIEWS = {
    "value": "Values",
    "net_position": "Against own net position",
    "zero": "Against own zero",
}
GAINS = {"gain_zero": "zero", "gain_net_position": "net_position"}


# --------------------------------------------------------------------------------------
# The overview
# --------------------------------------------------------------------------------------
def row_columns(table: pd.DataFrame) -> list[str]:
    """What a row stands for by default: the factors that differ, else what names the
    versions, else the run."""
    differs = [c for c in ROWS if c != "key" and table[c].nunique(dropna=False) > 1]

    return (
        [c for c in differs if c not in ("experiment", "variant")] or differs or ["key"]
    )


def number(row: pd.Series) -> str:
    """A cell: the mean over seeds, with its interval or each seed's value."""
    mean = cell(float(row["mean"]))

    if pd.notna(row.get("low")):
        return f"{mean} [{cell(float(row['low']))}, {cell(float(row['high']))}]"

    seeds = row.get("values")

    if isinstance(seeds, list) and len(seeds) > 1:
        return f"{mean} ({', '.join(str(cell(float(v))) for v in seeds)})"

    return str(mean)


def wide(found: pd.DataFrame, rows: list[str]) -> pd.DataFrame:
    """``found`` as a row per ``rows`` and a column per headline, in text."""
    found = found[found.indicator.isin(HEADLINES)]
    text = found.assign(text=found.apply(number, axis=1))
    table = text.pivot(index=rows, columns="indicator", values="text")

    return table.reindex(columns=list(HEADLINES)).reset_index()


class Overview:
    """The table and its controls.

    Args:
        table: ``day_indicators`` of the ticked runs.
        tab: The tab, for the selection.
    """

    def __init__(self, table: pd.DataFrame, tab: "ValidationTab") -> None:
        self.table, self.tab = table, tab

        # Controls: a row per | view | difference from
        with ui.row().classes("w-full items-center gap-3"):
            self.rows = ui.select(
                ROWS, value=row_columns(table), multiple=True, label="A row per"
            ).classes("w-96")
            self.view = ui.select(VIEWS, value="value", label="Show").classes("w-64")
            self.reference = ui.select(
                {"": "Nothing"}, value="", label="Difference from"
            ).classes("w-96")

        remember(self.rows, "results_rows", ROWS)
        remember(self.view, "results_view")
        self.box = ui.column().classes("w-full")

        # Open a row: which | Market | Grid
        with ui.row().classes("w-full items-center gap-3"):
            self.closer = ui.select([], label="Look closer at").classes("w-96")

            for name in ("Market", "Grid"):
                ui.button(name, on_click=lambda n=name: self.open(n)).props(
                    "outline no-caps dense"
                )

        for field in (self.rows, self.view, self.reference):
            field.on_value_change(self.draw)

        self.draw()

    def set(self, table: pd.DataFrame) -> None:
        """The table read again, by the live view."""
        self.table = table
        self.draw()

    def _labelled(self) -> pd.DataFrame:
        """The table with a ``row`` column: the row's name."""
        rows = list(self.rows.value or ["key"])

        return self.table.assign(
            row=self.table[rows].astype(str).agg(" · ".join, axis=1)
        )

    def draw(self) -> None:
        rows = list(self.rows.value or ["key"])
        labelled = self._labelled()
        names = sorted(labelled.row.unique())
        reference = self.reference.value if self.reference.value in names else ""
        self.reference.set_options(
            {"": "Nothing"} | {n: n for n in names}, value=reference
        )
        closer = self.closer.value if self.closer.value in names else names[0]
        self.closer.set_options(names, value=closer)
        self.box.clear()
        failed = self.table[
            (self.table.indicator == "not_converged") & (self.table.value > 0)
        ]

        with self.box:
            if len(failed):
                ui.label(
                    f"{int(failed.value.sum())} steps did not converge: on those "
                    "steps the loading and limits count nothing, so they read low."
                ).classes("text-negative")

            if reference:
                found = indicators.difference(labelled, "row", reference, within=[])
                self._table(found, ["row", "paired"])
            elif self.view.value == "value":
                self._table(
                    indicators.side_by_side(labelled, rows), rows, baselines=True
                )
            else:
                played = indicators.against_baseline(labelled, self.view.value)
                self._table(indicators.side_by_side(played, rows), rows)

    def _table(
        self, found: pd.DataFrame, rows: list[str], baselines: bool = False
    ) -> None:
        if found.empty:
            ui.label("Nothing to compare it with.").classes("mls-card-caption")
            return

        frame = wide(found, rows)
        names = ROWS | {"row": "Row", "paired": "Paired"}
        columns = [(c, names[c]) for c in rows]
        columns += [(n, f"{i.label} {i.unit}".strip()) for n, i in HEADLINES.items()]

        if baselines:
            frame = pd.concat([frame, self._baselines(rows[0])], ignore_index=True)

        records = [
            {"_row": i} | {f: "" if pd.isna(v) else str(v) for f, v in row.items()}
            for i, row in enumerate(frame.to_dict("records"))
        ]
        data_table(records, columns, row_key="_row", pagination=15)

    def _baselines(self, column: str) -> pd.DataFrame:
        """A row per baseline, days and prices, named in the table's first column."""
        found = indicators.baselines(self.table)
        found = found[found.indicator.isin(HEADLINES)]
        groups = ["policy", *indicators.PLAYED_ON]
        table = found.pivot(index=groups, columns="indicator", values="value")
        table = table.reset_index()
        differ = [c for c in indicators.PLAYED_ON if table[c].nunique(dropna=False) > 1]
        name = table[["policy", *differ]].astype(str).agg(" · ".join, axis=1)
        values = table.reindex(columns=list(HEADLINES)).map(lambda v: cell(float(v)))

        return values.assign(**{column: name})

    def open(self, tab: str) -> None:
        """Select the row's median seed by team money, and go to ``tab``."""
        labelled = self._labelled()
        row = labelled[labelled.row == self.closer.value]
        money = row[(row.indicator == "team_money") & (row.policy == "trained")]
        means = money.groupby("key").value.mean().sort_values()

        if len(means):
            self.tab.selection.run = means.index[len(means) // 2]
            self.tab.selection.open(tab)


# --------------------------------------------------------------------------------------
# The gain per day
# --------------------------------------------------------------------------------------
class GainChart(Chart):
    """Per run, the trained policy's money minus each baseline's on every test day, as
    boxes. Options: ``days`` (``gains``), ``labels``."""

    height = 380
    y_title = "EUR per test day"
    layout = {"boxmode": "group", "hovermode": "closest"}

    def draw(self) -> None:
        for i, (column, baseline) in enumerate(GAINS.items()):
            if column in self.o.days:
                self.fig.add_box(
                    x=[self.o.labels[k] for k in self.o.days.key],
                    y=self.o.days[column],
                    name=f"trained − {BASELINES[baseline]}",
                    boxpoints="all",
                    jitter=0.3,
                    marker_color=SERIES[i + 1],
                )

        self.fig.add_hline(y=0, line_color=MUTED)


def gains(table: pd.DataFrame) -> pd.DataFrame:
    """A row per run and test day, a column per gain."""
    if table.empty:
        return pd.DataFrame()

    found = table[(table.policy == "trained") & table.indicator.isin(GAINS)]

    return found.pivot_table(
        index=["key", "day"], columns="indicator", values="value"
    ).reset_index()


# --------------------------------------------------------------------------------------
# The tab
# --------------------------------------------------------------------------------------
class ValidationTab(Tab):
    """What differs, the overview, the gain per day, one run's settings."""

    label, icon = "Validation", "verified"

    def read(self, keys: list[str]) -> dict[str, Any]:
        s = self.service
        table = s.day_indicators(keys)

        return {
            "differs": s.differing_settings(keys),
            "results": s.results(keys),
            "table": table,
            "days": gains(table),
        }

    def build(self, keys: list[str], data: dict[str, Any]) -> None:
        shown = [d for d in data["differs"] if d != "seed"]
        ui.label("These runs differ in: " + (", ".join(shown) or "nothing")).classes(
            "text-body2"
        )

        with section(
            "Overview",
            "Any ticked runs, on their test days. A cell is the mean over seeds, with "
            "each seed's value, or an interval from 5 seeds.",
            "table_chart",
        ):
            if data["table"].empty:
                ui.label("No held-out results yet.").classes("mls-card-caption")
            else:
                self.watch(Overview(data["table"], self), table="table")

        with section(
            "On the test days",
            "Every test day: the trained policy's money minus each baseline's on the "
            "same day (above 0: better). Written when a run has finished.",
            "leaderboard",
        ):
            chart = GainChart(days=data["days"], labels=labels_of(keys)).show()
            self.watch(chart, days="days")

        self._settings(keys, data)

    @staticmethod
    def _settings(keys: list[str], data: dict[str, Any]) -> None:
        """One run's settings on demand."""
        with section("One run's settings", f"{len(keys)} ticked", "list"):
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
                        ("env_config", "Environment settings"),
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
                labels_of(keys), label="Run", on_change=lambda e: show(e.value)
            ).classes("w-full")
            box = ui.column().classes("w-full")  # under the picker, filled by show
