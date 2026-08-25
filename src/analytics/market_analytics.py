"""Market analytics derived directly from recorded settlement data."""

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from ..market.matching import MatchingHistory


@dataclass
class MarketMetrics:
    """Descriptive metrics with direct settlement/history provenance."""

    settlement_turnover: float = 0.0
    total_traded_energy: float = 0.0
    transaction_count: int = 0
    average_trade_size: float = 0.0
    average_settlement_price: float = 0.0
    transaction_price_cv: float = 0.0
    settlement_price_trend: float = 0.0
    market_concentration_hhi: float = 0.0
    p2p_volume_share: float = 0.0
    dso_volume_share: float = 0.0
    volume_trend: float = 0.0
    average_agent_reward: Dict[str, float] = field(default_factory=dict)
    trading_frequency_by_agent: Dict[str, int] = field(default_factory=dict)


class MarketMetricsHandler:
    """Calculate only metrics whose raw inputs are present in the ledger."""

    def __init__(self,
                 agent_rewards: Dict[str, List[float]],
                 matching_history: MatchingHistory) -> None:
        self.agent_rewards = agent_rewards
        self.matching_history = matching_history
        self.trades = [trade for result in matching_history.history for trade in result.trades]

    def get_metrics(self) -> MarketMetrics:
        if not self.trades:
            return MarketMetrics(average_agent_reward={agent_id: float(np.mean(rewards))
                                                       for agent_id, rewards in self.agent_rewards.items()
                                                       if rewards})

        quantities = np.asarray([trade.quantity for trade in self.trades], dtype=float)
        prices = np.asarray([trade.price for trade in self.trades], dtype=float)
        total_energy = float(quantities.sum())
        price_mean = float(prices.mean())
        result_history = self.matching_history.history
        p2p_volume = sum(result.p2p_volume for result in result_history)
        dso_volume = sum(result.dso_total_volume for result in result_history)
        recorded_volume = p2p_volume + dso_volume

        participants: Dict[str, float] = {}
        for trade in self.trades:
            participants[trade.buyer_id] = participants.get(trade.buyer_id, 0.0) + trade.quantity
            participants[trade.seller_id] = participants.get(trade.seller_id, 0.0) + trade.quantity
        participant_total = sum(participants.values())
        concentration = (sum((volume / participant_total) ** 2 for volume in participants.values())
                         if participant_total else 0.0)

        return MarketMetrics(
            settlement_turnover=float((prices * quantities).sum()),
            total_traded_energy=total_energy,
            transaction_count=len(self.trades),
            average_trade_size=total_energy / len(self.trades),
            average_settlement_price=price_mean,
            transaction_price_cv=float(prices.std() / price_mean) if price_mean else 0.0,
            settlement_price_trend=self._trend([result.clearing_price for result in result_history]),
            market_concentration_hhi=concentration,
            p2p_volume_share=p2p_volume / recorded_volume if recorded_volume else 0.0,
            dso_volume_share=dso_volume / recorded_volume if recorded_volume else 0.0,
            volume_trend=self._trend([result.clearing_volume for result in result_history]),
            average_agent_reward={agent_id: float(np.mean(rewards))
                                  for agent_id, rewards in self.agent_rewards.items() if rewards},
            trading_frequency_by_agent=self._trading_frequency(),
        )

    def _trading_frequency(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for trade in self.trades:
            counts[trade.buyer_id] = counts.get(trade.buyer_id, 0) + 1
            counts[trade.seller_id] = counts.get(trade.seller_id, 0) + 1
        return counts

    @staticmethod
    def _trend(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        return float(np.polyfit(np.arange(len(values)), values, 1)[0])
