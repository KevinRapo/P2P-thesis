"""What the Market tab shows of the trades (``heldout_trades.csv.gz``, the peer ones): a
box per run or version of the trades' size and of their price's place in the band, and
who traded with whom in one run, as a matrix.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd
from nicegui import run, ui

from studio.adapters.results_service import ResultsService
from studio.components.cards import section
from studio.components.charts import Chart
from studio.components.memory import remember
from studio.pages.results.common import (
    ALL_PERIODS,
    BY,
    POLICIES,
    ParticipantChart,
    Selection,
    Tab,
    by_number,
    has,
    in_period,
    period_labels,
    period_select,
)
from studio.theme import SERIES

# What a box can show: column of ``trade_table`` -> the y axis.
DISTRIBUTIONS = {
    "kwh": "Peer trade size (kWh)",
    "band": "Peer price in the band (0 feed-in tariff, 1 utility price)",
}
# What a cell of the matrix can be.
MEASURES = {"kwh": "Energy (kWh)", "money": "Money (EUR)", "count": "Trades"}


# --------------------------------------------------------------------------------------
# A box per run or version
# --------------------------------------------------------------------------------------
class TradeBoxChart(Chart):
    """The peer trades' ``metric`` as a box per group, the outliers named by their run in
    the hover. Options: ``trades`` (``trade_table``), ``metric`` (a key of
    ``DISTRIBUTIONS``), ``by`` (the column a box stands for), ``policy`` (one, or
    ``"all"``), ``labels`` (run key -> name), ``period`` (one evaluation period, by its
    first day, or ``ALL_PERIODS``)."""

    height = 340
    layout = {"hovermode": "closest"}

    def draw(self) -> None:
        o = self.o

        if not has(o.trades, o.metric):
            return

        rows = o.trades[o.trades.stage < 3]
        rows = rows[in_period(rows.day, o.get("period", ALL_PERIODS), o.trades.day)]

        if o.policy != "all":
            rows = rows[rows.policy == o.policy]

        self.titles(y=DISTRIBUTIONS[o.metric])

        for i, (value, group) in enumerate(
            rows.groupby(o.by, sort=False, dropna=False)
        ):
            name = o.labels.get(value, value) if o.by == "key" else value
            self.fig.add_box(
                y=group[o.metric],
                name=str(name),
                text=group.key.map(o.labels),
                boxpoints="outliers",
                marker_color=SERIES[i % len(SERIES)],
                showlegend=False,
            )


def trade_card(tab: Tab, data: dict[str, Any], labels: dict[str, str]) -> TradeBoxChart:
    """A card with a ``TradeBoxChart`` of ``data["trades"]`` (watched by ``tab``) and its
    controls: the distribution, what a box stands for and the policy."""
    with section(
        "Peer trades",
        "How big the trades between participants were, and where their price fell "
        "between the feed-in tariff and the utility price. Not the raw price: with "
        "tariffs that change by the day it would only show the spot price.",
        "candlestick_chart",
    ):
        controls = ui.row().classes("w-full items-center gap-3")
        chart = TradeBoxChart(
            trades=data["trades"],
            labels=labels,
            metric="kwh",
            by="key",
            policy="trained",
            period=ALL_PERIODS,
        ).show()
        tab.watch(chart, trades="trades")
        chart.memory = "results_Market_trades"

        with controls:
            chart.select("metric", DISTRIBUTIONS, "Distribution").classes("w-96")

            if has(data["trades"], "day"):
                period_select(chart, "period", data["trades"].day)

            chart.select("by", BY, "A box per").classes("w-40")
            chart.select("policy", {"all": "All"} | POLICIES, "Policy").classes("w-40")

    return chart


# --------------------------------------------------------------------------------------
# Who trades with whom
# --------------------------------------------------------------------------------------
class MatrixChart(ParticipantChart):
    """A matrix of buyers (rows) and sellers (columns); a pair that never traded is
    blank. Options as ``ParticipantChart``."""

    x_title = "seller"
    y_title = "buyer"


def trade_matrix(
    trades: pd.DataFrame,
    policy: str,
    measure: str,
    everyone: Sequence[str] = (),
    period: str = ALL_PERIODS,
) -> pd.DataFrame:
    """Buyers × sellers of the peer trades of ``policy`` (the test days of ``period``,
    by default all, summed): the energy, its money (price × kWh) or the number of
    trades; NaN for no trade. The participants in ``everyone`` have a row and a column
    though they never traded."""
    rows = trades[(trades.stage < 3) & (trades.policy == policy)]
    rows = rows[in_period(rows.day, period, trades.day)]
    found = rows.assign(money=rows.price * rows.kwh, count=1)
    grid = found.pivot_table(
        index="buyer",
        columns="seller",
        values="count" if measure == "count" else measure,
        aggfunc="sum",
    )
    agents = sorted({*grid.index, *grid.columns, *everyone}, key=by_number)

    return grid.reindex(index=agents, columns=agents)


class TradeMatrix:
    """The buyer × seller matrix of one run, and its selectors.

    Args:
        service: The Results service.
        labels: The ticked runs, key -> name.
        selection: What the tabs share (the run and the policy).
        days: The test days of the ticked runs, which the evaluation periods to pick
            from are made of (none: no period to pick, every day is summed).
    """

    def __init__(
        self,
        service: ResultsService,
        labels: dict[str, str],
        selection: Selection,
        days: Any = (),
    ) -> None:
        self.service, self.selection = service, selection
        self._drawn = 0  # the latest draw: an older one that wakes up later stops
        first = selection.run if selection.run in labels else next(iter(labels))

        self.period: Optional[ui.select] = None

        # Selector row: run | policy | what a cell is | evaluation period
        with ui.row().classes("w-full items-center gap-3"):
            self.run = ui.select(labels, value=first, label="Run").classes("w-96")
            self.policy = ui.select(
                POLICIES, value=selection.policy, label="Policy"
            ).classes("w-40")
            self.measure = ui.select(MEASURES, value="kwh", label="A cell is").classes(
                "w-40"
            )
            periods = period_labels(days)

            if len(periods) > 1:
                self.period = ui.select(
                    {ALL_PERIODS: "All periods"} | periods,
                    value=ALL_PERIODS,
                    label="Evaluation period",
                ).classes("w-56")

        remember(self.measure, "results_Market_matrix")

        if self.period is not None:
            remember(self.period, "results_Market_matrix_period")

        self.box = ui.column().classes("w-full")

        for field in (self.run, self.policy, self.measure, self.period):
            if field is not None:
                field.on_value_change(self.draw)

        ui.timer(0.01, self.draw, once=True)

    async def draw(self) -> None:
        self._drawn += 1
        drawn = self._drawn
        key, policy = self.run.value, self.policy.value
        self.selection.run, self.selection.policy = key, policy
        trades = await run.io_bound(self.service.table, key, "heldout_trades")

        if drawn != self._drawn:
            return

        self.box.clear()

        with self.box:
            if trades is None:
                ui.label("Not recorded: a run from before the trade table.").classes(
                    "mls-card-caption"
                )
                return

            everyone = self.service.network(key)[1]
            period = self.period.value if self.period is not None else ALL_PERIODS
            grid = trade_matrix(
                trades, policy, self.measure.value, list(everyone), period
            )

            if grid.empty or not np.isfinite(grid.to_numpy()).any():
                ui.label("No peer trades.").classes("mls-card-caption")
                return

            MatrixChart(
                rows=list(grid.index),
                columns=list(grid.columns),
                cells=grid.to_numpy(),
                title=MEASURES[self.measure.value],
                centred=False,
            ).show()
