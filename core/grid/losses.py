"""Who caused the network's losses: the step's power-flow losses shared out.

An AC power flow gives the loss of every line and transformer (pandapower's
``res_line.pl_mw``, ``res_trafo.pl_mw``): where energy was lost. It cannot say whose
loss it was. A line's loss is quadratic in its current, and the current is the sum of
the currents of everything below it, so the loss holds cross terms between elements
that belong to neither alone. A loss allocation is the rule that shares them out; the
rules here give every element of the network (each load, generator, storage unit and
participant's injection) its share of the step's losses in kW, adding up to the
network's total.

The rules to choose from (``LOSS_ALLOCATIONS``, by name):

    "bcdla"     ``BranchCurrentDecomposition``: each branch's current-dependent loss
                shared by the elements below it, by how much of the branch current
                each one makes (Carpaneto, Chicco & Sumaili Akilimali 2006). Needs a
                radial network. A share can be negative: an element whose current
                runs against the branch's lowers its loss and gets a credit. A
                transformer's no-load (iron) loss does not depend on any current and
                is not shared: it is left over (``LossShares.residual_kw``).
    "pro_rata"  ``ProRata``: the total shared by each element's active power, wherever
                it is. The simplest rule, ignoring the network; also the template for
                a new rule.

**Adding a rule.** Subclass ``LossAllocation``, set ``name`` and ``label`` (and
``radial_only`` if the rule needs a radial network), implement ``shares``, and add the
class to
``LOSS_ALLOCATIONS``. ``allocate`` does the rest: it checks the network, reads the
measured losses and reports what the rule left unallocated. Tests:
``tests/market/test_losses.py``, which every rule must pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

import numpy as np

# An element of the network, as pandapower names it: (table, row index).
Element = tuple[str, int]

# The tables whose elements draw or inject power, and the sign that turns their
# result into power drawn from the network (pandapower's load convention: + draws).
POWER_TABLES: Mapping[str, float] = {
    "load": 1.0,
    "storage": 1.0,
    "shunt": 1.0,
    "sgen": -1.0,
    "gen": -1.0,
}
# Below this current (per unit) a branch carries nothing worth sharing.
_TINY = 1e-12


@dataclass(frozen=True)
class LossShares:
    """The step's losses shared out.

    Attributes:
        method: The rule's ``name``.
        total_kw: The network's losses from the power flow: every line and
            transformer.
        by_element: Each element's share in kW, ``(table, index)`` as pandapower
            names it; negative is a credit. Elements with no share are left out.
        residual_kw: ``total_kw`` minus the shares' sum: what the rule left
            unallocated. 0 for ``pro_rata`` (up to rounding). For ``bcdla`` it is the
            transformers' no-load (iron) loss, about 0.5 kW on the thesis network:
            it flows while the transformer is energised, whatever the participants
            do, so the DSO keeps it.
    """

    method: str
    total_kw: float
    by_element: dict[Element, float] = field(default_factory=dict)
    residual_kw: float = 0.0

    def of(self, elements: list[Element]) -> float:
        """The summed share of ``elements`` (a participant's, say), in kW."""
        return sum(self.by_element.get(e, 0.0) for e in elements)


class LossAllocation:
    """A rule that shares the step's losses among the network's elements.

    Subclasses set ``name`` and implement ``shares``; ``allocate`` is the one
    method the market calls.
    """

    name: ClassVar[str] = ""
    label: ClassVar[str] = ""  # how the Studio names it
    radial_only: ClassVar[bool] = False

    def allocate(self, net: Any) -> LossShares:
        """The losses of ``net``, a pandapower network whose power flow has just
        run, shared out by this rule."""
        if self.radial_only and (loops := independent_loops(net)):
            raise ValueError(
                f"loss allocation {self.name!r} needs a radial network; this one has "
                f"{loops} loop(s) with its switches as set"
            )

        total = branch_losses_kw(net)
        found = self.shares(net, total)

        return LossShares(
            method=self.name,
            total_kw=sum(total.values()),
            by_element=found,
            residual_kw=sum(total.values()) - sum(found.values()),
        )

    def shares(self, net: Any, losses: Mapping[Element, float]) -> dict[Element, float]:
        """Each element's share in kW, given every branch's loss ``losses`` (kW,
        keyed ``("line", i)`` or ``("trafo", i)``)."""
        raise NotImplementedError


# --------------------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------------------
class BranchCurrentDecomposition(LossAllocation):
    """Branch current decomposition (BCDLA; Carpaneto, Chicco & Sumaili Akilimali,
    IEEE Trans. Power Systems 21(3), 2006).

    On a radial network the current of branch b is the sum of the currents drawn by
    the elements below it, I_b = Σ_e I_e, so its loss R_b·|I_b|² splits exactly into

        R_b · Re(I_e · conj(I_b))     for each element e below b,

    each element's own term in full and half of every cross term with another
    element. An element whose current runs against the branch's (a PV export where
    the branch imports) gets a negative share. Here the split is applied to each
    branch's current-dependent loss: element e's share of branch b is
    Re(I_e · conj(I_b)) / |I_b|² of it. A line's is its measured loss, ``pl_mw``. A
    transformer's is its copper loss (``trafo_copper_losses_kw``), not its measured
    ``pl_mw``, which also holds the no-load loss: that is a constant (the iron core
    is magnetised whatever flows), so dividing it by |I_b|² makes the shares blow up
    where the net transformer current is near zero (two households that balance each
    other get opposite shares many times the loss itself). The no-load loss is left
    unallocated, in ``LossShares.residual_kw``, and stays with the DSO.

    The currents are per unit, I_e = conj(S_e / V_bus), from the power flow's own
    results. Every element below a branch sits on the same side of any transformer
    (the network is radial, fed from its external grid), so a transformer's phase
    shift turns all of them alike and leaves the shares unchanged.
    """

    name = "bcdla"
    label = "Measured, shared by branch currents (BCDLA)"
    radial_only = True

    def shares(self, net: Any, losses: Mapping[Element, float]) -> dict[Element, float]:
        current = _element_currents(net)
        below = _elements_below(net, current)
        copper = trafo_copper_losses_kw(net)
        found: dict[Element, float] = {}

        for branch, loss_kw in losses.items():
            if branch[0] == "trafo" and branch in copper:
                loss_kw = max(0.0, min(loss_kw, copper[branch]))

            mine = below.get(branch, [])
            total = sum((current[e] for e in mine), 0j)

            if abs(total) ** 2 < _TINY:
                continue

            for e in mine:
                part = (current[e] * total.conjugate()).real / abs(total) ** 2
                found[e] = found.get(e, 0.0) + part * loss_kw

        return found


class ProRata(LossAllocation):
    """Pro rata: the network's total loss shared by each element's active power,
    |P_e| / Σ |P|, wherever the element is. The simplest rule there is (Conejo et
    al. 2002 compare it with the network-aware ones): it uses the power flow's total
    and nothing of its flows, so a household next to the transformer pays as one at
    the feeder's end. Kept as a reference and as the template for a new rule."""

    name = "pro_rata"
    label = "Measured, shared pro rata"

    def shares(self, net: Any, losses: Mapping[Element, float]) -> dict[Element, float]:
        power = {e: abs(s.real) for e, s in _element_powers(net).items()}
        weight = sum(power.values())
        total = sum(losses.values())

        if weight <= 0:
            return {}

        return {e: total * p / weight for e, p in power.items() if p > 0}


# Every rule, by the name a scenario gives it.
LOSS_ALLOCATIONS: dict[str, type[LossAllocation]] = {
    rule.name: rule for rule in (BranchCurrentDecomposition, ProRata)
}


def build_loss_allocation(name: str) -> LossAllocation:
    """The rule called ``name`` (``LOSS_ALLOCATIONS``)."""
    if name not in LOSS_ALLOCATIONS:
        raise ValueError(
            f"unknown loss allocation {name!r}; choose from {sorted(LOSS_ALLOCATIONS)}"
        )

    return LOSS_ALLOCATIONS[name]()


# --------------------------------------------------------------------------------------
# What the rules read from a solved network
# --------------------------------------------------------------------------------------
def independent_loops(net: Any) -> int:
    """How many independent loops the in-service network has with its switches as
    set (edges − buses + connected parts): 0 for a radial network. Parallel branches
    between the same two buses count as one: they share one subtree below, so the
    rules handle them."""
    import networkx as nx
    import pandapower.topology as top

    graph = nx.Graph(
        top.create_nxgraph(net, respect_switches=True, include_out_of_service=False)
    )
    parts = nx.number_connected_components(graph)

    return graph.number_of_edges() - graph.number_of_nodes() + parts


def branch_losses_kw(net: Any) -> dict[Element, float]:
    """Every line's and transformer's loss in the solved power flow, kW."""
    found = {}

    for table in ("line", "trafo"):
        result = net[f"res_{table}"]
        if len(result):
            for index, loss in result.pl_mw.items():
                if np.isfinite(loss):
                    found[(table, int(index))] = 1000.0 * float(loss)

    return found


def trafo_copper_losses_kw(net: Any) -> dict[Element, float]:
    """The current-dependent part of every transformer's loss, kW: its copper (winding)
    loss ``vkr% / 100 · S_n · (I / I_rated)²``, on the LV side's solved current
    ``res_trafo.i_lv_ka`` (``vkr_percent`` is the loss at rated current). What is left
    of the measured ``pl_mw`` is the no-load (iron) loss, ``pfe_kw`` at the
    transformer's voltage: on the thesis network 0.48 kW at every loading from 0 to
    4 times rated, within 0.01 kW. Parallel transformers count as one of ``parallel``
    times the rating. Out-of-service transformers have no entry."""
    found: dict[Element, float] = {}

    if not len(net.trafo) or not len(net.res_trafo):
        return found

    for index, row in net.trafo.iterrows():
        current_ka = float(net.res_trafo.at[index, "i_lv_ka"])

        if not np.isfinite(current_ka):
            continue

        parallel = float(row["parallel"]) if "parallel" in row.index else 1.0
        rated_mva = parallel * float(row["sn_mva"])
        rated_ka = rated_mva / (np.sqrt(3.0) * float(row["vn_lv_kv"]))
        found[("trafo", int(index))] = (
            float(row["vkr_percent"]) / 100.0 * rated_mva * 1000.0
            * (current_ka / rated_ka) ** 2
        )

    return found


def _element_powers(net: Any) -> dict[Element, complex]:
    """Each in-service element's complex power drawn from the network, MVA (load
    convention: + draws, a generator's output negative)."""
    found = {}

    for table, sign in POWER_TABLES.items():
        if not len(net[table]) or not len(net[f"res_{table}"]):
            continue

        result = net[f"res_{table}"]
        on = net[table].in_service

        for index in net[table].index[on]:
            p = float(result.at[index, "p_mw"])
            q = float(result.at[index, "q_mvar"]) if "q_mvar" in result else 0.0
            if np.isfinite(p) and (p or q):
                found[(table, int(index))] = sign * complex(p, q)

    return found


def _element_currents(net: Any) -> dict[Element, complex]:
    """Each element's current drawn from the network, per unit: conj(S / V) with
    its bus's solved voltage."""
    vm, va = net.res_bus.vm_pu, np.deg2rad(net.res_bus.va_degree)
    found = {}

    for (table, index), power in _element_powers(net).items():
        bus = int(net[table].at[index, "bus"])
        voltage = vm[bus] * np.exp(1j * va[bus])
        found[(table, index)] = (power / voltage).conjugate()

    return found


def _elements_below(net: Any, current: Mapping[Element, complex]) -> dict[Element, list]:
    """For every line and transformer, the elements below it: in the subtree away
    from the external grid, with the switches as set."""
    import networkx as nx
    import pandapower.topology as top

    graph = top.create_nxgraph(
        net, respect_switches=True, include_out_of_service=False, multi=True
    )
    roots = [int(b) for b in net.ext_grid.bus[net.ext_grid.in_service]]
    at_bus: dict[int, list] = {}

    for element in current:
        table, index = element
        at_bus.setdefault(int(net[table].at[index, "bus"]), []).append(element)

    found: dict[Element, list] = {}

    for root in roots:
        if root not in graph:
            continue
        tree = nx.bfs_tree(graph, root)  # parent -> child, away from the feed

        for parent, child in tree.edges():
            subtree = nx.descendants(tree, child) | {child}
            elements = [e for bus in subtree for e in at_bus.get(bus, [])]

            for key in graph[parent][child]:
                table, index = key[0], int(key[1])
                if table in ("line", "trafo"):
                    found[(table, index)] = elements

    return found
