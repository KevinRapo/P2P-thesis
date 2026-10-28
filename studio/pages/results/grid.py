"""Results → Grid: what did the grid do?

Every grid amount of the played days (``core/runner/results.day_metrics``), from
the AC power flow whatever the grid method charged the fees with: energy drawn
from and fed into the upstream grid, line and transformer losses, limits broken,
flows that did not converge, the fees charged and the trades' transmission losses;
during training and on the held-out test days. The charts follow the live view.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from studio.components.run_table import labels_of
from studio.pages.results.common import Tab, metric_card

# The grid amounts of the per-day tables, in the order offered.
GRID_METRICS = [
    "grid_losses_kwh",
    "grid_violations",
    "grid_import_kwh",
    "grid_export_kwh",
    "fees",
    "trade_losses_kwh",
    "not_converged",
]


class GridTab(Tab):
    """The grid per day, during training and on the test days."""

    label, icon = "Grid", "hub"

    def read(self, keys: list[str]) -> dict[str, Any]:
        return {"days": self.service.day_metrics(keys)}

    def build(self, keys: list[str], data: dict[str, Any]) -> None:
        common = dict(data=data, labels=labels_of(keys), metrics=GRID_METRICS)
        metric_card(
            self,
            "During training",
            "On the evaluation days, over environment steps: the mean over the days "
            "played at each point",
            "days",
            phase="evaluation",
            **common,
        )
        metric_card(
            self,
            "On the test days",
            "Each held-out test day, at the end of training",
            "days",
            phase="heldout",
            **common,
        )
        ui.label(
            "The line loading the fees were charged on against the loading the power "
            "flow measured is kept per step on traced days only (Market → One run → "
            "Traced days), not yet per day."
        ).classes("mls-card-caption")
