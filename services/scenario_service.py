"""ScenarioService: the scenario the Studio edits, kept on disk.

The Studio restarts on every code change, so the scenario is saved after every edit
and read back at start. Placing participants follows the rules of
``config/placement.py``.
"""

from __future__ import annotations

from pathlib import Path

from config import placement, store
from config.scenario import Scenario


# --------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------
class ScenarioService:
    """The current scenario, saved after every change.

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
    # The rules are in ``config/placement.py``; here the result is kept on disk.
    def toggle(self, bus: str) -> str:
        """Add or remove a participant on ``bus``; returns what happened."""
        message = placement.toggle(self.current(), bus)
        self.save()
        return message

    def place_all(self, which: str, battery_kwh: float = 0.0) -> int:
        """Replace the participants (see ``placement.place_all``)."""
        count = placement.place_all(self.current(), which, battery_kwh)
        self.save()
        return count

    def clear(self) -> None:
        """Remove every participant."""
        placement.clear(self.current())
        self.save()
