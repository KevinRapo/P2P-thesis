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

from core.market.indicators import INDICATORS
from studio.adapters.results_service import ResultsService
from studio.components.cards import section
from studio.components.charts import Chart, SeriesChart
from studio.components.memory import keep, recalled
from studio.components.run_table import cell
from studio.components.tables import data_table

# The policies of the evaluation tables: the trained one and the played baseline.
POLICIES = {"trained": "Trained", "net_position": "Net position"}
BASELINES = {"net_position": "net position"}
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
    """What the tabs look at, kept when the tab changes; with ``memory``, also
    between visits (``keep``), under ``<memory>_<what>``.

    Attributes:
        open: Go to a tab, by its label.
        run: The run in depth.
        day: The test day.
        policy: The policy.
        agent: The participant.
        memory: What it is kept under; None: not kept (a test, a notebook).
    """

    open: Callable[[str], None]
    run: Optional[str] = None
    day: Optional[str] = None
    policy: str = "trained"
    agent: Optional[str] = None
    memory: Optional[str] = None

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)

        if getattr(self, "memory", None) and name in KEPT:
            keep(f"{self.memory}_{name}", value)

    @classmethod
    def recalled(cls, open: Callable[[str], None], memory: str) -> "Selection":
        """The selection of the last visit."""
        kept = {name: recalled(f"{memory}_{name}") for name in KEPT}

        if kept["policy"] not in POLICIES:  # e.g. ``random``, no longer offered
            kept["policy"] = None

        return cls(
            open, **{k: v for k, v in kept.items() if v is not None}, memory=memory
        )


KEPT = ("run", "day", "policy", "agent")  # what a ``Selection`` keeps between visits


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
        self._prints: dict[str, Any] = {}  # what the charts were last drawn from
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
        """The data read again: a watched chart redraws when what it shows changed
        (``fingerprint``), and not when its data is not in ``data`` (a panel not
        read, as Learning's Timing before it is opened)."""
        prints = {name: fingerprint(value) for name, value in data.items()}
        changed = {n for n in prints if prints[n] != self._prints.get(n)}
        self._prints = prints

        for chart, options in self.watched:
            if not set(options.values()) <= data.keys():
                continue

            if changed & set(options.values()):
                chart.set(**{option: data[name] for option, name in options.items()})


def fingerprint(value: Any) -> Any:
    """What tells two reads of one piece of a tab's data apart: a table's shape and
    the hash of its rows (index and values), anything else as it prints."""
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return ("empty", tuple(value.columns))

        rows = pd.util.hash_pandas_object(value, index=True)

        return (value.shape, tuple(value.columns), int(rows.sum()), int(rows.iloc[-1]))

    if isinstance(value, pd.Series):
        return fingerprint(value.to_frame())

    if isinstance(value, (list, tuple)):
        return tuple(fingerprint(v) for v in value)

    return repr(value)


# --------------------------------------------------------------------------------------
# DayChart: one metric of a long table over the test days, a line per group
# --------------------------------------------------------------------------------------
ALL_PERIODS = "all"
ISO_DAY = "%Y-%m-%d"  # how a test day is named


def period_starts(days: Any) -> pd.Series:
    """Each test day's evaluation period, named by its first day: the test days come
    in periods (a week each), and a period is a run of consecutive dates. A day that
    is not a date, or none, is one period."""
    unique = pd.Series(sorted(set(days)), dtype=object)
    dates = pd.to_datetime(unique, format=ISO_DAY, errors="coerce")

    if unique.empty or dates.isna().any():
        first = unique.iloc[0] if len(unique) else None

        return pd.Series(first, index=unique, dtype=object)

    new = dates.diff().dt.days.fillna(2) > 1
    starts = unique.where(new).ffill()

    return pd.Series(starts.to_numpy(), index=unique, dtype=object)


def period_labels(days: Any) -> dict[str, str]:
    """The evaluation periods of ``days`` as first day -> name (``11 - 17 Jan 2016``)."""
    starts = period_starts(days)
    labels = {}

    for first, group in starts.groupby(starts, sort=True):
        dates = pd.to_datetime(pd.Series(group.index), format=ISO_DAY, errors="coerce")

        if dates.isna().any():
            labels[first] = str(first)
            continue

        a, b = dates.min(), dates.max()

        if a == b:
            labels[first] = f"{a:%d %b %Y}"
        elif a.year == b.year and a.month == b.month:
            labels[first] = f"{a.day} – {b.day} {a:%b %Y}"
        else:
            labels[first] = f"{a:%d %b %Y} – {b:%d %b %Y}"

    return labels


