"""One power flow per market step on a SimBench network.

The network's own elements follow their SimBench profiles, except the ones the
participants own: those are switched off and replaced by each participant's net
injection at its bus (what it physically did in the step, never its trades). It
also gives the market the way between two buses: distance, lines and zones.
Ported from the refactor branch's step-time model.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from core.config.scenario import GridSetup
from core.grid import simbench
from core.grid.contract import (
    GridAssessment,
    GridLimits,
    GridPath,
    NetworkRef,
    ParticipantInjection,
)


# --------------------------------------------------------------------------------------
# The step-time grid
# --------------------------------------------------------------------------------------
# pandapower's ``recycle``: between steps only the loads' and generators' power
# changes (never the topology or the transformers), so the internal network model
# and the run options are built once and reused; only the bus power is refreshed
# and the equations solved again. The results are the same (same Newton-Raphson
# solve, same tolerance); a step's power flow takes about a third of the time.
RECYCLE = {"trafo": False, "gen": False, "bus_pq": True}


class SimBenchGrid:
    """A working copy of the network, stepped with the market.

    Args:
        setup: The network, the day, the step length, the background and limits.
        owned: Element IDs each participant owns (they are replaced by injections).
    """

    #: ``RECYCLE`` (default) or ``None`` to rebuild everything at every step.
    recycle: dict | None = RECYCLE

    def __init__(self, setup: GridSetup, owned: dict[str, list[str]]) -> None:
        if setup.step_hours not in (1.0, 0.25):
            raise ValueError("step_hours must be 1.0 or 0.25")

        self.setup = setup
        self.owned = owned
        self.ref = NetworkRef("simbench", setup.code)
        self.limits = GridLimits(
            setup.v_min_pu, setup.v_max_pu, setup.line_max_percent, None
        )
        self._net: Any = None
        self._bus_index: dict[str, int] = {}
        self._owned_rows: dict[str, list[int]] = {}
        self._static: dict[tuple[str, str], Any] = {}
        self._loads: dict[str, int] = {}
        self._graph: Any = None
        self._zones: dict[int, str] = {}
        self._roots: set[int] = set()

    # --- Preparing the network -------------------------------------------------------
    def reset(self) -> None:
        """Load a fresh copy of the network for the configured day."""
        net = simbench._working_copy(self.ref)
        self._net = net
        self._graph = None
        self._zones = {}
        self._bus_index = {name: i for i, name in simbench._bus_ids(net).items()}
        self._loads = {}
        wanted = {e for ids in self.owned.values() for e in ids}
        self._owned_rows = {
            table: [
                int(i)
                for i, row in net[table].iterrows()
                if _element_id(row, table, i) in wanted
            ]
            for table in ("load", "sgen", "storage")
        }
        self._static = {
            (t, c): net[t][c].copy()
            for t in ("load", "sgen", "storage")
            for c in ("p_mw", "q_mvar")
            if c in net[t]
        }

    def _apply_background(self, step: int) -> None:
        """Every element at its value for ``step``; owned elements off."""
        net = self._net

        for (table, column), values in self._static.items():
            net[table][column] = values.copy()

        if simbench._has_profiles(net):
            if self.setup.step_hours == 1.0:
                rows = list(simbench.profile_rows(self.setup.day, step % 24))
            else:
                rows = [simbench.profile_rows(self.setup.day, 0).start + step % 96]
            for (table, column), df in simbench._absolute_profiles(self.ref).items():
                if table not in ("load", "sgen", "storage") or df.empty:
                    continue
                values = df.iloc[rows].mean()
                net[table].loc[values.index, column] = values.values

        factor = 0.0 if self.setup.background == "off" else 1.0

        for table in ("load", "sgen", "storage"):
            if not len(net[table]):
                continue
            for column in ("p_mw", "q_mvar"):
                if column not in net[table]:
                    continue
                net[table][column] = net[table][column] * factor
                if self._owned_rows[table]:
                    net[table].loc[self._owned_rows[table], column] = 0.0

    # --- One power flow --------------------------------------------------------------
    def assess(
        self, step: int, injections: Sequence[ParticipantInjection]
    ) -> GridAssessment:
        """Run the power flow for ``step`` with the participants' injections. A flow
        that does not converge is reported as such, not raised."""
        import pandapower as pp

        if self._net is None:
            self.reset()

        net = self._net
        self._apply_background(step)

        for inj in injections:
            if inj.bus_id not in self._bus_index:
                raise ValueError(f"{inj.participant_id}: no bus {inj.bus_id!r}")

            p_mw = -inj.net_injection_kw / 1000.0  # a negative load injects
            index = self._loads.get(inj.participant_id)

            if index is None:
                index = int(
                    pp.create_load(
                        net,
                        self._bus_index[inj.bus_id],
                        p_mw=p_mw,
                        q_mvar=0.0,
                        name=f"injection {inj.participant_id}",
                    )
                )
                self._loads[inj.participant_id] = index

            net.load.loc[index, "p_mw"] = p_mw
            net.load.loc[index, "q_mvar"] = 0.0

        try:
            pp.runpp(net, algorithm="nr", recycle=self.recycle)
        except pp.LoadflowNotConverged:
            return simbench._not_converged(step, [])

        return simbench._assessment(net, step, self.setup.step_hours, [], self.limits)

    # --- Distances, paths and zones -------------------------------------------------
    def electrical_distance(self, bus_a: str, bus_b: str) -> float:
        """Line length in km between two buses (transformers count 0): the
        shortest-path electrical distance d_ij of [P1] §3.5.1."""
        return self.path(bus_a, bus_b).distance_km

    def path(self, bus_a: str, bus_b: str) -> GridPath:
        """The shortest way between two buses along the lines: its length d_ij
        ([P1] §3.5.1), the lines on it (for the congestion of [P1] eq. 8a) and the
        zone of each end ([P1] §3.5.4, for the zone bonus of eq. 8e)."""
        import networkx as nx

        graph = self._topology()
        a, b = self._bus_index[bus_a], self._bus_index[bus_b]
        nodes = nx.shortest_path(graph, a, b, weight="weight")

        return self._along(graph, nodes)

    def path_upstream(self, bus: str) -> GridPath:
        """The way from a bus to where the upstream grid feeds the network: the
        nearest transformer's low-voltage busbar (or the external grid bus). The
        route of energy bought from or sold to the DSO."""
        import networkx as nx

        graph = self._topology()
        a = self._bus_index[bus]

        if not self._roots:
            return GridPath(0.0, (), self._zones[a], self._zones[a], bus, bus)

        _, nodes = nx.multi_source_dijkstra(graph, self._roots, a, weight="weight")

        return self._along(graph, nodes[::-1])

    def _along(self, graph: Any, nodes: list[int]) -> GridPath:
        """The path through ``nodes``: its length, its lines, the zones of its ends."""
        lines = tuple(
            graph.edges[u, v]["line"]
            for u, v in zip(nodes, nodes[1:])
            if graph.edges[u, v]["line"]
        )
        km = sum(graph.edges[u, v]["weight"] for u, v in zip(nodes, nodes[1:]))
        names = simbench._bus_ids(self._net)

        return GridPath(
            float(km),
            lines,
            self._zones[nodes[0]],
            self._zones[nodes[-1]],
            names[nodes[0]],
            names[nodes[-1]],
        )

    def line_table(self) -> dict[str, tuple[float, float]]:
        """Every line by the IDs of ``GridAssessment.line_loading_percent``: its
        length (km) and its rating (kW): √3 · rated voltage of its bus · I_max."""
        if self._net is None:
            self.reset()

        net = self._net
        out = {}

        for i, row in net.line.iterrows():
            kv = float(net.bus.at[row.from_bus, "vn_kv"])
            rating = math.sqrt(3) * kv * float(row.max_i_ka) * 1000.0
            out[simbench._branch_name(net.line, i, "line")] = (
                float(row.length_km),
                rating,
            )

        return out

    def _topology(self) -> Any:
        """The network as a weighted graph (built once per reset): lines weigh
        their length, transformers and bus-to-bus switches 0. Also fills the zones."""
        import networkx as nx

        if self._net is None:
            self.reset()

        if self._graph is not None:
            return self._graph

        net = self._net
        graph = nx.Graph()
        graph.add_nodes_from(int(i) for i in net.bus.index)

        for i, row in net.line.iterrows():
            graph.add_edge(
                int(row.from_bus),
                int(row.to_bus),
                weight=float(row.length_km),
                line=simbench._branch_name(net.line, i, "line"),
            )

        for _, row in net.switch[net.switch.et == "b"].iterrows():
            graph.add_edge(int(row.bus), int(row.element), weight=0.0, line="")

        roots = {int(b) for b in net.trafo.lv_bus} or {int(b) for b in net.ext_grid.bus}
        self._roots = roots & set(graph.nodes)
        self._zones = self._feeders(graph)

        for _, row in net.trafo.iterrows():
            graph.add_edge(int(row.hv_bus), int(row.lv_bus), weight=0.0, line="")

        self._graph = graph

        return graph

    def _feeders(self, graph: Any) -> dict[int, str]:
        """Each bus's zone: the feeder it hangs on ([P1] §3.5.4 leaves zones open).
        Without the transformers, every bus is reached from the nearest
        transformer's low-voltage bus (or the external grid); the first bus after
        it names the feeder. The low-voltage busbar itself is its own zone."""
        import networkx as nx

        names = simbench._bus_ids(self._net)

        if not self._roots:
            return {int(b): "" for b in graph.nodes}

        _, paths = nx.multi_source_dijkstra(graph, self._roots, weight="weight")
        zones = {}

        for bus in graph.nodes:
            way = paths.get(bus)
            if way is None:
                zones[bus] = names[bus]
            else:
                zones[bus] = names[way[1]] if len(way) > 1 else names[way[0]]

        return zones


def _element_id(row: Any, table: str, i: Any) -> str:
    """An element's ID, as in ``simbench.elements``."""
    name = row.get("name")
    return str(name) if isinstance(name, str) else f"{table} {i}"
