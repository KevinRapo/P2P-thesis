"""Results → Validation: how good is each version on the test days?

The tab opened first: any ticked runs in one table, a row per what the reader picks and
a column per headline indicator (``core/runner/indicators.py``), as values, against
each run's own baseline, or as differences from a reference row; and the gain per test
day. A row opens in Market or Grid, on its median seed. Each participant's gain shows who
wins and who loses at any size.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nicegui import ui

from core.runner import indicators
from core.runner.indicators import INDICATORS
from studio.components.cards import key_values, section
from studio.components.charts import Chart
from studio.components.choices import checkboxes
from studio.components.memory import remember
from studio.components.run_table import cell, labels_of
from studio.components.tables import data_table
from studio.pages.results.common import BASELINES, Tab, indicator_rows, metric_card
from studio.theme import MUTED, SERIES

HEADLINES = {i.name: i for i in INDICATORS if i.headline}
# What grows with the number of participants, so ``Per participant`` divides it.
AMOUNTS = {i.name for i in INDICATORS if i.unit in ("EUR", "kWh")}
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
}
GAINS = {"gain_net_position": "net_position"}
# The references of the overview's own table, by VTI from the top down (ceiling 1, the
# rule, non_p2p 0).
SHOWN = ("ceiling", "net_position", "non_p2p")
# The indices per test day, each day its own horizon, and the money they are made of:
# the metrics of "On the test days" (the overview shows them over the test period).
PER_DAY = (
    "vti_day",
    "pi_day",
    "ei_day",
    "energy_balance_index",
    "peak_to_average",
    "self_sufficiency_index",
    "team_money",
    "gain_net_position",
    "stored_change_kwh",
)


# --------------------------------------------------------------------------------------
# The overview
# --------------------------------------------------------------------------------------
def records_of(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """A table's rows for ``data_table``: its cells as text, a row key ``_row``."""
    return [
        {"_row": i} | {f: "" if pd.isna(v) else str(v) for f, v in row.items()}
        for i, row in enumerate(frame.to_dict("records"))
    ]


