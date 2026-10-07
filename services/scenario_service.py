"""ScenarioService: the scenario the Studio edits, kept on disk.

The Studio restarts on every code change, so the scenario is saved after every edit
and read back at start. Placing participants also lives here: a participant sits on
one bus and takes over the loads, generators and storage there.
"""

from __future__ import annotations

from pathlib import Path

from config import store
from config.scenario import BatterySetup, ParticipantSetup, Scenario
from grid import simbench
from grid.contract import ElementRecord, NetworkRef


# --------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------
class ScenarioService:
    """The current scenario, and placing participants on its network.

    Args:
        path: Where the scenario is kept (``Workspace.scenario_file``).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._scenario: Scenario | None = None

    # --- The current scenario --------------------------------------------------------
    def current(self) -> Scenario:
        """The scenario being edited: the saved one, else a new default one."""
        if self._scenario is None:
            try:
                self._scenario = store.load(self.path)
            except (OSError, ValueError, TypeError, KeyError):
                self._scenario = Scenario()
        return self._scenario

    def save(self) -> None:
        """Keep the current scenario on disk."""
        store.save(self.current(), self.path)

    def set_network(self, code: str) -> None:
        """Use another network; participants belong to the old one and are removed."""
        s = self.current()
        if s.grid.code != code:
            s.grid.code = code
            s.participants = []
        self.save()

    # --- Placing participants --------------------------------------------------------
    def elements_by_bus(self) -> dict[str, list[ElementRecord]]:
        """The current network's loads, generators and storage, grouped by bus."""
        ref = NetworkRef("simbench", self.current().grid.code)
        out: dict[str, list[ElementRecord]] = {}
        for e in simbench.elements(ref):
            out.setdefault(e.bus, []).append(e)
        return out

    def toggle(self, bus: str) -> str:
        """Add a participant on ``bus`` (owning its elements) or remove the one
        there. Returns what happened, for a notification."""
        s = self.current()
        here = [p for p in s.participants if p.bus == bus]
        if here:
            s.participants = [p for p in s.participants if p.bus != bus]
            self.save()
            return f"Removed {here[0].id} from {bus}"
        elements = self.elements_by_bus().get(bus, [])
        if not elements:
            return f"{bus} has no load or generator to take over"
        p = self._new(bus, elements)
        s.participants.append(p)
        self.save()
        return f"Added {p.id} on {bus}"

    def place_all(self, which: str, battery_kwh: float = 0.0) -> int:
        """Replace the participants: one per bus with a load (``"loads"``) or with
        a load and a generator (``"prosumers"``). Buses with PV get a battery of
        ``battery_kwh`` when it is above 0. Returns the number placed."""
        s = self.current()
        s.participants = []
        for bus, elements in sorted(self.elements_by_bus().items()):
            types = {e.element_type for e in elements}
            if "load" not in types:
                continue
            if which == "prosumers" and "sgen" not in types:
                continue
            p = self._new(bus, elements)
            if battery_kwh > 0 and "sgen" in types:
                p.battery = BatterySetup(capacity_kwh=battery_kwh)
            s.participants.append(p)
        self.save()
        return len(s.participants)

    def clear(self) -> None:
        """Remove every participant."""
        self.current().participants = []
        self.save()

    def _new(self, bus: str, elements: list[ElementRecord]) -> ParticipantSetup:
        taken = {p.id for p in self.current().participants}
        n = 1
        while f"P{n}" in taken:
            n += 1
        return ParticipantSetup(f"P{n}", bus, [e.id for e in elements])
