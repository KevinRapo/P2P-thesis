"""Regression tests for the abstract capacity-flow graph (P1-02/P1-03)."""

import networkx as nx

from src.grid.base import GridTopology
from src.grid.network import GridNetwork


def test_flow_is_zeroed_each_step_and_rejects_overload() -> None:
    grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2, capacity=5.0, seed=1)

    assert list(grid.edge_flows.values()) == [0.0]
    assert grid.can_settle("1", "0", 5.0)
    assert grid.update_flow_from_trade("1", "0", 5.0)
    assert not grid.can_settle("1", "0", 0.1)

    grid.reset()
    assert list(grid.edge_flows.values()) == [0.0]


def test_opposite_flow_nets_on_an_abstract_edge() -> None:
    grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2, capacity=10.0, seed=1)

    assert grid.update_flow_from_trade("1", "0", 2.0)
    assert grid.update_flow_from_trade("0", "1", 2.0)
    assert abs(next(iter(grid.edge_flows.values()))) < 0.1


def test_ieee34_capacity_graph_is_connected() -> None:
    grid = GridNetwork(topology=GridTopology.IEEE34)

    assert nx.number_connected_components(grid.graph) == 1
    assert grid.graph.has_edge("832", "888")
