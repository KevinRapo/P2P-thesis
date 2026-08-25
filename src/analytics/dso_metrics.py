"""DSO fallback summaries with direct matching-result provenance."""

from dataclasses import dataclass

import numpy as np

from ..market.matching import MatchingHistory


@dataclass
class DSOMetrics:
    dso_buy_volume: float = 0.0
    dso_sell_volume: float = 0.0
    dso_total_volume: float = 0.0
    p2p_volume: float = 0.0
    dso_volume_share: float = 0.0
    p2p_volume_share: float = 0.0
    dso_buy_price_average: float = 0.0
    dso_sell_price_average: float = 0.0
    mean_price_spread: float = 0.0
    local_settlement_price_average: float = 0.0
    net_grid_import: float = 0.0


class DSOMetricsHandler:
    """Aggregate recorded DSO quantities and prices; no counterfactual scores."""

    def __init__(self, grid_capacity: float, matching_history: MatchingHistory, _window: int = 2) -> None:
        if grid_capacity <= 0:
            raise ValueError("Grid capacity must be positive.")
        self.history = matching_history.history

    def get_metrics(self) -> DSOMetrics:
        if not self.history:
            return DSOMetrics()
        dso_buy = sum(result.dso_buy_volume for result in self.history)
        dso_sell = sum(result.dso_sell_volume for result in self.history)
        dso_total = dso_buy + dso_sell
        p2p = sum(result.p2p_volume for result in self.history)
        total = dso_total + p2p
        return DSOMetrics(
            dso_buy_volume=dso_buy,
            dso_sell_volume=dso_sell,
            dso_total_volume=dso_total,
            p2p_volume=p2p,
            dso_volume_share=dso_total / total if total else 0.0,
            p2p_volume_share=p2p / total if total else 0.0,
            dso_buy_price_average=self._mean_positive("dso_buy_price"),
            dso_sell_price_average=self._mean_positive("dso_sell_price"),
            mean_price_spread=float(np.mean([result.price_spread for result in self.history])),
            local_settlement_price_average=self._mean_positive("local_price_avg"),
            net_grid_import=sum(result.dso_grid_import for result in self.history),
        )

    def _mean_positive(self, name: str) -> float:
        values = [getattr(result, name) for result in self.history if getattr(result, name) > 0]
        return float(np.mean(values)) if values else 0.0
