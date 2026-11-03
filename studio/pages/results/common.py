"""What the Results page's tabs share: the tab base, what they have selected, the
chart per test day and a table of a frame.

No chart draws a line per participant: a group is its mean, every participant at
once is a row of a heatmap (``ParticipantChart``), one participant is picked.

A tab reads its data off the UI thread (``read``), builds its cards once
(``build``) and registers the charts the live view refreshes (``watch``); on every
refresh ``update`` hands each watched chart the data read again, so the charts
redraw in place and keep their controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
from nicegui import ui

from core.runner.indicators import INDICATORS
from studio.adapters.results_service import ResultsService
from studio.components.cards import section
from studio.components.charts import Chart, SeriesChart
from studio.components.run_table import cell
from studio.components.tables import data_table

# The policies of the evaluation tables: the trained one and the two baselines.
POLICIES = {"trained": "Trained", "zero": "Zero", "net_position": "Net position"}
BASELINES = {"zero": "zero", "net_position": "net position"}
# What a line can stand for: the run, or what the runs differ in.
BY = {
    "key": "Run",
    "paradigm": "Paradigm",
    "variant": "Variant",
    "seed": "Seed",
    "policy": "Policy",
}


@dataclass
class Selection:
    """What the tabs look at, kept when the tab changes.

    Attributes:
        open: Go to a tab, by its label.
        run: The run in depth.
        day: The test day.
        policy: The policy.
    """

    open: Callable[[str], None]
    run: Optional[str] = None
    day: Optional[str] = None
    policy: str = "trained"


# --------------------------------------------------------------------------------------
# A tab
# --------------------------------------------------------------------------------------
class Tab:
    """One tab of the Results page, for the ticked runs.

    A subclass writes ``read(keys)`` (a dict of what it shows, read in a worker
    thread) and ``build(keys, data)`` (its cards); a chart it builds with
    ``self.watch(chart, option=data_key)`` gets ``data[data_key]`` as ``option``
    on every live refresh.
    """

    label = ""
    icon = ""

    def __init__(self, service: ResultsService, selection: Selection) -> None:
        self.service = service
        self.selection = selection
        self.watched: list[tuple[Chart, dict[str, str]]] = []
        self.waiting = False  # built without the data it shows (``empty``)

    def empty(self, data: dict[str, Any]) -> bool:
        """Whether ``data`` lacks what the tab shows, so that it is built again,
        in full, when the live view finds it (a subclass; default: never)."""
        return False

    def read(self, keys: list[str]) -> dict[str, Any]:
        return {}

    def build(self, keys: list[str], data: dict[str, Any]) -> None:
        raise NotImplementedError

    def watch(self, chart: Chart, **options: str) -> Chart:
        """Refresh ``chart``'s ``options`` from the data of each live refresh."""
        self.watched.append((chart, options))
        return chart

    def update(self, data: dict[str, Any]) -> None:
        """The data read again: every watched chart redraws with it."""
        for chart, options in self.watched:
            chart.set(**{option: data[name] for option, name in options.items()})


# --------------------------------------------------------------------------------------
# DayChart: one metric of a long table over the test days, a line per group
# --------------------------------------------------------------------------------------
class DayChart(SeriesChart):
    """One metric of a long table (``metric``, ``value``) over the test days: a line
    per group, at each day the mean over everything else in the group (participants,
    runs), with ``band`` its ± one standard deviation.

    Options: ``table`` (``indicator`` or ``participant_metrics``), ``metric``, ``by``
    (the column a line stands for), ``policy`` (one policy, or ``"all"``), ``band``,
    ``labels`` (run key -> name), ``title`` (the y axis).
    """

    height = 320

    def draw(self) -> None:
        o = self.o

        if o.table is None or o.table.empty or not o.get("metric"):
            return

        rows = o.table[o.table.metric == o.metric]

        if o.policy != "all":
            rows = rows[rows.policy == o.policy]

        self.titles(x="test day", y=o.get("titles", {}).get(o.metric, o.metric))

        for value, group in rows.groupby(o.by, sort=False, dropna=False):
            stats = group.groupby("day").value.agg(["mean", "std"])
            name = o.labels.get(value, value) if o.by == "key" else value
            band = None

            if o.band:
                spread = stats["std"].fillna(0.0)
                band = (stats["mean"] - spread, stats["mean"] + spread)

            self.line(stats.index, stats["mean"], str(name), markers=True, band=band)


