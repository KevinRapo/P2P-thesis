"""Regression test for visible DSO capacity residuals (P1-05)."""

from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.grid.base import Location
from src.market.dso import DSOAgent
from src.market.order import Order


def test_dso_capacity_leaves_unserved_buy_residual_visible() -> None:
    grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2)
    dso = DSOAgent("DSO", [1.0], [2.0], grid, max_sell_quantity=3.0)
    order = Order("buy", "agent", 2.0, 5.0, True, 0.0)

    trades, stats = dso.clear_unmatched_orders(0, [order], [])

    assert trades[0].quantity == 3.0
    assert stats["dso_sell_volume"] == 3.0
    assert order.quantity == 2.0


def test_dso_trade_respects_the_same_network_capacity() -> None:
    grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2, capacity=1.0)
    dso = DSOAgent("DSO", [1.0], [2.0], grid, max_sell_quantity=5.0, node_id="0")
    order = Order("buy", "agent", 2.0, 2.0, True, 0.0, Location("1", 1, 0))

    trades, _ = dso.clear_unmatched_orders(0, [order], [])

    assert trades == []
    assert order.quantity == 2.0
