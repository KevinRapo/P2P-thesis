"""Reading, writing and hashing experiment files (05-experiment-layer.md §3.1).

The canonical hash identifies "the same study" regardless of formatting or key
order (02 §6): it is computed on sorted-key, compact JSON of the model.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from .records import SCHEMA_VERSION, ExperimentFile

# from_version -> function that upgrades the raw dict by one version
MIGRATIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a raw file dict to ``SCHEMA_VERSION`` step by step."""
    data = dict(data)
    version = str(data.get("schema_version", SCHEMA_VERSION))
    while version != SCHEMA_VERSION:
        if version not in MIGRATIONS:
            raise ValueError(
                f"No migration from schema_version {version!r} to {SCHEMA_VERSION!r}"
            )
        data = MIGRATIONS[version](data)
        version = str(data["schema_version"])
    return data


def parse(text: str) -> ExperimentFile:
    """Parse JSON text into a validated, migrated experiment file."""
    return ExperimentFile.model_validate(migrate(json.loads(text)))


def load(path: str | Path) -> ExperimentFile:
    """Read an experiment file from disk; migrated and validated like ``parse``."""
    return parse(Path(path).read_text(encoding="utf-8"))


def dumps(file: ExperimentFile) -> str:
    """Pretty JSON in the model's field order, for files people read and share."""
    return json.dumps(file.model_dump(mode="json"), indent=2, ensure_ascii=False)


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Write via a temporary file in the same folder, then rename over the target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def save(file: ExperimentFile, path: str | Path) -> Path:
    """Write the file atomically as pretty JSON.

    Returns:
        The path written.
    """
    return atomic_write_text(path, dumps(file) + "\n")


def canonical_json(data: ExperimentFile | dict[str, Any]) -> str:
    """Sorted-key, compact JSON of the file: what ``canonical_hash`` hashes."""
    if isinstance(data, ExperimentFile):
        data = data.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(data: ExperimentFile | dict[str, Any]) -> str:
    """sha256 of the canonical JSON; the same study always has the same hash."""
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def json_schema() -> dict[str, Any]:
    """JSON Schema of the experiment file, for editor autocompletion (02 §6)."""
    return ExperimentFile.model_json_schema()
