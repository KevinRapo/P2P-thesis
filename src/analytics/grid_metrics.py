"""Grid summaries derived directly from recorded matching results."""

from dataclasses import dataclass, field
from typing import List

import numpy as np

from ..grid.network import GridNetwork
from ..market.matching import MatchingHistory


@dataclass
class GridMetrics:
    """Recorded grid quantities; no AC-stability or utilization claims."""

    mean_absolute_grid_balance: float = 0.0
    mean_grid_congestion: float = 0.0
    total_transmission_loss: float = 0.0
    transmission_loss_ratio: float = 0.0
    mean_clearing_volume: float = 0.0
    peak_clearing_volume: float = 0.0
    clearing_volume_load_factor: float = 0.0
    grid_balance_trend: float = 0.0
    congestion_trend: float = 0.0
    clearing_volume_trend: float = 0.0
    grid_balance_over_time: List[float] = field(default_factory=list)
    grid_congestion_over_time: List[float] = field(default_factory=list)
    clearing_volume_over_time: List[float] = field(default_factory=list)


class GridMetricsHandler:
    """Aggregate raw balance, congestion, flow, and loss records."""

    def __init__(self, grid_network: GridNetwork, matching_history: MatchingHistory, _window: int = 2) -> None:
        self.grid_network = grid_network
        self.history = matching_history.history

    def get_metrics(self) -> GridMetrics:
        if not self.history:
            return GridMetrics()
        balances = [float(result.grid_balance) for result in self.history]
        congestion = [float(result.grid_congestion) for result in self.history]
        volumes = [float(result.clearing_volume) for result in self.history]
        trades = [trade for result in self.history for trade in result.trades]
        loss = sum(trade.transmission_loss for trade in trades)
        source_energy = sum(trade.quantity for trade in trades)
        peak_volume = max(volumes) if volumes else 0.0
        return GridMetrics(
            mean_absolute_grid_balance=float(np.mean(np.abs(balances))),
            mean_grid_congestion=float(np.mean(congestion)),
            total_transmission_loss=loss,
            transmission_loss_ratio=loss / source_energy if source_energy else 0.0,
            mean_clearing_volume=float(np.mean(volumes)),
            peak_clearing_volume=peak_volume,
            clearing_volume_load_factor=float(np.mean(volumes) / peak_volume) if peak_volume else 0.0,
            grid_balance_trend=self._trend(balances),
            congestion_trend=self._trend(congestion),
            clearing_volume_trend=self._trend(volumes),
            grid_balance_over_time=balances,
            grid_congestion_over_time=congestion,
            clearing_volume_over_time=volumes,
        )

    @staticmethod
    def _trend(values: List[float]) -> float:
        return float(np.polyfit(np.arange(len(values)), values, 1)[0]) if len(values) > 1 else 0.0
