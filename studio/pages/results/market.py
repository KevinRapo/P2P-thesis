"""Results → Market: what did the market do?

Its indicators per test day (``core/runner/indicators.py``) and each participant's
amounts (``participant_metrics``); one run's participants against a baseline; and one
run step by step, a second one over it if asked. The charts follow the live view.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from nicegui import run, ui

from studio.adapters.results_service import ResultsService
from studio.components.cards import section
from studio.components.charts import TradedChart
from studio.components.memory import remember
from studio.components.run_table import labels_of
from studio.pages.results.common import (
    BASELINES,
    BY,
    ParticipantChart,
    Tab,
    has,
    indicator_card,
    indicator_rows,
    metric_card,
)
from studio.pages.results.steps import StepView
from studio.pages.results.trades import TradeMatrix, trade_card

def traded(
    rows: pd.DataFrame, other: Optional[pd.DataFrame], key: str
) -> TradedChart:
    """The day's energy traded per step, stacked (the stage-1 part of the peer
    trades apart), the peer price on the right; the compared run's peer energy
    dotted."""
    zero = pd.Series(0.0, index=rows.index)
    dso = rows.get("bought_from_dso_kwh", zero) + rows.get("sold_to_dso_kwh", zero)
    return TradedChart(
        x=rows.step,
        p2p=rows.p2p_kwh.fillna(0.0),
        dso=dso.fillna(0.0),
        price=rows.get("peer_price", zero),
        stage1=rows.preference_kwh.fillna(0.0) if has(rows, "preference_kwh") else None,
        compared=None if other is None else (other.step, other.p2p_kwh.fillna(0.0)),
        x_title="step",
    )


MARKET_CHARTS = [
    traded,
    ("prices, per kWh", ["peer_price", "feed_in_tariff", "utility_price"]),
    ("peer share of the energy traded", ["peer_share"]),
    ("grid balance, kWh", ["grid_balance_kwh"]),
    ("peer trades", ["peer_trades"]),
]
PERSON_CHARTS = [
    ("kWh", ["demand_kwh", "generation_kwh", "order_kwh", "bought_kwh", "sold_kwh"]),
    ("battery and reward", ["soc", "reward"]),
]
# The amounts per participant, in the order offered.
PARTICIPANT_METRICS = [
    "return",
    "bill",
    "profit",
    "bought_kwh",
    "sold_kwh",
    "preference_kwh",
    "deferred_demand_kwh",
    "deferred_supply_kwh",
]
# A participant's orders and partner choice in a day (``heldout_agent_steps``).
TRACE_COLUMNS = [
    ("step", "Step"),
    ("side", "Side"),
    ("order_kwh", "Order kWh"),
    ("order_price", "Price"),
    ("partner", "Partner"),
    ("partner_mutual", "Mutual"),
    ("preference_kwh", "Stage 1 kWh"),
    ("bought_kwh", "Bought kWh"),
    ("sold_kwh", "Sold kWh"),
    ("reward", "Reward"),
]
# The participant outcomes of ``heldout_agents.csv`` the Participants view offers.
OUTCOMES = {m: m.replace("_", " ") for m in PARTICIPANT_METRICS}


# --------------------------------------------------------------------------------------
# One run: participants against a baseline, orders of a day
# --------------------------------------------------------------------------------------
def shown_participants(table: pd.DataFrame, column: str, text: str = "") -> list[str]:
    """The participants the heatmap shows: those whose name contains ``text`` (all
    without), the largest mean absolute ``column`` first."""
    sizes = table.groupby("agent")[column].apply(lambda v: v.abs().mean())

    if text:
        sizes = sizes[[text.lower() in str(a).lower() for a in sizes.index]]

    return list(sizes.sort_values(ascending=False).index)


def _orders(person: pd.DataFrame) -> None:
    """A participant's orders and partners in a day, as a table."""
    shown = [(f, label) for f, label in TRACE_COLUMNS if f in person]
    rows = person[[f for f, _ in shown]]
    ui.label(
        "Orders and partners: the partner named (a participant, DSO or none), "
        "whether it named this participant back on the other side (1/0), and the "
        "energy traded in stage 1"
    ).classes("mls-card-caption")
    ui.table(
        columns=[
            {"name": f, "label": label, "field": f, "align": "left"}
            for f, label in shown
        ],
        rows=rows.round(4).astype(object).where(rows.notna(), "").to_dict("records"),
        row_key="step",
    ).props("dense flat").classes("w-full")


