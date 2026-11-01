"""Where the Studio keeps its data: the network cache and per-browser state.

The workspace lives outside the repository and outside OneDrive, because sync
clients lock and duplicate large and frequently written files. Its folder is, in
this order:

1. the setting ``MARLEM_HOME``, if set (the environment or ``.env``, see
   ``core/settings.py``; scripts, tests);
2. the folder chosen in the Studio's Settings page, kept in a small settings
   file (``settings_path()``: ``%APPDATA%\\MARLEM\\settings.json`` on Windows,
   ``~/.config/marlem/settings.json`` elsewhere);
3. ``%LOCALAPPDATA%\\MARLEM`` on Windows, ``~/.local/share/marlem`` elsewhere.

    <home>/cache/networks/   built networks, so they open at once
    <home>/scenarios/        the scenario the Studio edits (current.json)
    <home>/studio-state/     the Studio's per-browser state
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from core import settings as machine


# --------------------------------------------------------------------------------------
# Where the workspace is
# --------------------------------------------------------------------------------------
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
    if machine.get("MARLEM_HOME"):
        return "environment"
    return "settings" if _saved_home() else "default"


def default_home() -> Path:
    """The workspace folder in use: ``MARLEM_HOME``, else the Settings choice, else the
    built-in default.
    """
    home = machine.get("MARLEM_HOME")

    if home:
        return Path(home).expanduser()

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


# --------------------------------------------------------------------------------------
# The system's folder dialog
# --------------------------------------------------------------------------------------
# Tk belongs on a main thread and dies with its process, so each dialog is a small
# Python process of its own. It stays on top: the browser would otherwise cover it.
_FOLDER_DIALOG = """
import sys
from tkinter import Tk, filedialog

root = Tk()
root.withdraw()
root.attributes("-topmost", True)
print(filedialog.askdirectory(parent=root, initialdir=sys.argv[1], title=sys.argv[2]))
"""


def nearest_folder(path: str | Path) -> Path:
    """``path``, or the closest parent of it that exists, else the user's home."""
    start = Path(str(path).strip() or Path.home()).expanduser().resolve()

    for folder in (start, *start.parents):
        if folder.is_dir():
            return folder

    return Path.home()


def choose_folder(start: str | Path, title: str = "Choose a folder") -> Path | None:
    """Ask for a folder in the system's dialog, on the computer the Studio runs on.

    Waits until the dialog is closed, so call it in a thread.

    Args:
        start: The folder the dialog opens in (or the closest one that exists).
        title: The dialog's title.

    Returns:
        The folder, or ``None`` if the dialog was cancelled.

    Raises:
        OSError: The dialog could not be shown.
    """
    done = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            _FOLDER_DIALOG,
            str(nearest_folder(start)),
            title,
        ],
        capture_output=True,
        encoding="utf-8",
    )

    if done.returncode != 0:
        raise OSError(done.stderr.strip().splitlines()[-1])

    chosen = done.stdout.strip()

    return Path(chosen) if chosen else None


# --------------------------------------------------------------------------------------
# The workspace and its folders
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Workspace:
    """The workspace folder and its subfolders.

    Attributes:
        home: The workspace folder.
    """

    home: Path

    @classmethod
    def default(cls) -> Workspace:
        """The workspace in use (``default_home()``)."""
        return cls(default_home())

    @property
    def network_cache(self) -> Path:
        """``<home>/cache/networks``: built networks, so they open at once."""
        return self.home / "cache" / "networks"

    @property
    def experiment_file(self) -> Path:
        """``<home>/experiments/selected.json``: the experiment the Studio prepares."""
        return self.home / "experiments" / "selected.json"

    @property
    def scenario_file(self) -> Path:
        """``<home>/scenarios/current.json``: the scenario the Studio edits."""
        return self.home / "scenarios" / "current.json"