def in_period(days: pd.Series, period: str, universe: Any = None) -> pd.Series:
    """Which of ``days`` are in the evaluation ``period`` (its first day, as
    ``period_labels`` names it); every one for ``ALL_PERIODS`` or a period that is not
    among ``universe`` (the days the periods are made of, default ``days``)."""
    starts = period_starts(days if universe is None else universe)

    if period == ALL_PERIODS or period not in set(starts):
        return pd.Series(True, index=days.index)

    return days.map(starts) == period


def period_select(owner: Any, option: str, days: Any) -> Optional[ui.select]:
    """The "Evaluation period" dropdown of ``owner`` (a chart: its option ``option``),
    when ``days`` hold more than one period; None otherwise."""
    periods = period_labels(days)

    if len(periods) < 2:
        return None

    return owner.select(
        option, {ALL_PERIODS: "All periods"} | periods, "Evaluation period"
    ).classes("w-56")


class DayChart(SeriesChart):
    """One metric of a long table (``metric``, ``value``) over the test days: a line
    per group, at each day the mean over everything else in the group (participants,
    runs), with ``band`` its ± one standard deviation.

    Options: ``table`` (``indicator`` or ``participant_metrics``), ``metric``, ``by``
    (the column a line stands for), ``policy`` (one policy, or ``"all"``), ``band``,
    ``labels`` (run key -> name), ``title`` (the y axis), ``period`` (one evaluation
    period, by its first day, or ``ALL_PERIODS``; a week on its own is readable, all
    of them together are a few spikes between long gaps).
    """

    height = 320

    def draw(self) -> None:
        o = self.o

        if o.table is None or o.table.empty or not o.get("metric"):
            return

        rows = o.table[o.table.metric == o.metric]

        if o.policy != "all":
            rows = rows[rows.policy == o.policy]

        period = o.get("period", ALL_PERIODS)
        rows = rows[in_period(rows.day, period, o.table.day)]
        one = period != ALL_PERIODS and period in set(period_starts(o.table.day))

        self.titles(x="test day", y=o.get("titles", {}).get(o.metric, o.metric))

        if (
            one
            and pd.to_datetime(rows.day, format=ISO_DAY, errors="coerce").notna().all()
        ):
            # a week: a tick per day, with its weekday
            self.fig.update_xaxes(dtick=86_400_000, tickformat="%a %d %b")

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
    controls above it: the metric (``metrics``: name -> label), the evaluation period
    (when there are several; the first is shown, one at a time), what a line stands
    for (``by``), the policy and the band."""
    table = data[data_key]
    periods = period_labels(table.day) if len(table) and "day" in table else {}

    with section(title, caption, "show_chart"):
        controls = ui.row().classes("w-full items-center gap-3")
        chart = DayChart(
            table=table,
            labels=labels,
            metric=next(iter(metrics), None),
            titles=metrics,
            by="key",
            policy="trained",
            band=False,
            period=next(iter(periods), ALL_PERIODS),
        ).show()
        tab.watch(chart, table=data_key)
        chart.memory = f"results_{tab.label}_{data_key}"  # its controls, between visits

        with controls:
            chart.select("metric", metrics, "Metric").classes("w-64")

            if len(table) and "day" in table:
                period_select(chart, "period", table.day)

            chart.select("by", by or BY, "A line per").classes("w-40")
            chart.select("policy", {"all": "All"} | POLICIES, "Policy").classes("w-40")
            chart.hover_select().classes("w-40")
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
        # Grid lines on the cells' edges, not through their middles, drawn over them
        edges = dict(tickson="boundaries", layer="above traces")
        self.fig.update_yaxes(type="category", autorange="reversed", **edges)

        if all(isinstance(c, str) for c in o.columns):  # a day is a name, not a date
            self.fig.update_xaxes(type="category", **edges)
        else:  # many numeric columns (environment steps): no line per column
            self.fig.update_xaxes(showgrid=False)


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
