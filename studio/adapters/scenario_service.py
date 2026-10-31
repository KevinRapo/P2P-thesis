"""ScenarioService: the active scenario, the one the Studio edits and plays.

The Studio restarts on every code change, so the scenario is saved after every edit
and read back at start. Placing participants follows the rules of
``core/config/placement.py``. A scenario file (a notebook's, e.g.
``config/scenarios/validate_market.json``) can be opened in its place. The active
scenario then remembers the file (``origin``), and is unsaved once it differs from it
or if it never had one; a changed one is shown as ``<name>-mod`` (``shown_name``).
Nothing depends on that: an unsaved scenario can be played and started like any other.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Optional

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
        self._origin_file = path.with_name("origin.json")
        self._origin: dict | None = None

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

    def open(
        self,
        scenario: Scenario,
        source: Optional[str] = None,
        path: Optional[Path] = None,
    ) -> None:
        """Make ``scenario`` the active one and save it; its file is not changed.

        Args:
            scenario: The scenario.
            source: The name of the file it came from (None: no file).
            path: That file, if it is one in the library that a save may replace.
        """
        self._scenario = scenario
        self._origin = {
            "file": source,
            "path": str(path) if path else None,
            "contents": asdict(scenario),
        }
        self._origin_file.parent.mkdir(parents=True, exist_ok=True)
        self._origin_file.write_text(json.dumps(self._origin), encoding="utf-8")
        self.save()

    def origin(self) -> dict:
        """Where the active scenario came from: ``file``, ``path`` and ``contents``
        (None: it has no file)."""
        if self._origin is None:
            try:
                self._origin = json.loads(self._origin_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._origin = {"file": None, "path": None, "contents": None}

        return self._origin

    def unsaved(self) -> bool:
        """Whether the active scenario has no file, or differs from the one it came
        from."""
        origin = self.origin()
        return origin["file"] is None or origin["contents"] != asdict(self.current())

    def shown_name(self) -> str:
        """The active scenario's name, with ``-mod`` once it differs from its file."""
        name = self.current().name
        return f"{name}-mod" if self.unsaved() and self.origin()["file"] else name

    def played(self) -> Scenario:
        """The active scenario under its shown name: what an experiment plays, so its
        record tells a changed scenario from its file."""
        return replace(self.current(), name=self.shown_name())

    def save_as(self, name: str) -> Path:
        """Write the active scenario to the library as ``<name>.json``, for an
        experiment to name; it is then that file's. ``ValueError`` if the name is no
        plain word, or another file has it: only its own file can be replaced."""
        if self.library is None or not name or any(c in name for c in '/\\:*?"<>| '):
            raise ValueError(f"{name!r} is not a plain file name")

        path = self.library / f"{name}.json"

        if path.exists() and str(path) != self.origin()["path"]:
            raise ValueError(f"{path.name} exists already")

        self.current().name = name
        store.save(self.current(), path)
        self.open(self.current(), path.name, path)

        return path

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
