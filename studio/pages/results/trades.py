"""What the Market tab shows of the trades (``heldout_trades.csv.gz``, the peer ones): a
box per run or version of the trades' size and of their price's place in the band, and
who traded with whom in one run, as a matrix.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from nicegui import run, ui

from studio.adapters.results_service import ResultsService
from studio.components.cards import section
from studio.components.charts import Chart
from studio.components.memory import remember
from studio.pages.results.common import (
    BY,
    POLICIES,
    ParticipantChart,
    Selection,
    Tab,
    by_number,
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
    ``"all"``), ``labels`` (run key -> name)."""

    height = 340
    layout = {"hovermode": "closest"}

    def draw(self) -> None:
        o = self.o

        if o.trades is None or o.trades.empty or o.metric not in o.trades:
            return

        rows = o.trades[o.trades.stage < 3]

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
        ).show()
        tab.watch(chart, trades="trades")

        with controls:
            chart.select("metric", DISTRIBUTIONS, "Distribution").classes("w-96")
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


def trade_matrix(trades: pd.DataFrame, policy: str, measure: str) -> pd.DataFrame:
    """Buyers × sellers of the peer trades of ``policy`` (all test days summed): the
    energy, its money (price × kWh) or the number of trades; NaN for no trade."""
    rows = trades[(trades.stage < 3) & (trades.policy == policy)]
    found = rows.assign(money=rows.price * rows.kwh, count=1)
    grid = found.pivot_table(
        index="buyer",
        columns="seller",
        values="count" if measure == "count" else measure,
        aggfunc="sum",
    )
    agents = sorted(set(grid.index) | set(grid.columns), key=by_number)

    return grid.reindex(index=agents, columns=agents)


class TradeMatrix:
    """The buyer × seller matrix of one run, and its selectors.

    Args:
        service: The Results service.
        labels: The ticked runs, key -> name.
        selection: What the tabs share (the run and the policy).
    """

    def __init__(
        self, service: ResultsService, labels: dict[str, str], selection: Selection
    ) -> None:
        self.service, self.selection = service, selection
        self._drawn = 0  # the latest draw: an older one that wakes up later stops
        first = selection.run if selection.run in labels else next(iter(labels))

        # Selector row: run | policy | what a cell is
        with ui.row().classes("w-full items-center gap-3"):
            self.run = ui.select(labels, value=first, label="Run").classes("w-96")
            self.policy = ui.select(
                POLICIES | {"random": "Random"}, value=selection.policy, label="Policy"
            ).classes("w-40")
            self.measure = ui.select(MEASURES, value="kwh", label="A cell is").classes(
                "w-40"
            )

        remember(self.measure, "results_Market_matrix")
        self.box = ui.column().classes("w-full")

        for field in (self.run, self.policy, self.measure):
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

            grid = trade_matrix(trades, policy, self.measure.value)

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
