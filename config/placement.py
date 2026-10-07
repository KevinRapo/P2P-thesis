"""Placing participants on a scenario's network.

A participant sits on one bus and takes over the loads, generators and storage
there. These rules belong to the scenario, not to the Studio: a notebook or an RL
run places participants the same way. The functions change the ``Scenario`` they
are given and leave saving to the caller.
"""

from __future__ import annotations

from config.scenario import BatterySetup, ParticipantSetup, Scenario
from grid import simbench
from grid.contract import ElementRecord, NetworkRef


def elements_by_bus(scenario: Scenario) -> dict[str, list[ElementRecord]]:
    """The scenario's network: its loads, generators and storage, grouped by bus."""
    ref = NetworkRef("simbench", scenario.grid.code)
    out: dict[str, list[ElementRecord]] = {}
    for e in simbench.elements(ref):
        out.setdefault(e.bus, []).append(e)
    return out


def toggle(scenario: Scenario, bus: str) -> str:
    """Add a participant on ``bus`` (owning its elements) or remove the one there.

    Returns:
        What happened, for a notification.
    """
    here = [p for p in scenario.participants if p.bus == bus]
    if here:
        scenario.participants = [p for p in scenario.participants if p.bus != bus]
        return f"Removed {here[0].id} from {bus}"
    elements = elements_by_bus(scenario).get(bus, [])
    if not elements:
        return f"{bus} has no load or generator to take over"
    p = _new(scenario, bus, elements)
    scenario.participants.append(p)
    return f"Added {p.id} on {bus}"


def place_all(scenario: Scenario, which: str, battery_kwh: float = 0.0) -> int:
    """Replace the participants: one per bus with a load (``"loads"``) or with a
    load and a generator (``"prosumers"``). Buses with PV get a battery of
    ``battery_kwh`` when it is above 0.

    Returns:
        The number of participants placed.
    """
    scenario.participants = []
    for bus, elements in sorted(elements_by_bus(scenario).items()):
        types = {e.element_type for e in elements}
        if "load" not in types:
            continue
        if which == "prosumers" and "sgen" not in types:
            continue
        p = _new(scenario, bus, elements)
        if battery_kwh > 0 and "sgen" in types:
            p.battery = BatterySetup(capacity_kwh=battery_kwh)
        scenario.participants.append(p)
    return len(scenario.participants)


def clear(scenario: Scenario) -> None:
    """Remove every participant."""
    scenario.participants = []


def _new(scenario: Scenario, bus: str, elements: list[ElementRecord]):
    taken = {p.id for p in scenario.participants}
    n = 1
    while f"P{n}" in taken:
        n += 1
    return ParticipantSetup(f"P{n}", bus, [e.id for e in elements])
