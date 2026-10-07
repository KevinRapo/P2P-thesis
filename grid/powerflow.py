"""One power flow per market step on a SimBench network.

The network's own elements follow their SimBench profiles, except the ones the
participants own: those are switched off and replaced by each participant's net
injection at its bus (what it physically did in the step, never its trades).
Ported from the refactor branch's step-time model.
"""

from __future__ import annotations

from typing import Any, Sequence

from config.scenario import GridSetup
from grid import simbench
from grid.contract import GridAssessment, GridLimits, NetworkRef, ParticipantInjection


# --------------------------------------------------------------------------------------
# The step-time grid
# --------------------------------------------------------------------------------------
class SimBenchGrid:
    """A working copy of the network, stepped with the market.

    Args:
        setup: The network, the day, the step length, the background and limits.
        owned: Element IDs each participant owns (they are replaced by injections).
    """

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

    # --- Preparing the network -------------------------------------------------------
    def reset(self) -> None:
        """Load a fresh copy of the network for the configured day."""
        net = simbench._working_copy(self.ref)
        self._net = net
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
            pp.runpp(net, algorithm="nr")
        except pp.LoadflowNotConverged:
            return simbench._not_converged(step, [])
        return simbench._assessment(net, step, self.setup.step_hours, [], self.limits)

    # --- Distances -------------------------------------------------------------------
    def electrical_distance(self, bus_a: str, bus_b: str) -> float:
        """Line length in km between two buses (transformers count 0)."""
        import networkx as nx

        if self._net is None:
            self.reset()
        graph = nx.Graph()
        for _, row in self._net.line.iterrows():
            graph.add_edge(int(row.from_bus), int(row.to_bus), weight=row.length_km)
        for _, row in self._net.trafo.iterrows():
            graph.add_edge(int(row.hv_bus), int(row.lv_bus), weight=0.0)
        for _, row in self._net.switch[self._net.switch.et == "b"].iterrows():
            graph.add_edge(int(row.bus), int(row.element), weight=0.0)
        return float(
            nx.shortest_path_length(
                graph,
                self._bus_index[bus_a],
                self._bus_index[bus_b],
                weight="weight",
            )
        )


def _element_id(row: Any, table: str, i: Any) -> str:
    """An element's ID, as in ``simbench.elements``."""
    name = row.get("name")
    return str(name) if isinstance(name, str) else f"{table} {i}"
