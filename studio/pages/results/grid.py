"""Results → Grid: what did the grid do?

Its indicators per test day (``core/market/indicators.py``), from the AC power flow
whichever grid method charged the fees; then one run step by step, a second one over it
if asked: loading against what the fees read, voltages, the upstream exchange; and
the network's day replayed step by step.
"""

from __future__ import annotations

from typing import Any

from studio.components.cards import section
from studio.components.charts import VoltageChart
from studio.components.run_table import labels_of
from studio.pages.results.common import Tab, indicator_card, indicator_rows
from studio.pages.results.replay import Replay
from studio.pages.results.steps import StepView

GRID_CHARTS = [
    (
        "line loading, %",
        [
            "max_line_loading_percent",
            "mean_line_loading_percent",
            "max_trafo_loading_percent",
        ],
    ),
    ("upstream exchange, kWh", ["grid_import_kwh", "grid_export_kwh"]),
    ("losses, kWh", ["grid_losses_kwh", "trade_losses_kwh"]),
    ("limits broken", ["voltage_violations", "loading_violations"]),
]


class GridTab(Tab):
    """The grid per test day, and one run step by step."""

    label, icon = "Grid", "hub"

    def read(self, keys: list[str]) -> dict[str, Any]:
        return {"days": indicator_rows(self.service.day_indicators(keys))}

    def build(self, keys: list[str], data: dict[str, Any]) -> None:
        labels = labels_of(keys)
        indicator_card(self, "grid", data, labels)

        def voltages(rows, other, key: str) -> VoltageChart:
            """The day's lowest and highest bus voltage, the run's limits dashed."""
            return VoltageChart(
                x=rows.step,
                highest=rows.max_voltage_pu,
                lowest=rows.min_voltage_pu,
                limits=self.service.voltage_limits(key),
                compared=None
                if other is None
                else (other.step, other.max_voltage_pu, other.min_voltage_pu),
                x_title="step",
            )

        charts = [GRID_CHARTS[0], voltages, *GRID_CHARTS[1:]]

        with section("Step by step", "One run, a test day at a time", "timeline"):
            StepView(self.service, labels, self.selection, charts)

        with section(
            "Network replay",
            "The network a step at a time: lines by loading, buses by voltage, the "
            "participants ringed. A participant that traded is marked: orange sold, "
            "blue bought, larger for more energy, filled when mostly with peers and "
            "hollow when with the DSO. Click one to draw its peer trades.",
            "play_circle",
        ):
            Replay(self.service, labels, self.selection)