class OneRun:
    """One run's participants (read when the run is picked)."""

    def __init__(self, service: ResultsService) -> None:
        self.service = service

    def participants(self, key: str, people: Optional[pd.DataFrame]) -> None:
        with section(
            "Participants",
            "An outcome of the trained policy minus the same of a baseline, per "
            "participant and test day (blue: higher for the trained policy). A "
            "better team total can hide participants that lose. The largest "
            "difference is on top; the filter narrows it by name.",
            "groups",
        ):
            if people is None:
                ui.label(
                    "Not recorded: a run from before the per-participant tables."
                ).classes("mls-card-caption")
                return

            outcomes = {k: v for k, v in OUTCOMES.items() if k in people}

            # Filter row: outcome | baseline | participant name filter
            with ui.row().classes("w-full items-center gap-4"):
                outcome = ui.select(outcomes, value="return", label="Outcome").classes(
                    "w-56"
                )
                baseline = ui.radio(BASELINES, value="net_position").props("inline")
                text = ui.input(placeholder="Only participants containing").props(
                    "dense clearable"
                )

            remember(outcome, "results_Market_outcome")
            remember(baseline, "results_Market_baseline")
            remember(text, "results_Market_participants")

            # The chart under the filters, redrawn by draw()
            box = ui.column().classes("w-full gap-1")

            async def draw() -> None:
                table = await run.io_bound(
                    self.service.participant_days, key, outcome.value
                )
                column = f"trained_minus_{baseline.value}"
                box.clear()

                with box:
                    if table.empty or column not in table:
                        ui.label("Nothing to show.").classes("mls-card-caption")
                        return

                    agents = shown_participants(table, column, text.value or "")
                    grid = table[table.agent.isin(agents)].pivot(
                        index="agent", columns="day", values=column
                    )
                    title = (
                        f"{OUTCOMES[outcome.value]}:<br>trained −<br>"
                        + BASELINES[baseline.value]
                    )
                    ParticipantChart(
                        rows=agents,
                        columns=grid.columns,
                        cells=grid.reindex(agents).to_numpy(),
                        title=title,
                    ).show()

            for field in (outcome, baseline, text):
                field.on_value_change(draw)

            ui.timer(0.01, draw, once=True)


# --------------------------------------------------------------------------------------
# The tab
# --------------------------------------------------------------------------------------
class MarketTab(Tab):
    """The market per test day, per participant, and one run step by step."""

    label, icon = "Market", "storefront"

    def read(self, keys: list[str]) -> dict[str, Any]:
        return {
            "days": indicator_rows(self.service.day_indicators(keys)),
            "people": self.service.participant_metrics(keys),
            "trades": self.service.trade_table(keys),
        }

    def build(self, keys: list[str], data: dict[str, Any]) -> None:
        labels = labels_of(keys)
        indicator_card(self, "market", data, labels)
        metric_card(
            self,
            "Per participant",
            "The same per participant on the test days: the mean over them, or a "
            "line per kind with 'A line per: Participant group'",
            "people",
            data,
            labels,
            {m: m.replace("_", " ") for m in PARTICIPANT_METRICS},
            by=BY | {"group": "Participant group"},
        )

        trade_card(self, data, labels)

        with section(
            "Who trades with whom",
            "Peer trades of one run and policy over all test days: a row per buyer, a "
            "column per seller.",
            "grid_on",
        ):
            TradeMatrix(self.service, labels, self.selection)

        with section("One run", "Its participants against a baseline", "search"):
            one = OneRun(self.service)

            def show(key: Optional[str]) -> None:
                box.clear()

                if key:
                    with box:
                        one.participants(key, self.service.table(key, "heldout_agents"))

            ui.select(labels, label="Run", on_change=lambda e: show(e.value)).classes(
                "w-full"
            )
            box = ui.column().classes("w-full gap-4")  # under the picker

        with section("Step by step", "One run, a test day at a time", "timeline"):
            StepView(
                self.service,
                labels,
                self.selection,
                MARKET_CHARTS,
                PERSON_CHARTS,
                _orders,
            )
