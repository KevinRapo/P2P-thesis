"""Where the services keep user data: library, experiment store and exports.

The workspace lives outside the repository and outside OneDrive, because runs
write many small files while they execute (sync clients lock and duplicate
them). Its folder is, in this order:

1. ``MARLEM_HOME``, if set (scripts, tests);
2. the folder chosen in the Studio's Settings page, kept in a small settings
   file (``settings_path()``: ``%APPDATA%\\MARLEM\\settings.json`` on Windows,
   ``~/.config/marlem/settings.json`` elsewhere);
3. ``%LOCALAPPDATA%\\MARLEM`` on Windows, ``~/.local/share/marlem`` elsewhere.

    <home>/library/   experiment files the user saves (*.marlem.json)
    <home>/store/     run folders (experiment layer store, 05 §3.5)
    <home>/exports/   bundles (experiment file + referenced data files)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PRESETS_DIR = Path(__file__).resolve().parents[1] / "experiments" / "presets"
FILE_SUFFIX = ".marlem.json"


def settings_path() -> Path:
    """The per-user settings file; it lives outside the workspace it points to."""
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "MARLEM" / "settings.json"
    return Path.home() / ".config" / "marlem" / "settings.json"


def built_in_home() -> Path:
    """The workspace folder when nothing is chosen: ``MARLEM`` in ``%LOCALAPPDATA%`` on
    Windows.
    """
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "MARLEM"
    return Path.home() / ".local" / "share" / "marlem"


def _saved_home() -> Path | None:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    home = data.get("home") if isinstance(data, dict) else None
    return Path(home).expanduser() if home else None


def home_source() -> str:
    """Which rule chose the workspace: "environment", "settings" or "default"."""
    if os.environ.get("MARLEM_HOME"):
        return "environment"
    return "settings" if _saved_home() else "default"


def default_home() -> Path:
    """The workspace folder in use: ``MARLEM_HOME``, else the Settings choice, else the
    built-in default.
    """
    if os.environ.get("MARLEM_HOME"):
        return Path(os.environ["MARLEM_HOME"]).expanduser()
    return _saved_home() or built_in_home()


def set_home(home: str | Path | None) -> Path:
    """Remember ``home`` as the workspace folder (``None`` = back to the default).

    The folder is created and must be writable. Existing files are not moved.
    """
    target = settings_path()
    if home is None or str(home).strip() == "":
        target.unlink(missing_ok=True)
        return built_in_home()
    path = Path(str(home).strip()).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".marlem-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
    finally:
        probe.unlink(missing_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"home": str(path)}, indent=2), encoding="utf-8")
    return path


def is_synced_folder(path: Path) -> bool:
    """True inside OneDrive (or a folder it syncs), where runs should not live."""
    resolved = Path(path).expanduser().resolve()
    roots = [os.environ.get(k) for k in ("OneDrive", "OneDriveConsumer")]
    for root in filter(None, roots):
        if resolved.is_relative_to(Path(root).resolve()):
            return True
    return any(
        part.lower() == "onedrive" or part.lower().startswith("onedrive - ")
        for part in resolved.parts
    )


@dataclass(frozen=True)
class Workspace:
    """The workspace folder and its subfolders.

    Attributes:
        home: The workspace folder.
        presets: Folder of the read-only presets (in the repository).
    """

    home: Path
    presets: Path = PRESETS_DIR

    @classmethod
    def default(cls) -> Workspace:
        """The workspace in use (``default_home()``)."""
        return cls(default_home())

    @property
    def library(self) -> Path:
        """``<home>/library``: your experiment files."""
        return self.home / "library"

    @property
    def store(self) -> Path:
        """``<home>/store``: run folders."""
        return self.home / "store"

    @property
    def exports(self) -> Path:
        """``<home>/exports``: bundles."""
        return self.home / "exports"
