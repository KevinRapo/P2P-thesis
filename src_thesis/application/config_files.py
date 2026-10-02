"""The real ConfigService: experiment files on disk (03 §2.1).

Presets are read-only files in the repository (``experiments/presets/``); the
user's files live in the workspace library, outside OneDrive (``workspace.py``).
Every operation on file content is delegated to the experiment layer
(``experiments.models``); this module only decides where files live and how
they are named.
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..experiments.models import expand as expansion
from ..experiments.models import files
from ..experiments.models import resolve as resolution
from ..experiments.models.manifest import data_path, referenced_paths
from .models import ExperimentFile, FieldChange, FileSummary, RunCell
from .workspace import FILE_SUFFIX, Workspace

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class FileConfigService:
    """The real ``ConfigService``: presets from the repository, your files in the
    workspace library.

    Args:
        workspace: Where the library is; default ``Workspace.default()``.
    """

    def __init__(self, workspace: Workspace | None = None) -> None:
        self.workspace = workspace or Workspace.default()

    # ------------------------------------------------------------------ files
    def list(self, kind: str | None = None) -> list[FileSummary]:
        """Presets (kind ``"preset"``) and library files (kind ``"draft"``), filtered by
        ``kind``.
        """
        items = [self._summary(p, "preset") for p in self._files(self.presets_dir)]
        items += [self._summary(p, "draft") for p in self._files(self.library_dir)]
        return [i for i in items if kind is None or i.kind == kind]

    def load(self, file_id: str) -> ExperimentFile:
        """A library file, or else a preset, by ID."""
        for folder in (self.library_dir, self.presets_dir):
            path = folder / f"{file_id}{FILE_SUFFIX}"
            if path.exists():
                return files.load(path)
        raise FileNotFoundError(f"No experiment file or preset {file_id!r}")

    def new_from_preset(self, preset_id: str) -> ExperimentFile:
        """A new library file copied from a preset, with a free ``<preset>-draft`` ID."""
        preset = files.load(self._preset_path(preset_id))
        file = preset.model_copy(deep=True)
        file.meta.id = self._free_id(f"{preset_id}-draft")
        file.meta.derived_from = f"preset:{preset_id}"
        file.meta.tags = [t for t in file.meta.tags if t != "preset"] + ["draft"]
        self.save(file)
        return file

    def save(self, file: ExperimentFile, path: Path | None = None) -> str:
        """Write to the library (or ``path``); presets can never be overwritten."""
        file_id = self._check_id(file.meta.id)
        if (self.presets_dir / f"{file_id}{FILE_SUFFIX}").exists():
            raise ValueError(f"{file_id!r} is a preset ID; save under another ID")
        target = path or self.library_dir / f"{file_id}{FILE_SUFFIX}"
        return str(files.save(file, target))

    def clone(self, file_id: str, new_id: str) -> ExperimentFile:
        """Save a copy of ``file_id`` under ``new_id`` with ``meta.derived_from =
        file_id``.

        Raises:
            FileExistsError: A library file or preset already has ``new_id``.
            ValueError: ``new_id`` is not usable as a file name.
        """
        new_id = self._check_id(new_id)
        if self._exists(new_id):
            raise FileExistsError(f"An experiment file {new_id!r} already exists")
        file = self.load(file_id).model_copy(deep=True)
        file.meta.id, file.meta.derived_from = new_id, file_id
        self.save(file)
        return file

    def delete(self, file_id: str) -> None:
        """Delete a library file; presets cannot be deleted."""
        path = self.library_dir / f"{self._check_id(file_id)}{FILE_SUFFIX}"
        if not path.exists():
            raise FileNotFoundError(f"No library file {file_id!r}")
        path.unlink()

    # ------------------------------------------------------------------ content
    def update(self, file: ExperimentFile, changes: dict[str, Any]) -> ExperimentFile:
        """A validated copy with each dotted path set (``market.mechanism``)."""
        return expansion.apply_overrides(file, changes)

    def origin(self, file: ExperimentFile) -> ExperimentFile | None:
        """The preset or file this one was derived from, if it still exists."""
        source = file.meta.derived_from
        if not source:
            return None
        try:
            return self.load(source.removeprefix("preset:"))
        except (FileNotFoundError, ValueError):
            return None

    def resolve(self, file: ExperimentFile) -> ExperimentFile:
        """Every unset field filled from the defaults
        (``experiments.models.resolve.resolve``).
        """
        return resolution.resolve(file)

    def expand(self, file: ExperimentFile) -> list[RunCell]:
        """The runs the file asks for (``experiments.models.expand.expand``)."""
        return expansion.expand(file)

    def hash(self, file: ExperimentFile) -> str:
        """Canonical sha256 of the file (``files.canonical_hash``)."""
        return files.canonical_hash(file)

    def to_json(self, file: ExperimentFile) -> str:
        """The file as saved: pretty JSON in field order."""
        return files.dumps(file)

    def diff(self, a: ExperimentFile, b: ExperimentFile) -> list[FieldChange]:
        """Changed leaves as dotted paths, e.g. ``participants[2].bus``."""
        changes: list[FieldChange] = []
        _diff(a.model_dump(mode="json"), b.model_dump(mode="json"), "", changes)
        return changes

    def export_bundle(self, file: ExperimentFile) -> str:
        """Zip the file with the external data files it names that exist (02 §6)."""
        file_id = self._check_id(file.meta.id)
        target = self.workspace.exports / f"{file_id}.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(f"{file_id}{FILE_SUFFIX}", files.dumps(file) + "\n")
            for path in referenced_paths(file.model_dump(mode="json")):
                source = data_path(path)
                if source.is_file():
                    bundle.write(source, f"data/{Path(path).as_posix().lstrip('/')}")
        return str(target)

    # ------------------------------------------------------------------ helpers
    @property
    def presets_dir(self) -> Path:
        """Folder of the read-only presets."""
        return self.workspace.presets

    @property
    def library_dir(self) -> Path:
        """Folder of your experiment files."""
        return self.workspace.library

    @staticmethod
    def _files(folder: Path) -> list[Path]:
        return sorted(folder.glob(f"*{FILE_SUFFIX}")) if folder.exists() else []

    def _summary(self, path: Path, kind: str) -> FileSummary:
        file = files.load(path)
        return FileSummary(
            id=file.meta.id,
            name=file.meta.name,
            kind=kind,
            path=str(path),
            modified=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
            tags=file.meta.tags,
            network=str(file.grid.get("source", {}).get("code", "")),
            participants=len(file.participants),
        )

    def _preset_path(self, preset_id: str) -> Path:
        path = self.presets_dir / f"{preset_id}{FILE_SUFFIX}"
        if not path.exists():
            raise FileNotFoundError(f"No preset {preset_id!r}")
        return path

    def _exists(self, file_id: str) -> bool:
        return any(
            (folder / f"{file_id}{FILE_SUFFIX}").exists()
            for folder in (self.library_dir, self.presets_dir)
        )

    def _free_id(self, base: str) -> str:
        candidate, n = base, 2
        while self._exists(candidate):
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    @staticmethod
    def _check_id(file_id: str) -> str:
        """IDs become file names and run-ID prefixes, so keep them path-safe."""
        if not SAFE_ID.match(file_id) or "__" in file_id:
            raise ValueError(
                f"Invalid experiment ID {file_id!r}: use letters, digits, '.', '-' "
                "and '_' (no '__', which separates the parts of a run ID)"
            )
        return file_id


def _diff(a: Any, b: Any, path: str, out: list[FieldChange]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in list(a) + [k for k in b if k not in a]:
            sub = f"{path}.{key}" if path else str(key)
            _diff(a.get(key), b.get(key), sub, out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(FieldChange(path=path, before=a, after=b))
