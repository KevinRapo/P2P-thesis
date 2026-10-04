"""Participant mapping: placement rules and profile scaling (01-simbench-grid.md §3).

Why: an agent only has a physical effect if it sits on a bus and owns network
elements, and its demand and generation must fit the size the study wants. These
rules are needed twice, by the Studio (to propose and preview participants) and
later by the environment factory (to build the agents), so they live here once,
as plain functions over the contract records. No pandapower inside.

Placement (01 §3.1) turns a rule such as "8 households with PV" into explicit
participant entries of the experiment file. Scaling (01 §3.4) turns a profile
into the agent's own power.
"""

from __future__ import annotations

import random
import re
from collections import defaultdict, deque
from typing import Any, Sequence

from src_thesis.marketplace.grid.contract_new import ElementRecord, TopologyView

# Placement rules: type -> what it selects (shown in the Studio).
RULES = {
    "by_elements": "One agent per load, each owning that load and the "
    "generators at its bus",
    "household_with_pv": "Buses that have a household load (H0) and a PV "
    "generator; the agent owns both",
    "feeder_ends": "Buses at the end of a feeder (one connection only) that "
    "have a load",
    "spread": "Loads spread evenly over the feeders below the substation",
}
SCALING_MODES = ("none", "peak_kw", "energy_kwh")


def place(
    elements: Sequence[ElementRecord], topology: TopologyView, rule: dict[str, Any]
) -> list[dict[str, Any]]:
    """Participants placed on a network by a seeded rule (01 §3.1).

    Every agent owns one load and, unless another agent already owns them, the
    generators at its bus; its profiles are the owned elements' own (``native``).

    Args:
        elements: The network's loads, generators and storage.
        topology: The network's buses and branches.
        rule: ``{"type": <one of RULES>, "n": <agents>, "seed": <int>}``.

    Returns:
        Participant entries for the experiment file, in network order.

    Raises:
        ValueError: Unknown rule, or the network has fewer candidates than ``n``.
    """
    kind = rule.get("type", "by_elements")
    n = int(rule.get("n", 8))
    rng = random.Random(int(rule.get("seed", 1)))
    loads = [e for e in elements if e.element_type == "load"]
    if kind == "by_elements":
        chosen = _sample(loads, n, rng, "loads")
    elif kind == "household_with_pv":
        pv_buses = {
            e.bus
            for e in elements
            if e.element_type == "sgen" and e.profile_type.startswith("PV")
        }
        candidates = _first_per_bus(
            [e for e in loads if e.profile_type.startswith("H0-") and e.bus in pv_buses]
        )
        chosen = _sample(candidates, n, rng, "buses with a household load and PV")
    elif kind == "feeder_ends":
        degree = _degrees(topology)
        ends = {
            bus
            for bus, d in degree.items()
            if d == 1 and bus != topology.external_grid_bus
        }
        candidates = _first_per_bus([e for e in loads if e.bus in ends])
        chosen = _sample(candidates, n, rng, "feeder ends with a load")
    elif kind == "spread":
        chosen = _spread(loads, topology, n, rng)
    else:
        raise ValueError(f"Unknown placement rule {kind!r}; use one of {list(RULES)}")
    order = {e.id: i for i, e in enumerate(elements)}
    chosen.sort(key=lambda e: order[e.id])
    return _participants(chosen, elements)


def _sample(
    candidates: list[ElementRecord], n: int, rng: random.Random, what: str
) -> list[ElementRecord]:
    """``n`` candidates drawn without replacement, reproducibly."""
    if n < 1:
        raise ValueError("The number of agents must be at least 1")
    if len(candidates) < n:
        raise ValueError(
            f"The network has {len(candidates)} {what}, fewer than the {n} agents "
            "asked for"
        )
    return rng.sample(candidates, n)


def _first_per_bus(loads: list[ElementRecord]) -> list[ElementRecord]:
    """One load per bus (the first), so two agents never share a bus."""
    seen: set[str] = set()
    out = []
    for e in loads:
        if e.bus not in seen:
            seen.add(e.bus)
            out.append(e)
    return out


