"""Placing participants on a scenario's network.

A participant sits on one bus and takes over the loads, generators and storage
there. These rules belong to the scenario, not to the Studio: a notebook or an RL
run places participants the same way. The functions change the ``Scenario`` they
are given and leave saving to the caller.

Participants are placed by bus kind: what the bus carries, e.g. ``"load"``,
``"load+pv"`` or ``"load+storage"`` (``bus_kinds``). A participant that takes
over a SimBench storage unit gets that unit as its battery, with its energy
capacity and power limit, which cannot be changed (``set_battery``). A battery
added where the network has none takes its power limit by hand, or SimBench's
ratio of two hours (``simbench_battery``, ``BATTERY_PRESETS``).
"""

from __future__ import annotations

from typing import Iterable

from core.config.scenario import BatterySetup, ParticipantSetup, Scenario
from core.grid import simbench
from core.grid.contract import ElementRecord, NetworkRef

# --------------------------------------------------------------------------------------
# Batteries sized like SimBench's
# --------------------------------------------------------------------------------------
# Measured on the 84 storage units of the twelve 1-LV-*--1/2-sw networks (SimBench's
# future scenarios; scenario 0 has none): energy ÷ power is 2.0 h for every unit
# (1.98 to 2.02 after rounding), efficiency 0.95.
SIMBENCH_STORAGE_HOURS = 2.0
# Capacity in kWh at the 10th, 50th and 90th percentile of those units (3.4 to
# 236 kWh in all); the power follows from SIMBENCH_STORAGE_HOURS.
BATTERY_PRESETS = {"small": 6.8, "typical": 13.7, "large": 66.4}


def simbench_battery(capacity_kwh: float, **kwargs) -> BatterySetup:
    """A battery of ``capacity_kwh`` with SimBench's power limit, capacity ÷ 2 h.
    Other ``BatterySetup`` fields can be passed as keywords."""
    power = capacity_kwh / SIMBENCH_STORAGE_HOURS
    return BatterySetup(capacity_kwh=capacity_kwh, max_power_kw=power, **kwargs)


def battery_preset(name: str, **kwargs) -> BatterySetup:
    """A SimBench-sized battery by name: ``"small"``, ``"typical"`` or ``"large"``
    (``BATTERY_PRESETS``)."""
    return simbench_battery(BATTERY_PRESETS[name], **kwargs)


def storage_battery(elements: list[ElementRecord]) -> BatterySetup | None:
    """The battery of the SimBench storage units among ``elements``: their energy
    capacity and power limit added up; ``None`` when there is none."""
    units = [e for e in elements if e.element_type == "storage" and e.energy_kwh > 0]

    if not units:
        return None

    return BatterySetup(
        capacity_kwh=sum(e.energy_kwh for e in units),
        max_power_kw=sum(e.rated_kw for e in units),
    )


# --------------------------------------------------------------------------------------
# Placing participants
# --------------------------------------------------------------------------------------
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


def bus_kinds(scenario: Scenario) -> dict[str, str]:
    """Each bus of the scenario's network with elements, and what is on it:
    ``"load"``, ``"load+pv"``, ``"load+storage"``, ``"load+gen+storage"``, ...
    (``simbench.bus_kinds``)."""
    return simbench.bus_kinds(NetworkRef("simbench", scenario.grid.code))


def kind_counts(scenario: Scenario) -> dict[str, int]:
    """How many buses of each kind the network has (``bus_kinds``), most first."""
    counts: dict[str, int] = {}

    for kind in bus_kinds(scenario).values():
        counts[kind] = counts.get(kind, 0) + 1

    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def place_all(
    scenario: Scenario,
    kinds: str | Iterable[str],
    battery_kwh: float = 0.0,
    battery_power_kw: float | None = None,
) -> int:
    """Replace the participants: one on every bus whose kind (``bus_kinds``) is in
    ``kinds``, e.g. ``["load", "load+pv", "load+storage"]``.

    A participant on a bus with SimBench storage gets that unit as its battery.
    Participants on other buses with a generator (pv or gen) get a battery of
    ``battery_kwh`` when it is above 0, with ``battery_power_kw`` as its power
    limit (``None``: no limit).

    Returns:
        The number of participants placed.
    """
    wanted = {kinds} if isinstance(kinds, str) else set(kinds)
    kind = bus_kinds(scenario)
    scenario.participants = []

    for bus, elements in sorted(elements_by_bus(scenario).items()):
        if kind.get(bus) not in wanted:
            continue

        p = _new(scenario, bus, elements)
        generates = any(e.element_type == "sgen" for e in elements)

        if p.battery is None and battery_kwh > 0 and generates:
            p.battery = BatterySetup(
                capacity_kwh=battery_kwh, max_power_kw=battery_power_kw
            )

        scenario.participants.append(p)

    return len(scenario.participants)


def participant_storage(scenario: Scenario, participant_id: str) -> BatterySetup | None:
    """The battery of the SimBench storage a participant took over (capacity and
    power limit; ``storage_battery``); ``None`` when it took over none."""
    p = _participant(scenario, participant_id)
    owned = [e for e in elements_by_bus(scenario).get(p.bus, []) if e.id in p.owns]

    return storage_battery(owned)


def set_battery(
    scenario: Scenario, participant_id: str, battery: BatterySetup | None
) -> str:
    """Give a participant a battery (``None``: remove it).

    A participant that took over SimBench storage has that unit as its battery:
    its capacity and power limit cannot be changed or removed, only its other
    settings (start SoC, SoC window, efficiencies).

    Returns:
        What happened, for a notification.

    Raises:
        ValueError: The participant does not exist, or the change would replace
            its SimBench storage.
    """
    p = _participant(scenario, participant_id)
    storage = participant_storage(scenario, participant_id)

    if storage is not None and (
        battery is None
        or abs(battery.capacity_kwh - storage.capacity_kwh) > 1e-9
        or battery.max_power_kw != storage.max_power_kw
    ):
        raise ValueError(
            f"{participant_id} took over SimBench storage of "
            f"{storage.capacity_kwh:g} kWh, {storage.max_power_kw:g} kW: its "
            "capacity and power are fixed"
        )

    p.battery = battery

    if battery is None:
        return f"{participant_id}: battery removed"

    return f"{participant_id}: battery saved"


def clear(scenario: Scenario) -> None:
    """Remove every participant."""
    scenario.participants = []


def _new(scenario: Scenario, bus: str, elements: list[ElementRecord]):
    taken = {p.id for p in scenario.participants}
    n = 1

    while f"P{n}" in taken:
        n += 1

    return ParticipantSetup(
        f"P{n}", bus, [e.id for e in elements], battery=storage_battery(elements)
    )


def _participant(scenario: Scenario, participant_id: str) -> ParticipantSetup:
    p = next((x for x in scenario.participants if x.id == participant_id), None)
    if p is None:
        raise ValueError(f"No participant {participant_id}")
    return p
