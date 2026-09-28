"""Where the services keep user data: library, experiment store and exports.

The workspace lives outside the repository and outside OneDrive, because runs
write many small files while they execute (sync clients lock and duplicate
them). Default: ``%LOCALAPPDATA%\\MARLEM`` on Windows, ``~/.local/share/marlem``
elsewhere. ``MARLEM_HOME`` overrides it.

    <home>/library/   experiment files the user saves (*.marlem.json)
    <home>/store/     run folders (experiment layer store, 05 §3.5)
    <home>/exports/   bundles (experiment file + referenced data files)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PRESETS_DIR = Path(__file__).resolve().parents[1] / "experiments" / "presets"
FILE_SUFFIX = ".marlem.json"


def default_home() -> Path:
    if os.environ.get("MARLEM_HOME"):
        return Path(os.environ["MARLEM_HOME"]).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "MARLEM"
    return Path.home() / ".local" / "share" / "marlem"


@dataclass(frozen=True)
class Workspace:
    home: Path
    presets: Path = PRESETS_DIR

    @classmethod
    def default(cls) -> Workspace:
        return cls(default_home())

    @property
    def library(self) -> Path:
        return self.home / "library"

    @property
    def store(self) -> Path:
        return self.home / "store"

    @property
    def exports(self) -> Path:
        return self.home / "exports"
