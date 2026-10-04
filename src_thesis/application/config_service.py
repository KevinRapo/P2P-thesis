"""ConfigService: experiment files (04 §5).

Final implementation: ``FileConfigService`` (presets from the repository, the
user's files in the workspace library). Demo: ``DemoConfigService`` (files kept
in memory, presets built in code). The sample data below is shared with the other
demo services.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from src_thesis.experiments.models import expand as expansion
from src_thesis.experiments.models import files
from src_thesis.experiments.models import resolve as resolution
from src_thesis.experiments.models.manifest import data_path, referenced_paths
from src_thesis.application.workspace import FILE_SUFFIX, Workspace
from src_thesis.application.models import (
    ExperimentFile,
    ExperimentMeta,
    FieldChange,
    FileSummary,
    RunCell,
)


# ---------------------------------------------------------------------- protocol
class ConfigService(Protocol):
    """Experiment files: presets, the user's library, editing, comparing, sharing.

    Nothing here runs a simulation. Real implementation: ``FileConfigService``.
    """

    def list(self, kind: str | None = None) -> list[FileSummary]:
        """Presets and library files, for the Home and Library pages.

        Args:
            kind: ``"preset"`` or ``"draft"`` to list only one kind; ``None`` for all.
        """
        ...

    def load(self, file_id: str) -> ExperimentFile:
        """Read a library file or preset by ID.

        Raises:
            FileNotFoundError: Neither a library file nor a preset has this ID.
        """
        ...

    def new_from_preset(self, preset_id: str) -> ExperimentFile:
        """Copy a preset into the library as a new draft and return it.

        The draft gets a free ID (``<preset>-draft``, ``-draft-2``, …) and records
        the preset in ``meta.derived_from``.
        """
        ...

    def save(self, file: ExperimentFile, path: Path | None = None) -> str:
        """Write the file (to the library unless ``path`` is given).

        Returns:
            The path written.

        Raises:
            ValueError: The ID is a preset's or is not usable as a file name.
        """
        ...

    def clone(self, file_id: str, new_id: str) -> ExperimentFile:
        """Save a copy of ``file_id`` under ``new_id``, recording where it came from.

        Raises:
            FileExistsError: A file with ``new_id`` already exists.
        """
        ...

    def delete(self, file_id: str) -> None:
        """Delete a library file. Presets cannot be deleted."""
        ...

    def update(self, file: ExperimentFile, changes: dict[str, Any]) -> ExperimentFile:
        """A validated copy of ``file`` with each dotted path set; nothing is saved.

        Args:
            file: The file to change; it is not modified.
            changes: Dotted path → new value, e.g. ``{"market.mechanism": "seller"}``.

        Raises:
            ValueError: The result is not a valid experiment file.
        """
        ...

    def origin(self, file: ExperimentFile) -> ExperimentFile | None:
        """The preset or file named in ``meta.derived_from``; ``None`` if gone."""
        ...

    def resolve(self, file: ExperimentFile) -> ExperimentFile:
        """The file with every unset field filled from the defaults (02 §3)."""
        ...

    def expand(self, file: ExperimentFile) -> list[RunCell]:
        """The runs the file asks for.

        Sweep points × paradigms × algorithms × seeds, plus the baselines.
        """
        ...

    def hash(self, file: ExperimentFile) -> str:
        """Canonical sha256: equal for files that describe the same study (02 §6)."""
        ...

    def diff(self, a: ExperimentFile, b: ExperimentFile) -> list[FieldChange]:
        """Every field that differs between ``a`` and ``b``, as dotted paths."""
        ...

    def export_bundle(self, file: ExperimentFile) -> str:
        """Zip the file with the data files it references.

        Returns:
            The path of the zip.
        """
        ...

    def to_json(self, file: ExperimentFile) -> str:
        """The file as the pretty JSON that is saved and shared."""
        ...


# ---------------------------------------------------------------------- final implementation
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


# ---------------------------------------------------------------------- demo implementation and shared sample data
PARADIGMS = ["ctce", "ctde", "dtde"]


ALGORITHMS = ["ppo", "appo", "sac"]


_NOW = datetime(2026, 9, 23, 12, 0)


def _default_learning() -> dict:
    """Original MARLEM defaults, see 02-experiment-config.md §3.8."""
    return {
        "paradigms": list(PARADIGMS),
        "algorithms": list(ALGORITHMS),
        "seeds": [1, 2, 3],
        "budget": {"unit": "env_steps", "value": 2_000_000},
        "paradigm_options": {
            "ctce": {"reward_aggregation": "sum"},
            "ctde": {"reward_aggregation": "sum"},
            "dtde": {"policy_sharing": "independent"},
        },
        "model": {"embeddings_dim": 128, "activation": "relu"},
        "algorithm_params": {
            "ppo": {
                "lr": 1e-5,
                "gamma": 0.99,
                "lambda_": 0.95,
                "num_epochs": 30,
                "minibatch_size": 128,
                "clip_param": 0.2,
                "entropy_coeff": 0.01,
                "kl_coeff": 0.0,
                "grad_clip": 0.5,
            },
            "appo": {
                "lr": 1e-5,
                "gamma": 0.99,
                "lambda_": 0.95,
                "vtrace": True,
                "entropy_coeff": 0.01,
                "kl_coeff": 0.0,
                "grad_clip": 0.5,
            },
            "sac": {
                "actor_lr": 1e-5,
                "critic_lr": 1e-5,
                "gamma": 0.99,
                "twin_q": True,
                "target_entropy": "auto",
                "replay_buffer": {"capacity": 1000},
                "grad_clip": 0.5,
            },
        },
        "tuning": {"method": "none", "num_samples": 1},
        "checkpoint": {"every": 10, "keep": 3},
    }


def _participants(n: int = 8) -> list[dict]:
    roles = [
        ("small_industry", "G1-A", "PV3", 180),
        ("community_hospital", "G3-A", "PV2", 170),
        ("university_campus", "G2-A", "PV4", 140),
        ("shopping_mall", "G4-A", "PV1", 130),
        ("residential_complex", "H0-B", "PV5", 80),
        ("apartment_building", "H0-A", "PV6", 75),
        ("community_solar_farm", "H0-C", "PV8", 180),
        ("parking_lot", "G6-A", "PV7", 160),
    ]
    out = []
    for i, (role, demand, gen, peak) in enumerate(roles[:n]):
        out.append(
            {
                "id": role,
                "role": role,
                "bus": f"LV4.101 Bus {10 + 3 * i}",
                "owns": {"loads": [f"LV4.101 Load {5 + 2 * i}"], "sgens": []},
                "profile": {
                    "source": "catalog",
                    "demand": {"type": demand},
                    "generation": {"type": gen},
                },
                "scaling": {"mode": "peak_kw", "demand": peak, "generation": peak},
                "battery": (
                    {
                        "nominal_capacity_kwh": round(peak * 0.6, 1),
                        "min_soc": 0.1,
                        "max_soc": 0.9,
                        "charge_efficiency": 0.95,
                        "discharge_efficiency": 0.95,
                    }
                    if i % 3 != 2
                    else None
                ),
            }
        )
    return out


_PRESETS = {
    "case1-mechanisms": ("Case 1: market mechanisms", "sweep: market.mechanism (6)"),
    "case2-heterogeneity": ("Case 2: agent heterogeneity", "sweep: participant sizes"),
    "case3-dso-strategies": ("Case 3: DSO strategies", "sweep: DSO fees and tariffs"),
    "case4-grid-constraints": (
        "Case 4: grid constraints",
        "sweep: feeder, SimBench scenario, background",
    ),
    "case5-battery": (
        "Case 5: battery coordination",
        "sweep: batteries none vs strategic",
    ),
    "case6-3x3": (
        "Case 6: implicit cooperation (3 × 3)",
        "paradigms × algorithms × seeds",
    ),
    "case7-scalability": ("Case 7: scalability", "sweep: number of agents"),
}


def _preset_file(preset_id: str) -> ExperimentFile:
    name, description = _PRESETS[preset_id]
    return ExperimentFile(
        meta=ExperimentMeta(
            id=preset_id,
            name=name,
            description=description,
            tags=["preset", "paper"],
            derived_from=f"preset:{preset_id}",
            data_status=(
                "reconstructed-unverified" if preset_id == "case6-3x3" else "synthetic"
            ),
        ),
        time={
            "resolution": "hourly_aggregated",
            "horizon_steps": 24,
            "days": {
                "mode": "sampler",
                "start": "2016-05-01",
                "end": "2016-08-31",
                "filter": {"day_type": "workday"},
                "eval_holdout": 0.2,
                "seed": 42,
            },
        },
        grid={
            "source": {"type": "simbench", "code": "1-LV-semiurb4--0-sw"},
            "background": {"mode": "mapped_replacement"},
            "limits": {
                "v_min_pu": 0.95,
                "v_max_pu": 1.05,
                "line_max_percent": 100,
                "trafo_max_percent": 100,
            },
            "ratings": {"source": "network"},
            "assessment": {"mode": "feedback", "non_convergence": "truncate_episode"},
        },
        participants=_participants(),
        market={
            "mechanism": "average",
            "price": {"min": 20, "max": 600},
            "quantity": {"min": 0, "max": 180},
            "partner_preference": False,
            "ledger": {"enabled": True, "difficulty": 0},
            "async_orders": True,
        },
        dso={
            "tariffs": {"source": "csv", "mode": "normalized"},
            "fees": {
                "charged": True,
                "congestion_factor": 0.5,
                "congestion_threshold": 0.8,
                "distance_factor": 0.35,
                "voltage_factor": 0.15,
                "voltage_threshold": 0.05,
                "instability_threshold": 0.2,
                "imbalance_factor": 0.15,
                "zone_factor": 0.15,
            },
        },
        environment={
            "observation": {
                "version": "v2-grid",
                "forecast_error": 0.3,
                "own_bus_voltage": "private",
            },
            "reward": {
                "version": "corrected-v1",
                "log_scale": 20,
                "grid_violation": {"attribution": "bus"},
            },
            "reputation": {
                "weights": {"reliability": 0.3, "fairness": 0.2, "grid": 0.5}
            },
        },
        learning=_default_learning(),
        evaluation={
            "interval": 10,
            "episodes": 20,
            "days": "holdout",
            "explore": False,
        },
        baselines=["no_order", "random"],
        sweep=(
            {
                "mode": "grid",
                "parameters": {
                    "market.mechanism": [
                        "average",
                        "buyer",
                        "seller",
                        "bid_ask_spread",
                        "nash_bargaining",
                        "proportional_surplus",
                    ]
                },
            }
            if preset_id == "case1-mechanisms"
            else {}
        ),
        resources={"cpus_per_run": 6, "gpus_per_learner": 0, "max_parallel_runs": 1},
        outputs={"record_steps": "evaluation", "grid_element_results": False},
    )


class DemoConfigService:
    """Demo ``ConfigService``: experiment files kept in memory; presets built in code.
    Shown as DEMO DATA in the Studio.
    """

    def __init__(self) -> None:
        self._drafts: dict[str, ExperimentFile] = {}

    def list(self, kind: str | None = None) -> list[FileSummary]:
        """Sample-data version of ``ConfigService.list``."""
        items = [
            FileSummary(
                id=pid,
                name=name,
                kind="preset",
                path=f"experiments/presets/{pid}.marlem.json",
                modified=_NOW - timedelta(days=i),
                tags=["paper"],
                network="1-LV-semiurb4--0-sw",
                participants=8,
            )
            for i, (pid, (name, _)) in enumerate(_PRESETS.items())
        ]
        items += [
            FileSummary(
                id=d.meta.id,
                name=d.meta.name,
                kind="draft",
                path=f"experiments/user/{d.meta.id}.marlem.json",
                modified=_NOW,
                network=d.grid.get("source", {}).get("code", ""),
                participants=len(d.participants),
            )
            for d in self._drafts.values()
        ]
        return [i for i in items if kind is None or i.kind == kind]

    def load(self, file_id: str) -> ExperimentFile:
        """Sample-data version of ``ConfigService.load``."""
        return self._drafts.get(file_id) or _preset_file(
            file_id if file_id in _PRESETS else "case6-3x3"
        )

    def new_from_preset(self, preset_id: str) -> ExperimentFile:
        """Sample-data version of ``ConfigService.new_from_preset``."""
        file = _preset_file(preset_id)
        file.meta.id = f"{preset_id}-draft"
        file.meta.tags = ["draft"]
        self._drafts[file.meta.id] = file
        return file

    def save(self, file: ExperimentFile, path: Path | None = None) -> str:
        """Sample-data version of ``ConfigService.save``."""
        self._drafts[file.meta.id] = file
        return str(path or f"experiments/user/{file.meta.id}.marlem.json")

    def clone(self, file_id: str, new_id: str) -> ExperimentFile:
        """Sample-data version of ``ConfigService.clone``."""
        file = self.load(file_id).model_copy(deep=True)
        file.meta.id, file.meta.derived_from = new_id, file_id
        self._drafts[new_id] = file
        return file

    def delete(self, file_id: str) -> None:
        """Sample-data version of ``ConfigService.delete``."""
        self._drafts.pop(file_id, None)

    def update(self, file: ExperimentFile, changes: dict) -> ExperimentFile:
        """Sample-data version of ``ConfigService.update``."""
        data = file.model_dump(mode="json")
        for path, value in changes.items():
            node = data
            *parents, leaf = path.split(".")
            for key in parents:
                node = node.setdefault(key, {})
            node[leaf] = value
        return ExperimentFile.model_validate(data)

    def origin(self, file: ExperimentFile) -> ExperimentFile | None:
        """Sample-data version of ``ConfigService.origin``."""
        source = (file.meta.derived_from or "").removeprefix("preset:")
        return _preset_file(source) if source in _PRESETS else None

    def resolve(self, file: ExperimentFile) -> ExperimentFile:
        """Sample-data version of ``ConfigService.resolve``."""
        return file

    def expand(self, file: ExperimentFile) -> list[RunCell]:
        """Sample-data version of ``ConfigService.expand``."""
        learning = file.learning or _default_learning()
        points = 1
        for values in file.sweep.get("parameters", {}).values():
            points *= len(values)
        return [
            RunCell(
                sweep_label=f"p{p}" if points > 1 else "",
                algorithm=a,
                paradigm=m,
                seed=s,
            )
            for p in range(points)
            for m in learning["paradigms"]
            for a in learning["algorithms"]
            for s in learning["seeds"]
        ]

    def hash(self, file: ExperimentFile) -> str:
        """Sample-data version of ``ConfigService.hash``."""
        return hashlib.sha256(self.to_json(file).encode()).hexdigest()

    def diff(self, a: ExperimentFile, b: ExperimentFile) -> list[FieldChange]:
        """Sample-data version of ``ConfigService.diff``."""
        da, db = a.model_dump(), b.model_dump()
        return [
            FieldChange(path=k, before=da[k], after=db[k]) for k in da if da[k] != db[k]
        ]

    def export_bundle(self, file: ExperimentFile) -> str:
        """Sample-data version of ``ConfigService.export_bundle``."""
        return f"exports/{file.meta.id}.zip"

    def to_json(self, file: ExperimentFile) -> str:
        """Sample-data version of ``ConfigService.to_json``."""
        return json.dumps(
            file.model_dump(mode="json"), indent=2, sort_keys=False, ensure_ascii=False
        )
