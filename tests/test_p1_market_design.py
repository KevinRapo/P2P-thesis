"""Regression tests for the price-time market baseline (P1-13)."""

from src.market.matching import MatchingResult


def test_aggregate_price_is_explicitly_a_volume_weighted_settlement_price() -> None:
    result = MatchingResult(
        trades=[], unmatched_orders=[], clearing_price=12.5, clearing_volume=0.0,
        dso_buy_volume=0.0, dso_sell_volume=0.0, dso_total_volume=0.0, p2p_volume=0.0,
        dso_trade_ratio=0.0, dso_grid_import=0.0, dso_buy_price=0.0, dso_sell_price=0.0,
        price_spread=0.0, local_price_avg=0.0, local_price_advantage=0.0,
        grid_balance=0.0, grid_congestion=0.0,
    )

    assert result.volume_weighted_settlement_price == 12.5