def titled(name: str) -> str:
    """An indicator's label, with its unit in brackets when it has one."""
    found = next(i for i in INDICATORS if i.name == name)

    return f"{found.label} ({found.unit})" if found.unit else found.label


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

        # Controls: a row per | view | difference from | per participant
        with ui.row().classes("w-full items-center gap-3"):
            self.rows = checkboxes(
                ui.select(
                    ROWS, value=row_columns(table), multiple=True, label="A row per"
                )
            ).classes("w-96")
            self.view = ui.select(VIEWS, value="value", label="Show").classes("w-64")
            self.reference = ui.select(
                {"": "Nothing"}, value="", label="Difference from"
            ).classes("w-96")
            self.per_participant = ui.switch("Per participant")

        remember(self.rows, "results_rows", lambda rows: set(rows) <= set(ROWS))
        remember(self.view, "results_view")
        remember(self.per_participant, "results_per_participant")
        self.box = ui.column().classes("w-full")

        # Open a row: which | Market | Grid
        with ui.row().classes("w-full items-center gap-3"):
            self.closer = ui.select([], label="Look closer at").classes("w-96")

            for name in ("Market", "Grid"):
                ui.button(name, on_click=lambda n=name: self.open(n)).props(
                    "outline no-caps dense"
                )

        for field in (self.rows, self.view, self.reference, self.per_participant):
            field.on_value_change(self.draw)

        self.draw()

    def set(self, table: pd.DataFrame) -> None:
        """The table read again, by the live view."""
        self.table = table
        self.draw()

    def _scaled(self) -> pd.DataFrame:
        """The table, with ``Per participant`` its ``AMOUNTS`` divided by the run's
        participants (missing for a run that does not say how many)."""
        table = self.table

        if not self.per_participant.value:
            return table

        each = table.value / table.participants.where(table.participants > 0)

        return table.assign(
            value=table.value.where(~table.indicator.isin(AMOUNTS), each)
        )

    def _labelled(self) -> pd.DataFrame:
        """The scaled table with a ``row`` column: the row's name."""
        rows = list(self.rows.value or ["key"])
        table = self._scaled()

        return table.assign(row=table[rows].astype(str).agg(" · ".join, axis=1))

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
        columns += [(n, self._heading(n, i)) for n, i in HEADLINES.items()]

        data_table(
            records_of(frame), columns, row_key="_row", pagination=max(15, len(frame))
        )

        # The baselines in a table of their own under the runs, the same columns:
        # sorting the runs leaves them where they are.
        if baselines:
            found = self._baselines(rows[0])

            if len(found):
                ui.label("Baselines and references, by VTI").classes(
                    "text-body2 text-weight-medium q-mt-sm"
                )
                data_table(records_of(found), columns, row_key="_row", pagination=0)

    def _heading(self, name: str, indicator: indicators.Indicator) -> str:
        """A headline's column heading."""
        each = self.per_participant.value and name in AMOUNTS
        heading = f"{indicator.label} {indicator.unit}".strip()

        return f"{heading} per participant" if each else heading

    def _baselines(self, column: str) -> pd.DataFrame:
        """A row per baseline, days and prices, named in the table's first column."""
        found = indicators.baselines(self._scaled())
        found = found[found.indicator.isin(HEADLINES) & found.policy.isin(SHOWN)]
        groups = ["policy", *indicators.PLAYED_ON]
        table = found.pivot(index=groups, columns="indicator", values="value")
        table = table.reset_index()
        differ = [c for c in indicators.PLAYED_ON if table[c].nunique(dropna=False) > 1]
        name = table[["policy", *differ]].astype(str).agg(" · ".join, axis=1)
        # From the top of the scale down, by VTI (the order of SHOWN on a tie)
        table = table.assign(
            _shown=table.policy.map(SHOWN.index),
            _vti=table["vti"] if "vti" in table else float("nan"),  # older runs
        )
        table = table.sort_values(["_vti", "_shown"], ascending=[False, True])
        values = table.reindex(columns=list(HEADLINES)).map(lambda v: cell(float(v)))

        return values.assign(**{column: name.loc[table.index]})

    def open(self, tab: str) -> None:
        """Select the row's median seed by team money, and go to ``tab``."""
        labelled = self._labelled()
        row = labelled[labelled.row == self.closer.value]
        money = row[(row.indicator == "team_money") & (row.policy == "trained")]
        means = money.groupby("key").value.mean().sort_values()

        if len(means):
            self.tab.selection.run = means.index[len(means) // 2]
            self.tab.selection.open(tab)


def setting(value: Any) -> str:
    """A setting as the run was given it: in full (a learning rate of 0.0003 is not
    rounded to 0), "not set" for nothing and "none" for an empty list."""
    if value is None:
        return "not set"

    if isinstance(value, (list, tuple)):
        return ", ".join(map(str, value)) if value else "none"

    if isinstance(value, dict):
        return ", ".join(f"{k}: {setting(v)}" for k, v in value.items()) or "none"

    return str(value)


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


class ParticipantGainChart(Chart):
    """Per run, each participant's gain over its own non-P2P money, as a box with
    every participant a
    point named in its hover. Options: ``gains`` (``participant_gains``), ``labels``."""

    height = 380
    y_title = "EUR per test day, trained − on its own"
    layout = {"hovermode": "closest"}

    def draw(self) -> None:
        o = self.o

        if o.gains.empty:
            return

        self.fig.add_box(
            x=[o.labels[k] for k in o.gains.key],
            y=o.gains.gain,
            text=o.gains.agent + " (" + o.gains.group + ")",
            hovertemplate="%{text}: %{y:.3f}<extra></extra>",
            hoveron="points",
            boxpoints="all",
            jitter=0.3,
            marker_color=SERIES[1],
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
    """What differs, the overview, the gain per day and per participant, one run's
    settings."""

    label, icon = "Validation", "verified"

    def read(self, keys: list[str]) -> dict[str, Any]:
        s = self.service
        table = s.day_indicators(keys)

        return {
            "differs": s.differing_settings(keys),
            "results": s.results(keys),
            "table": table,
            "days": gains(table),
            "per_day": indicator_rows(table[table.indicator.isin(PER_DAY)])
            if len(table)
            else table,
            "gains": s.participant_gains(keys),
        }

    def empty(self, data: dict[str, Any]) -> bool:
        return data["table"].empty

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

        metric_card(
            self,
            "On the test days",
            "Each test day as its own horizon: VTI, PI and EI against that day's "
            "ceiling and non-P2P, the technical indices of the day, and the money",
            "per_day",
            data,
            labels_of(keys),
            {name: titled(name) for name in PER_DAY},
        )

        with section(
            "Gain per test day",
            "Every test day: the trained policy's money minus each baseline's on the "
            "same day (above 0: better). Written when a run has finished.",
            "leaderboard",
        ):
            chart = GainChart(days=data["days"], labels=labels_of(keys)).show()
            self.watch(chart, days="days")

        with section(
            "Per participant",
            "Each participant's mean bill over the test days minus its own non-P2P "
            "money (above 0: better off than alone); hover over a point for who it is.",
            "groups",
        ):
            chart = ParticipantGainChart(
                gains=data["gains"], labels=labels_of(keys)
            ).show()
            self.watch(chart, gains="gains")

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
                                        k: setting(v)
                                        for k, v in result.settings[name].items()
                                    }
                                )

            ui.select(
                labels_of(keys), label="Run", on_change=lambda e: show(e.value)
            ).classes("w-full")
            ui.label(
                "As the run was given them. Not set: the default, or for the scales "
                "a value computed from the training days; none: an empty list (no "
                "layers)."
            ).classes("mls-card-caption")
            box = ui.column().classes("w-full")  # under the picker, filled by show
