"""The filesystem experiment store.

Why: runs outlive the process that started them, so their state has to live somewhere
durable. Plain folders were chosen over a database: you can open, copy, zip and share a
run folder, a crashed worker leaves readable files, and nothing needs to be installed.
Everyone (services, worker, pool) goes through this one class, so the folder layout is
defined in exactly one place.

One folder per run. Small state files are replaced atomically; logs, metrics
and step records are append-only. The store is the source of truth: the index
is a cache that can always be rebuilt by scanning the run folders.

    <root>/
    ├── index.json
    └── runs/<run_id>/
        ├── experiment.json  resolved.json  manifest.json
        ├── status.json  artifacts.json  cancel.request?
        ├── logs/worker.log
        ├── metrics/training.csv  metrics/evaluation.jsonl
        ├── raw/steps.jsonl
        ├── checkpoints/
        └── figures/
"""

from __future__ import annotations

import csv
import json
from collections import deque
from pathlib import Path
from typing import Any, Iterator

from src_thesis.platform.experiments.models.files import atomic_write_text, dumps, load
from src_thesis.platform.experiments.models.records import (
    ArtifactIndex,
    ExperimentFile,
    Manifest,
    RunState,
    StatusRecord,
    can_transition,
    utc_now,
)

SUBFOLDERS = ("logs", "metrics", "raw", "checkpoints", "figures")


class RunExistsError(FileExistsError):
    """A run folder with this run ID already exists."""

    pass


class IllegalTransitionError(ValueError):
    """A state change the run lifecycle does not allow (03 §5)."""

    pass


