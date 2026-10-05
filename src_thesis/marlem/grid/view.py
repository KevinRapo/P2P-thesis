"""A SimBench network as the market sees it.

The market, the DSO and the metrics want a graph with distances, zones, capacities
and congestion (the ``GridView`` protocol, implemented by ``GridNetwork``). This
subclass fills that graph from the network's real topology instead of a generated
one: one node per bus, one edge per closed line, transformer or switch. It only
supplies distances and zones in shadow mode; the physical state of the network
comes from the power flow (``SimBenchGrid``), not from here.

Distances count branches (every edge weighs 1): the topology records carry no line
lengths.
"""

from __future__ import annotations

from typing import Optional

import networkx as nx

from src_thesis.marlem.core.location import GridTopology
from src_thesis.marlem.grid.contract import TopologyView
from src_thesis.marlem.grid.network import GridNetwork


class SimBenchGridView(GridNetwork):
    """``GridNetwork`` over the buses and branches of a real network.

    Args:
        topology: The network's shape (``simbench.topology_view``).
        capacity: Total energy per step the grid can carry, in kWh.
        seed: Seed of the random initial edge flows (I-33).
    """

    def __init__(
        self, topology: TopologyView, capacity: float, seed: Optional[int] = None
    ) -> None:
        self._shape = topology
        super().__init__(GridTopology.MESH, len(topology.buses), capacity, seed)

    def _create_grid_network(self, seed: Optional[int] = None) -> nx.Graph:
        """The graph of the network's buses and closed branches."""
        shape = self._shape
        graph = nx.Graph()
        graph.pos = {}
        graph.zones = {}
        graph.node_to_zone = {}
        for bus in shape.buses:
            graph.add_node(bus.id)
            graph.pos[bus.id] = (bus.x, bus.y)
            zone = f"{bus.vn_kv:g} kV"
            graph.zones.setdefault(zone, []).append(bus.id)
            graph.node_to_zone[bus.id] = zone
        for branch in shape.branches:
            if branch.closed:
                graph.add_edge(branch.from_bus, branch.to_bus, weight=1.0)
        return graph

    def _check_init(self) -> None:
        """A network needs buses; it need not be connected (open switches)."""
        if not self.graph or len(self.graph.nodes) == 0:
            raise ValueError("The network has no buses")
        if self.capacity < 0:
            raise ValueError(f"Grid capacity must be non-negative, got {self.capacity}")
