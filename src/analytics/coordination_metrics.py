"""Descriptive history summaries; not evidence of coordination or causality."""

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from ..market.matching import MatchingHistory


@dataclass
class CoordinationMetrics:
    """Observable aggregate behavior, deliberately free of causal labels."""

    mean_absolute_grid_balance: float = 0.0
    mean_grid_congestion: float = 0.0
    p2p_volume_share: float = 0.0
    settlement_volume_trend: float = 0.0
    grid_balance_trend: float = 0.0
    mean_agent_reward: Dict[str, float] = None

    def __post_init__(self) -> None:
        if self.mean_agent_reward is None:
            self.mean_agent_reward = {}


class CoordinationMetricsHandler:
    """Summarize recorded outcomes without inferring strategies or impact."""

    def __init__(self, grid_capacity: float, matching_history: MatchingHistory, _window: int = 2) -> None:
        if grid_capacity <= 0:
            raise ValueError("Grid capacity must be positive.")
        self.history = matching_history.history

    def get_metrics(self, agents_reward: Dict[str, List[float]]) -> CoordinationMetrics:
        rewards = {agent_id: float(np.mean(values)) for agent_id, values in agents_reward.items() if values}
        if not self.history:
            return CoordinationMetrics(mean_agent_reward=rewards)
        balances = [result.grid_balance for result in self.history]
        volumes = [result.clearing_volume for result in self.history]
        total_p2p = sum(result.p2p_volume for result in self.history)
        total_volume = sum(result.p2p_volume + result.dso_total_volume for result in self.history)
        return CoordinationMetrics(
            mean_absolute_grid_balance=float(np.mean(np.abs(balances))),
            mean_grid_congestion=float(np.mean([result.grid_congestion for result in self.history])),
            p2p_volume_share=total_p2p / total_volume if total_volume else 0.0,
            settlement_volume_trend=self._trend(volumes),
            grid_balance_trend=self._trend(balances),
            mean_agent_reward=rewards,
        )

    @staticmethod
    def _trend(values: List[float]) -> float:
        return float(np.polyfit(np.arange(len(values)), values, 1)[0]) if len(values) > 1 else 0.0