def metric_card(
    tab: Tab,
    title: str,
    caption: str,
    data_key: str,
    data: dict[str, Any],
    labels: dict[str, str],
    metrics: dict[str, str],
    by: Optional[dict[str, str]] = None,
) -> DayChart:
    """A card with a ``DayChart`` of ``data[data_key]`` (watched by ``tab``) and its
    controls above it: the metric (``metrics``: name -> label), what a line stands
    for (``by``), the policy and the band."""
    with section(title, caption, "show_chart"):
        controls = ui.row().classes("w-full items-center gap-3")
        chart = DayChart(
            table=data[data_key],
            labels=labels,
            metric=next(iter(metrics), None),
            titles=metrics,
            by="key",
            policy="trained",
            band=False,
        ).show()
        tab.watch(chart, table=data_key)

        with controls:
            chart.select("metric", metrics, "Metric").classes("w-64")
            chart.select("by", by or BY, "A line per").classes("w-40")
            chart.select("policy", {"all": "All"} | POLICIES, "Policy").classes("w-40")
            chart.switch("band", "± one std")

    return chart


def indicator_rows(table: pd.DataFrame) -> pd.DataFrame:
    """``day_indicators`` as the long table a ``DayChart`` reads."""
    return table.rename(columns={"indicator": "metric"}) if len(table) else table


def indicator_card(
    tab: Tab, name: str, data: dict[str, Any], labels: dict[str, str]
) -> DayChart:
    """The tab ``name``'s indicators over the test days, from ``data["days"]``
    (``indicator_rows``)."""
    metrics = {
        i.name: f"{i.label} ({i.unit})" if i.unit else i.label
        for i in INDICATORS
        if i.tab == name
    }

    return metric_card(
        tab,
        "On the test days",
        "Each indicator per test day, at the end of training",
        "days",
        data,
        labels,
        metrics,
    )


# --------------------------------------------------------------------------------------
# ParticipantChart: every participant at once, one row each
# --------------------------------------------------------------------------------------
class ParticipantChart(Chart):
    """A heatmap with a row per participant, the first on top; red to blue around 0, or
    a plain scale with ``centred`` off. Options: ``rows`` and ``columns`` (their
    names), ``cells`` (rows × columns), ``title`` (the colour bar's), ``centred``."""

    layout = {"hovermode": "closest"}

    def draw(self) -> None:
        o = self.o
        cells = np.asarray(o.cells, dtype=float)

        if not np.isfinite(cells).any():
            return

        scale: dict[str, Any] = {"colorscale": "Viridis"}

        if o.get("centred", True):
            limit = float(np.nanmax(np.abs(cells))) or 1.0
            scale = {"colorscale": "RdBu", "zmin": -limit, "zmax": limit}

        self.height = max(260, 26 * len(o.rows) + 120)
        self.fig.add_heatmap(
            z=cells,
            x=list(o.columns),
            y=list(o.rows),
            colorbar=dict(title=o.title),
            **scale,
        )
        self.fig.update_yaxes(autorange="reversed")


def has(rows: Optional[pd.DataFrame], column: str) -> bool:
    """Whether ``rows`` has ``column`` with a value in it (a column of NaN, which an
    older table or a step without a power flow leaves, is nothing to draw)."""
    return rows is not None and column in rows and bool(rows[column].notna().any())


def by_number(agent: str) -> tuple[int, str]:
    """A participant's sort key: P2 before P10."""
    digits = "".join(c for c in agent if c.isdigit())

    return int(digits or 0), agent


# --------------------------------------------------------------------------------------
# A table of a frame
# --------------------------------------------------------------------------------------
def frame_table(frame: pd.DataFrame, columns: list[tuple[str, str]]) -> ui.table:
    """A table of ``frame``'s ``columns`` (those it has), ``(field, label)``."""
    columns = [(f, label) for f, label in columns if f in frame]
    rows = [
        {"_row": i} | {f: cell(row[f]) for f, _ in columns}
        for i, row in enumerate(frame.to_dict("records"))
    ]

    return data_table(rows, columns, row_key="_row", pagination=15)
