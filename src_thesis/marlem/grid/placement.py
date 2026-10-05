"""Participant mapping: placement rules and profile scaling (01-simbench-grid.md §3).

Why: an agent only has a physical effect if it sits on a bus and owns network
elements, and its demand and generation must fit the size the study wants. These
rules are needed twice, by the Studio (to propose and preview participants) and
later by the environment factory (to build the agents), so they live here once,
as plain functions over the contract records. No pandapower inside.

Placement (01 §3.1) turns a rule such as "8 buses with a farm or household load
and PV" into explicit participant entries of the experiment file. Scaling
(01 §3.4) turns a profile into the agent's own power.
"""

from __future__ import annotations

import random
from collections import defaultdict, deque
from typing import Any, Callable, Sequence

from src_thesis.marlem.grid.contract import ElementRecord, TopologyView

# A placement rule is a set of filters on the network's buses (01 §3.1):
#   loads       load classes a bus must have at least one of (empty: any load)
#   generation  "any" (no condition), "pv", "generator" (any sgen) or "none"
#   storage     "any", "with" or "without"
#   position    "anywhere", "spread" (evenly over the feeders) or "feeder_ends"
#   owns        "bus" (every load, generator and storage at the bus) or
#               "matching" (only the matching loads, plus the generators and
#               storage); the rest of the bus stays background
#   n, seed     how many agents, and the seed of the draw
GENERATION = {
    "any": "No condition",
    "pv": "With PV",
    "generator": "With any generator",
    "none": "Without generator",
}
STORAGE = {"any": "No condition", "with": "With storage", "without": "Without storage"}
POSITIONS = {
    "anywhere": "Anywhere",
    "spread": "Spread over the feeders",
    "feeder_ends": "Feeder ends only",
}
OWNS = {"bus": "Everything at the bus", "matching": "Only the matching loads"}
DEFAULT_RULE: dict[str, Any] = {
    "loads": [],
    "generation": "any",
    "storage": "any",
    "position": "anywhere",
    "owns": "bus",
    "n": 8,
    "seed": 1,
}
SCALING_MODES = ("none", "peak_kw", "energy_kwh")

# Classifies a load profile, e.g. "H0-A" -> "household" (ProfileService's classes).
Classify = Callable[[str], str]


def candidates(
    elements: Sequence[ElementRecord],
    topology: TopologyView,
    rule: dict[str, Any],
    classify: Classify,
) -> list[str]:
    """The buses that pass a rule's filters, in network order (01 §3.1).

    Args:
        elements: The network's loads, generators and storage.
        topology: The network's buses and branches.
        rule: The filters (see ``DEFAULT_RULE``); missing keys take the default.
        classify: Load profile name -> load class.

    Raises:
        ValueError: An unknown filter value.
    """
    rule = {**DEFAULT_RULE, **rule}
    _check(rule)
    wanted = set(rule["loads"] or [])
    at = _by_bus(elements)
    ends = None
    if rule["position"] == "feeder_ends":
        ends = {
            bus
            for bus, d in _degrees(topology).items()
            if d == 1 and bus != topology.external_grid_bus
        }
    out = []
    for bus, items in at.items():
        loads = [e for e in items if e.element_type == "load"]
        sgens = [e for e in items if e.element_type == "sgen"]
        storage = [e for e in items if e.element_type == "storage"]
        if not any(not wanted or classify(e.profile_type) in wanted for e in loads):
            continue
        if not _generation_ok(rule["generation"], sgens):
            continue
        if rule["storage"] == "with" and not storage:
            continue
        if rule["storage"] == "without" and storage:
            continue
        if ends is not None and bus not in ends:
            continue
        out.append(bus)
    return out


def place(
    elements: Sequence[ElementRecord],
    topology: TopologyView,
    rule: dict[str, Any],
    classify: Classify,
) -> list[dict[str, Any]]:
    """Participants placed by a rule: one agent per chosen bus (01 §3.1).

    ``n`` buses are drawn from the ``candidates`` (seeded; ``spread`` takes them
    feeder by feeder in turn). Each agent owns what ``owns`` says, with the owned
    elements' own SimBench profiles (``native``) and no scaling or battery.

    Raises:
        ValueError: An unknown filter value, or fewer candidates than ``n``.
    """
    rule = {**DEFAULT_RULE, **rule}
    n = int(rule["n"])
    if n < 1:
        raise ValueError("The number of agents must be at least 1")
    buses = candidates(elements, topology, rule, classify)
    if len(buses) < n:
        raise ValueError(
            f"{len(buses)} buses pass the filters, fewer than the {n} agents asked "
            "for: widen the filters or ask for fewer agents"
        )
    rng = random.Random(int(rule["seed"]))
    if rule["position"] == "spread":
        chosen = _spread(buses, topology, n, rng)
    else:
        chosen = rng.sample(buses, n)
    order = {bus: i for i, bus in enumerate(buses)}
    chosen.sort(key=order.__getitem__)
    at = _by_bus(elements)
    wanted = set(rule["loads"] or [])
    out = []
    for i, bus in enumerate(chosen, start=1):
        items = at[bus]
        loads = [
            e.id
            for e in items
            if e.element_type == "load"
            and (
                rule["owns"] == "bus"
                or not wanted
                or classify(e.profile_type) in wanted
            )
        ]
        owns = {
            "loads": loads,
            "sgens": [e.id for e in items if e.element_type == "sgen"],
        }
        storage = [e.id for e in items if e.element_type == "storage"]
        if storage:
            owns["storage"] = storage
        first = next(e for e in items if e.id == loads[0])
        out.append(
            {
                "id": f"agent_{i:02d}",
                "role": classify(first.profile_type)
                + ("_prosumer" if owns["sgens"] else ""),
                "bus": bus,
                "owns": owns,
                "profile": {"source": "native"},
                "scaling": {"mode": "none"},
                "battery": None,
            }
        )
    return out


def _check(rule: dict[str, Any]) -> None:
    """Reject unknown filter values with a clear message."""
    for key, allowed in (
        ("generation", GENERATION),
        ("storage", STORAGE),
        ("position", POSITIONS),
        ("owns", OWNS),
    ):
        if rule[key] not in allowed:
            raise ValueError(f"Unknown {key} {rule[key]!r}; use one of {list(allowed)}")


def _generation_ok(condition: str, sgens: list[ElementRecord]) -> bool:
    """Whether a bus's generators meet the generation condition."""
    if condition == "pv":
        return any(e.profile_type.startswith("PV") for e in sgens)
    if condition == "generator":
        return bool(sgens)
    if condition == "none":
        return not sgens
    return True


def _by_bus(elements: Sequence[ElementRecord]) -> dict[str, list[ElementRecord]]:
    """Bus -> its elements, buses in the order they first appear."""
    at: dict[str, list[ElementRecord]] = {}
    for e in elements:
        at.setdefault(e.bus, []).append(e)
    return at


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
    buses: list[str], topology: TopologyView, n: int, rng: random.Random
) -> list[str]:
    """Buses drawn feeder by feeder in turn, so every feeder gets agents."""
    candidates_ = set(buses)
    pools = []
    for feeder in _feeders(topology):
        pool = sorted(feeder & candidates_)
        rng.shuffle(pool)
        if pool:
            pools.append(pool)
    if sum(len(p) for p in pools) < n:  # candidates outside any feeder
        return rng.sample(buses, n)
    chosen: list[str] = []
    while len(chosen) < n:
        for pool in pools:
            if pool and len(chosen) < n:
                chosen.append(pool.pop())
    return chosen


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
