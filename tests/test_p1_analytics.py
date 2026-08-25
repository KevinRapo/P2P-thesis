"""Provenance tests for market analytics (P1-08)."""

import pytest

from src.analytics.market_analytics import MarketMetricsHandler
from src.analytics.grid_metrics import GridMetrics
from src.analytics.grid_metrics import GridMetricsHandler
from src.analytics.dso_metrics import DSOMetrics
from src.analytics.dso_metrics import DSOMetricsHandler
from src.analytics.coordination_metrics import CoordinationMetricsHandler
from src.visualization.plotter import Plotter
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.matching import MatchingHistory, MatchingResult
from src.market.order import Trade


def test_market_analytics_reports_only_direct_settlement_aggregates() -> None:
    history = MatchingHistory()
    history.update(MatchingResult(
        trades=[Trade("buyer", "seller", 2.0, 1.0, 0.0),
                Trade("buyer", "DSO", 5.0, 2.0, 0.0)],
        unmatched_orders=[], clearing_price=4.0, clearing_volume=3.0,
        dso_buy_volume=0.0, dso_sell_volume=2.0, dso_total_volume=2.0,
        p2p_volume=1.0, dso_trade_ratio=2 / 3, dso_grid_import=2.0,
        dso_buy_price=0.0, dso_sell_price=5.0, price_spread=0.0,
        local_price_avg=2.0, local_price_advantage=0.0,
        grid_balance=0.0, grid_congestion=0.0,
    ))

    metrics = MarketMetricsHandler({"buyer": [1.0, 3.0]}, history).get_metrics()

    assert metrics.settlement_turnover == 12.0
    assert metrics.total_traded_energy == 3.0
    assert metrics.p2p_volume_share == pytest.approx(1 / 3)
    assert metrics.dso_volume_share == pytest.approx(2 / 3)
    assert metrics.average_agent_reward == {"buyer": 2.0}
    assert not hasattr(metrics, "social_welfare")


def test_grid_dso_and_coordination_analytics_keep_literal_recorded_quantities() -> None:
    history = MatchingHistory()
    history.update(MatchingResult(
        trades=[Trade("buyer", "seller", 1.0, 2.0, 0.0, transmission_loss=0.5)],
        unmatched_orders=[], clearing_price=1.0, clearing_volume=2.0,
        dso_buy_volume=1.0, dso_sell_volume=2.0, dso_total_volume=3.0,
        p2p_volume=2.0, dso_trade_ratio=0.6, dso_grid_import=1.5,
        dso_buy_price=0.1, dso_sell_price=0.2, price_spread=0.1,
        local_price_avg=1.0, local_price_advantage=0.0,
        grid_balance=-3.0, grid_congestion=0.4,
    ))
    grid = GridNetwork(GridTopology.LINE, num_nodes=2, capacity=10.0)

    grid_metrics = GridMetricsHandler(grid, history).get_metrics()
    dso_metrics = DSOMetricsHandler(10.0, history).get_metrics()
    outcome_metrics = CoordinationMetricsHandler(10.0, history).get_metrics({"buyer": [2.0]})

    assert grid_metrics.total_transmission_loss == 0.5
    assert grid_metrics.grid_balance_over_time == [-3.0]
    assert dso_metrics.p2p_volume_share == pytest.approx(2 / 5)
    assert dso_metrics.dso_volume_share == pytest.approx(3 / 5)
    assert outcome_metrics.mean_agent_reward == {"buyer": 2.0}
    assert not hasattr(outcome_metrics, "strategy_alignment")


def test_grid_and_dso_plots_only_require_recorded_metric_fields() -> None:
    plotter = Plotter()

    assert len(plotter.plot_grid_stability_metrics(GridMetrics()).axes) == 2
    assert len(plotter.plot_dso_metrics(DSOMetrics()).axes) == 2