class ExperimentStore:
    """Run folders on disk: the single source of truth about runs (03 §6).

    Args:
        root: The store folder (``<workspace>/store``); runs live in
            ``root/runs/<run_id>/``.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.runs_dir = self.root / "runs"

    # ------------------------------------------------------------------ runs
    def run_dir(self, run_id: str) -> Path:
        """Folder of one run (it may not exist yet)."""
        return self.runs_dir / run_id

    def create_run(
        self,
        file: ExperimentFile,
        resolved: ExperimentFile,
        manifest: Manifest,
    ) -> Path:
        """Write a new run folder in state READY. Fails if the run already exists."""
        folder = self.run_dir(manifest.run_id)
        if folder.exists():
            raise RunExistsError(f"run {manifest.run_id} already exists")
        for name in SUBFOLDERS:
            (folder / name).mkdir(parents=True, exist_ok=True)
        atomic_write_text(folder / "experiment.json", dumps(file) + "\n")
        atomic_write_text(folder / "resolved.json", dumps(resolved) + "\n")
        self._write_model(folder / "manifest.json", manifest)
        self._write_model(
            folder / "status.json",
            StatusRecord(run_id=manifest.run_id, experiment_id=manifest.experiment_id),
        )
        self._write_model(folder / "artifacts.json", ArtifactIndex())
        return folder

    def exists(self, run_id: str) -> bool:
        """True once the run folder has its manifest."""
        return (self.run_dir(run_id) / "manifest.json").exists()

    def read_file(self, run_id: str) -> ExperimentFile:
        """The experiment file as written (``experiment.json``)."""
        return load(self.run_dir(run_id) / "experiment.json")

    def read_resolved(self, run_id: str) -> ExperimentFile:
        """The run's fully resolved file (``resolved.json``)."""
        return load(self.run_dir(run_id) / "resolved.json")

    def read_manifest(self, run_id: str) -> Manifest:
        """The run's manifest (``manifest.json``)."""
        return Manifest.model_validate_json(
            (self.run_dir(run_id) / "manifest.json").read_text(encoding="utf-8")
        )

    # ------------------------------------------------------------------ status
    def read_status(self, run_id: str) -> StatusRecord:
        """The run's live status (``status.json``)."""
        return StatusRecord.model_validate_json(
            (self.run_dir(run_id) / "status.json").read_text(encoding="utf-8")
        )

    def set_state(self, run_id: str, state: RunState, **fields: Any) -> StatusRecord:
        """Move a run to ``state`` (checked against the state machine) and save."""
        status = self.read_status(run_id)
        if status.state != state and not can_transition(status.state, state):
            raise IllegalTransitionError(
                f"{run_id}: {status.state.value} -> {state.value}"
            )
        now = utc_now()
        update: dict[str, Any] = {"state": state, "updated": now, **fields}
        if state == RunState.RUNNING and status.started is None:
            update["started"] = now
        if state in (RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED):
            update["finished"] = now
        status = status.model_copy(update=update)
        self._write_model(self.run_dir(run_id) / "status.json", status)
        return status

    def update_progress(
        self,
        run_id: str,
        progress: float,
        iteration: int,
        metrics: dict[str, float] | None = None,
    ) -> StatusRecord:
        """Record progress, iteration and latest metrics in ``status.json``.

        Args:
            run_id: The run.
            progress: Share of the budget done; clipped to 0..1.
            iteration: Current training iteration.
            metrics: Latest metrics to show.
        """
        status = self.read_status(run_id).model_copy(
            update={
                "progress": max(0.0, min(1.0, progress)),
                "iteration": iteration,
                "last_metrics": metrics or {},
                "updated": utc_now(),
            }
        )
        self._write_model(self.run_dir(run_id) / "status.json", status)
        return status

    def list_runs(
        self, experiment_id: str | None = None, state: RunState | None = None
    ) -> list[StatusRecord]:
        """All runs, oldest first.

        Args:
            experiment_id: Only runs of this experiment.
            state: Only runs in this state.
        """
        out = []
        for folder in self._run_folders():
            status = self.read_status(folder.name)
            if experiment_id and status.experiment_id != experiment_id:
                continue
            if state and status.state != state:
                continue
            out.append(status)
        return sorted(out, key=lambda s: s.created)

    def rebuild_index(self) -> dict[str, Any]:
        """Scan all run folders and rewrite ``index.json`` (a cache only)."""
        index = {
            "runs": {
                s.run_id: {"experiment_id": s.experiment_id, "state": s.state.value}
                for s in self.list_runs()
            }
        }
        atomic_write_text(self.root / "index.json", json.dumps(index, indent=2) + "\n")
        return index

    # ------------------------------------------------------------------ cancel
    def request_cancel(self, run_id: str) -> None:
        """Ask the worker to stop: writes ``cancel.request`` into the run folder."""
        atomic_write_text(
            self.run_dir(run_id) / "cancel.request", utc_now().isoformat()
        )

    def cancel_requested(self, run_id: str) -> bool:
        """True if ``cancel.request`` exists."""
        return (self.run_dir(run_id) / "cancel.request").exists()

    # ------------------------------------------------------------------ streams
    def append_log(self, run_id: str, line: str) -> None:
        """Append a timestamped line to ``logs/worker.log``."""
        with open(
            self.run_dir(run_id) / "logs" / "worker.log", "a", encoding="utf-8"
        ) as f:
            f.write(f"{utc_now().isoformat()} {line.rstrip()}\n")

    def log_tail(self, run_id: str, lines: int = 50) -> list[str]:
        """The last ``lines`` lines of ``logs/worker.log`` (empty without a log)."""
        path = self.run_dir(run_id) / "logs" / "worker.log"
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            return [line.rstrip("\n") for line in deque(f, maxlen=lines)]

    def append_metrics_row(self, run_id: str, name: str, row: dict[str, Any]) -> None:
        """Append one row to ``metrics/<name>.csv``; the first row fixes the header."""
        path = self.run_dir(run_id) / "metrics" / f"{name}.csv"
        new = not path.exists()
        with open(path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            if new:
                writer.writeheader()
            writer.writerow(row)

    def append_jsonl(
        self, run_id: str, relative_path: str, record: dict[str, Any]
    ) -> None:
        """Append one JSON record to ``relative_path`` in the run folder, e.g.
        ``raw/steps.jsonl``.
        """
        path = self.run_dir(run_id) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def read_jsonl(self, run_id: str, relative_path: str) -> Iterator[dict[str, Any]]:
        """The records of a JSONL file in the run folder, one by one (none if it is
        missing).
        """
        path = self.run_dir(run_id) / relative_path
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        yield json.loads(line)

    def write_artifacts(self, run_id: str, files: dict[str, str]) -> ArtifactIndex:
        """Add output files (name → path in the run folder) to ``artifacts.json``."""
        index = self.read_artifacts(run_id)
        index = index.model_copy(update={"files": {**index.files, **files}})
        self._write_model(self.run_dir(run_id) / "artifacts.json", index)
        return index

    def read_artifacts(self, run_id: str) -> ArtifactIndex:
        """The run's artifact index (empty if none)."""
        path = self.run_dir(run_id) / "artifacts.json"
        if not path.exists():
            return ArtifactIndex()
        return ArtifactIndex.model_validate_json(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ helpers
    def _run_folders(self) -> list[Path]:
        if not self.runs_dir.exists():
            return []
        return [p for p in self.runs_dir.iterdir() if (p / "status.json").exists()]

    @staticmethod
    def _write_model(path: Path, model: Any) -> None:
        atomic_write_text(path, model.model_dump_json(indent=2) + "\n")
