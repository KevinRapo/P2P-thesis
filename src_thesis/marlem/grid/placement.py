"""Participant mapping: which buses are participants, and profile scaling
(01-simbench-grid.md §3).

Why: an agent only has a physical effect if it sits on a bus and owns network
elements, and its demand and generation must fit the size the study wants. These
rules are needed twice, by the Studio (to propose and preview participants) and
later by the environment factory (to build the agents), so they live here once,
as plain functions over the contract records. No pandapower inside.

Placement (01 §3.1) is one rule: a bus with **flexibility**, any generator or a
storage unit, can be a participant; a bus with only regular load is background
(``grid.background``, 01 §3.5). Scaling (01 §3.4) turns a profile into the
agent's own power.
"""

from __future__ import annotations

from typing import Any, Sequence

from src_thesis.marlem.grid.contract import ElementRecord

SCALING_MODES = ("none", "peak_kw", "energy_kwh")


def candidates(elements: Sequence[ElementRecord]) -> list[str]:
    """The buses that can be participants: those with a generator or storage.

    Args:
        elements: The network's loads, generators and storage.

    Returns:
        Bus IDs in network order.
    """
    return [
        bus
        for bus, items in _by_bus(elements).items()
        if any(e.element_type in ("sgen", "storage") for e in items)
    ]


def place(elements: Sequence[ElementRecord]) -> list[dict[str, Any]]:
    """One participant per flexible bus (01 §3.1).

    Each owns everything at its bus (loads, generators, storage), with the owned
    elements' own SimBench profiles (``native``) and no scaling or battery. Buses
    with only load are not participants: they stay background.

    Returns:
        Participant entries for the experiment file's ``participants`` list, in
        network order.
    """
    at = _by_bus(elements)
    out = []
    for i, bus in enumerate(candidates(elements), start=1):
        items = at[bus]
        owns: dict[str, list[str]] = {
            "loads": [e.id for e in items if e.element_type == "load"],
            "sgens": [e.id for e in items if e.element_type == "sgen"],
        }
        storage = [e.id for e in items if e.element_type == "storage"]
        if storage:
            owns["storage"] = storage
        out.append(
            {
                "id": f"agent_{i:02d}",
                "role": _role(bool(owns["sgens"]), bool(storage)),
                "bus": bus,
                "owns": owns,
                "profile": {"source": "native"},
                "scaling": {"mode": "none"},
                "battery": None,
            }
        )
    return out


def _role(generator: bool, storage: bool) -> str:
    """A readable role from the flexibility the bus has."""
    if generator and storage:
        return "generator_storage"
    return "generator" if generator else "storage"


def _by_bus(elements: Sequence[ElementRecord]) -> dict[str, list[ElementRecord]]:
    """Bus -> its elements, buses in the order they first appear."""
    at: dict[str, list[ElementRecord]] = {}
    for e in elements:
        at.setdefault(e.bus, []).append(e)
    return at


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
