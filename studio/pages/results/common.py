"""What the Results page's tabs share: the tab base, the metric chart and a table of
a frame.

A tab reads its data off the UI thread (``read``), builds its cards once
(``build``) and registers the charts the live view refreshes (``watch``); on every
refresh ``update`` hands each watched chart the data read again, so the charts
redraw in place and keep their controls.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from nicegui import ui

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
AXES = {"env_steps": "environment steps", "day": "test day"}


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

    def __init__(self, service: ResultsService) -> None:
        self.service = service
        self.watched: list[tuple[Chart, dict[str, str]]] = []

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
# MetricChart: one metric of a long table, a line per group
# --------------------------------------------------------------------------------------
class MetricChart(SeriesChart):
    """One metric of a long table (``metric``, ``value``) along environment steps
    (during training) or the test days (held out): a line per group, at each
    point the mean over everything else in the group (days, episodes,
    participants, runs), with ``band`` its ± one standard deviation.

    Options: ``table`` (``day_metrics``, ``participant_metrics`` or
    ``learner_metrics``), ``metric``, ``by`` (the column a line stands for),
    ``phase`` (``"evaluation"`` or ``"heldout"``, when the table has phases),
    ``policy`` (one policy, or ``"all"``), ``band``, ``labels`` (run key ->
    name).
    """

    height = 320

    def draw(self) -> None:
        o = self.o
        table = o.table

        if table is None or table.empty or not o.get("metric"):
            return

        rows = table[table.metric == o.metric]
        phase = o.get("phase")

        if phase and "phase" in rows:
            rows = rows[rows.phase == phase]

        if o.get("policy", "all") != "all" and "policy" in rows:
            rows = rows[rows.policy == o.policy]

        x = "day" if phase == "heldout" else "env_steps"
        rows = rows.dropna(subset=[x])
        self.titles(x=AXES[x], y=o.metric)

        for value, group in rows.groupby(o.by, sort=False, dropna=False):
            stats = group.groupby(x).value.agg(["mean", "std"]).fillna(0.0)
            name = o.labels.get(value, value) if o.by == "key" else value
            band = None

            if o.get("band"):
                band = (stats["mean"] - stats["std"], stats["mean"] + stats["std"])

            self.line(stats.index, stats["mean"], str(name), markers=True, band=band)


def metric_card(
    tab: Tab,
    title: str,
    caption: str,
    data_key: str,
    data: dict[str, Any],
    labels: dict[str, str],
    metrics: Optional[list[str]] = None,
    by: Optional[dict[str, str]] = None,
    phases: Optional[dict[str, str]] = None,
    **options: Any,
) -> MetricChart:
    """A card with a ``MetricChart`` of ``data[data_key]`` (watched by ``tab``) and
    its controls above it: the metric (``metrics``, default every one in the
    table), with ``phases`` the phase, what a line stands for (``by``), the policy
    and the band."""
    table = data[data_key]
    found = list(table.metric.unique()) if not table.empty else []
    metrics = [m for m in (metrics or found) if m in found]
    by = by or BY

    with section(title, caption, "show_chart"):
        controls = ui.row().classes("w-full items-center gap-3")

        if not metrics:
            ui.label("Nothing recorded yet.").classes("mls-card-caption")

        chart = MetricChart(
            table=table,
            labels=labels,
            metric=metrics[0] if metrics else None,
            by="key",
            policy="trained",
            band=False,
            **options,
        ).show()
        tab.watch(chart, table=data_key)

        with controls:
            chart.select("metric", metrics, "Metric").classes("w-64")

            if phases:
                chart.select("phase", phases, "Phase").classes("w-44")

            chart.select("by", by, "A line per").classes("w-40")

            if "policy" in table:
                policies = {"all": "All"} | POLICIES
                chart.select("policy", policies, "Policy").classes("w-40")

            chart.switch("band", "± one std")

    return chart


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
