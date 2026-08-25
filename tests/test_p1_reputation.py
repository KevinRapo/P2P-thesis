"""Regression test for time-independent reputation smoothing (P1-10)."""

from src.agent.der import DERAgent
from src.market.matching import MatchingResult
from src.market.order import Order, Trade
from src.market.reputation import ReputationHandler


def test_reputation_update_uses_fixed_smoothing_not_episode_time() -> None:
    agent = DERAgent("agent", 1.0, generation_profile=[0.0], demand_profile=[0.0])
    agent.reputation = 0.5
    result = MatchingResult(
        trades=[Trade("agent", "other", 1.0, 1.0, 0.0)], unmatched_orders=[], clearing_price=1.0,
        clearing_volume=1.0, dso_buy_volume=0.0, dso_sell_volume=0.0, dso_total_volume=0.0,
        p2p_volume=1.0, dso_trade_ratio=0.0, dso_grid_import=0.0, dso_buy_price=0.0,
        dso_sell_price=0.0, price_spread=0.0, local_price_avg=1.0, local_price_advantage=0.0,
        grid_balance=0.0, grid_congestion=0.0,
    )
    handler = ReputationHandler(smoothing=0.2)

    assert handler.update_reputation(agent, result, time_of_day=0.0) == handler.update_reputation(agent, result, time_of_day=0.99)


def _result(trades, orders) -> MatchingResult:
    return MatchingResult(
        trades=trades, unmatched_orders=[], clearing_price=1.0, clearing_volume=1.0,
        dso_buy_volume=0.0, dso_sell_volume=0.0, dso_total_volume=0.0,
        p2p_volume=1.0, dso_trade_ratio=0.0, dso_grid_import=0.0,
        dso_buy_price=0.0, dso_sell_price=0.0, price_spread=0.0,
        local_price_avg=1.0, local_price_advantage=0.0, grid_balance=0.0,
        grid_congestion=0.0, submitted_orders=orders,
    )


def test_reputation_reliability_uses_filled_quantity_not_trade_fragments() -> None:
    agent = DERAgent("seller", 1.0, generation_profile=[0.0], demand_profile=[0.0])
    agent.reputation = 0.0
    order = Order("sell", "seller", 1.0, 10.0, False, 0.0)
    result = _result([
        Trade("buyer-a", "seller", 1.0, 3.0, 0.0, seller_order_id="sell"),
        Trade("buyer-b", "seller", 1.0, 3.0, 0.0, seller_order_id="sell"),
    ], [order])

    score = ReputationHandler(1.0, 0.0, 0.0, smoothing=1.0).update_reputation(agent, result, 0.0)

    assert score == 0.6


def test_reputation_fairness_requires_trade_to_respect_the_submitted_quote() -> None:
    agent = DERAgent("buyer", 1.0, generation_profile=[0.0], demand_profile=[0.0])
    agent.reputation = 1.0
    order = Order("buy", "buyer", 1.0, 2.0, True, 0.0)
    result = _result([Trade("buyer", "seller", 1.1, 2.0, 0.0, buyer_order_id="buy")], [order])

    score = ReputationHandler(0.0, 1.0, 0.0, smoothing=1.0).update_reputation(agent, result, 0.0)

    assert score == 0.0