def _adjacency(topology: TopologyView) -> dict[str, set[str]]:
    """Bus -> neighbouring buses over closed branches."""
    adjacent: dict[str, set[str]] = defaultdict(set)
    for b in topology.branches:
        if b.closed:
            adjacent[b.from_bus].add(b.to_bus)
            adjacent[b.to_bus].add(b.from_bus)
    return adjacent


def _degrees(topology: TopologyView) -> dict[str, int]:
    """Number of closed branches at each bus."""
    return {bus: len(n) for bus, n in _adjacency(topology).items()}


def _feeders(topology: TopologyView) -> list[set[str]]:
    """The buses of each feeder: the subtrees below the first bus that branches.

    Walks down from the external grid while the network does not branch (through
    the transformer); each branch below the first fork is one feeder.
    """
    adjacent = _adjacency(topology)
    root = topology.external_grid_bus or next(iter(adjacent), None)
    if root is None:
        return []
    parent, node = None, root
    while True:
        children = [b for b in adjacent[node] if b != parent]
        if len(children) != 1:
            break
        parent, node = node, children[0]
    feeders = []
    for child in sorted(b for b in adjacent[node] if b != parent):
        seen, queue = {node, child}, deque([child])
        while queue:
            bus = queue.popleft()
            for nxt in adjacent[bus]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        feeders.append(seen - {node})
    return feeders


def _spread(
    loads: list[ElementRecord], topology: TopologyView, n: int, rng: random.Random
) -> list[ElementRecord]:
    """Loads drawn feeder by feeder in turn, so every feeder gets agents."""
    pools = []
    for buses in _feeders(topology):
        pool = _first_per_bus([e for e in loads if e.bus in buses])
        rng.shuffle(pool)
        if pool:
            pools.append(pool)
    if sum(len(p) for p in pools) < n:
        return _sample(_first_per_bus(loads), n, rng, "buses with a load")
    chosen: list[ElementRecord] = []
    while len(chosen) < n:
        for pool in pools:
            if pool and len(chosen) < n:
                chosen.append(pool.pop())
    return chosen


def _participants(
    chosen: list[ElementRecord], elements: Sequence[ElementRecord]
) -> list[dict[str, Any]]:
    """Participant entries: each owns its load and the free generators at its bus."""
    taken: set[str] = set()
    out = []
    for i, load in enumerate(chosen, start=1):
        sgens = [
            e.id
            for e in elements
            if e.element_type == "sgen" and e.bus == load.bus and e.id not in taken
        ]
        taken.update(sgens)
        out.append(
            {
                "id": f"agent_{i:02d}",
                "role": _role(load.profile_type),
                "bus": load.bus,
                "owns": {"loads": [load.id], "sgens": sgens},
                "profile": {"source": "native"},
                "scaling": {"mode": "none"},
                "battery": None,
            }
        )
    return out


def _role(profile: str) -> str:
    """A readable role from the load's profile, e.g. ``household`` for H0-A."""
    for pattern, role in (
        (r"H0-", "household"),
        (r"G\d-", "commercial"),
        (r"L\d-", "agricultural"),
    ):
        if re.match(pattern, profile):
            return role
    return "consumer"


def scale(
    window: list[float],
    year: list[float],
    mode: str,
    target: float | None,
    step_hours: float,
) -> list[float]:
    """Scale a profile to the agent's size (01 §3.4).

    Args:
        window: The values to scale (the time window shown or simulated).
        year: The same profile over its whole year, at the same resolution; the
            reference for the peak and the annual energy.
        mode: ``"none"`` (keep the values), ``"peak_kw"`` (the year's peak becomes
            ``target`` kW) or ``"energy_kwh"`` (the year's energy becomes
            ``target`` kWh).
        target: The peak in kW or the annual energy in kWh.
        step_hours: Length of one value in hours (0.25, 1 or 24).

    Raises:
        ValueError: Unknown mode, or a mode that needs a target without one.
    """
    if mode not in SCALING_MODES:
        raise ValueError(f"Unknown scaling mode {mode!r}; use one of {SCALING_MODES}")
    if mode == "none":
        return list(window)
    if target is None:
        raise ValueError(f"Scaling mode {mode!r} needs a target value")
    reference = (
        max(year, default=0.0)
        if mode == "peak_kw"
        else sum(year) * step_hours  # annual energy in kWh
    )
    if reference <= 0:
        return [0.0 for _ in window]
    return [v * float(target) / reference for v in window]
