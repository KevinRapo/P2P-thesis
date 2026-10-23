"""ScenarioService: the scenario the Studio edits, kept on disk.

The Studio restarts on every code change, so the scenario is saved after every edit
and read back at start. Placing participants follows the rules of
``core/config/placement.py``. A scenario file (a notebook's, e.g.
``config/scenarios/validate_market.json``) can be opened in its place.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.config import placement, store
from core.config.scenario import BatterySetup, Scenario


# --------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------
class ScenarioService:
    """The current scenario, saved after every change.

    Args:
        path: Where the scenario is kept (``Workspace.scenario_file``).
        library: The folder of scenario files offered to open
            (``scenarios``).
    """

    def __init__(self, path: Path, library: Path | None = None) -> None:
        self.path = path
        self.library = library
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

    # --- Scenario files --------------------------------------------------------------
    def files(self) -> list[Path]:
        """The scenario files in the library, by name."""
        if self.library is None or not self.library.is_dir():
            return []
        return sorted(self.library.glob("*.json"))

    def peek(self, path: Path) -> Scenario:
        """The scenario in ``path``, without opening it."""
        return store.load(path)

    def parse(self, text: str) -> Scenario:
        """The scenario in a file's text (an uploaded file)."""
        return store.from_dict(json.loads(text))

    def open(self, scenario: Scenario) -> None:
        """Make ``scenario`` the current one and save it; its file is not changed."""
        self._scenario = scenario
        self.save()

    def set_network(self, code: str) -> None:
        """Use another network; participants belong to the old one and are removed."""
        s = self.current()

        if s.grid.code != code:
            s.grid.code = code
            s.participants = []

        self.save()

    # --- Placing participants --------------------------------------------------------
    # The rules are in ``core/config/placement.py``; here the result is kept on disk.
    def toggle(self, bus: str) -> str:
        """Add or remove a participant on ``bus``; returns what happened."""
        message = placement.toggle(self.current(), bus)
        self.save()

        return message

    def kind_counts(self) -> dict[str, int]:
        """How many buses of each kind the network has (``placement.kind_counts``)."""
        return placement.kind_counts(self.current())

    def place_all(
        self,
        kinds: list[str],
        battery_kwh: float = 0.0,
        battery_power_kw: float | None = None,
    ) -> int:
        """Replace the participants (see ``placement.place_all``)."""
        count = placement.place_all(
            self.current(), kinds, battery_kwh, battery_power_kw
        )
        self.save()

        return count

    def battery_presets(self) -> dict[str, BatterySetup]:
        """SimBench-sized batteries by name (``placement.battery_preset``)."""
        return {
            name: placement.battery_preset(name) for name in placement.BATTERY_PRESETS
        }

    def storage_of(self, participant_id: str) -> BatterySetup | None:
        """The SimBench storage a participant took over, as a battery
        (``placement.participant_storage``)."""
        return placement.participant_storage(self.current(), participant_id)

    def set_battery(self, participant_id: str, battery: BatterySetup | None) -> str:
        """Give a participant a battery (``placement.set_battery``; raises
        ``ValueError`` for a change to its SimBench storage)."""
        message = placement.set_battery(self.current(), participant_id, battery)
        self.save()

        return message

    def clear(self) -> None:
        """Remove every participant."""
        placement.clear(self.current())
        self.save()
