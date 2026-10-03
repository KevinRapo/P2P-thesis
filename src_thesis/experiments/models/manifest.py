"""The run manifest: what exactly a run used (05-experiment-layer.md §3.4, 02 §5).

Fingerprints are collected without importing heavy packages: versions come
from package metadata, the code state from git.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from src_thesis.experiments.models.files import canonical_hash
from src_thesis.experiments.models.records import ExperimentFile, Manifest, RunCell
from src_thesis.experiments.models.resolve import resolve_days

REPO = Path(__file__).resolve().parents[3]
PACKAGES = ("ray", "torch", "pandapower", "simbench", "pydantic", "numpy", "gymnasium")


def build_manifest(
    file: ExperimentFile,
    resolved: ExperimentFile,
    cell: RunCell,
    run_id: str,
    validation_hash: str | None = None,
) -> Manifest:
    """Everything a run was built from; written once, with the run folder.

    Args:
        file: The experiment file as written.
        resolved: This run's fully resolved file (``resolve_run``).
        cell: The run's cell.
        run_id: The run's ID.
        validation_hash: Hash of the validation report the file passed, if any.
    """
    split = resolve_days(resolved.time)
    return Manifest(
        run_id=run_id,
        experiment_id=file.meta.id,
        cell=cell,
        file_hash=canonical_hash(file),
        resolved_hash=canonical_hash(resolved),
        code=code_fingerprint(),
        environment=environment_fingerprint(),
        data=data_fingerprint(resolved),
        days={"train": list(split.train), "eval": list(split.eval)},
        time_alignment=str(resolved.time.get("resolution", "")),
        validation_hash=validation_hash,
        platform={
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
    )


def code_fingerprint(repo: Path = REPO) -> dict[str, str | bool | None]:
    """Git commit and a hash of the uncommitted diff (None outside a repository)."""

    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", *args], cwd=repo, capture_output=True, text=True, check=True
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return done.stdout

    commit = git("rev-parse", "HEAD")
    diff = git("diff", "HEAD") or ""
    return {
        "commit": commit.strip() if commit else None,
        "dirty": bool(diff),
        "diff_sha256": (
            hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff else None
        ),
    }


def environment_fingerprint() -> dict[str, object]:
    """Python and package versions (ray, torch, pandapower, …), read from metadata
    without importing the packages.
    """
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {"python": sys.version.split()[0], "packages": versions}


def data_fingerprint(resolved: ExperimentFile) -> dict[str, object]:
    """Network source and the sha256 of every external file the world names."""
    files = {}
    for path in referenced_paths(resolved.model_dump(mode="json")):
        p = data_path(path)
        files[path] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return {"network": resolved.grid.get("source", {}), "files": files}


def data_path(path: str) -> Path:
    """A ``path`` from an experiment file; relative paths are repository-relative."""
    return Path(path) if Path(path).is_absolute() else REPO / path


def referenced_paths(node: object) -> list[str]:
    """Every ``path`` value in a file section (CSVs, pandapower files), sorted."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "path" and isinstance(value, str):
                found.append(value)
            else:
                found += referenced_paths(value)
    elif isinstance(node, list):
        for value in node:
            found += referenced_paths(value)
    return sorted(set(found))
