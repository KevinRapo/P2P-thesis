"""ExperimentService: creating, starting and watching runs (04 §5, 03).

Runs live in the experiment store; the worker pool starts them as processes and
is polled by one Studio timer (``tick``). Simulation runs (``simulate``) are
built here from a draft file, a controller and a number of days.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from src_thesis.marlem.policies.registry import CATALOG
from src_thesis.platform.experiments.models import expand as expansion
from src_thesis.platform.experiments.models.files import canonical_hash
from src_thesis.platform.experiments.models.manifest import build_manifest
from src_thesis.platform.experiments.models.resolve import resolve_run
from src_thesis.platform.experiments.store.filesystem import (
    ExperimentStore,
    RunExistsError,
)
from src_thesis.platform.experiments.worker import pool as worker_pool
from src_thesis.platform.services.models import (
    ControllerInfo,
    ControllerParam,
    ExperimentFile,
    RepositoryHealth,
    RunCell,
    RunEstimate,
    RunState,
    RunStatus,
    RunSummary,
)
from src_thesis.platform.services.workspace import Workspace

PARADIGMS = ["ctce", "ctde", "dtde"]
ALGORITHMS = ["ppo", "appo", "sac"]


class ExperimentService:
    """Creating, starting, watching and cancelling runs (the experiment layer, 03).

    Args:
        workspace: Where the store lives; the default workspace when ``None``.
        max_parallel: Runs at once.
    """

    SAMPLE_DATA = False

    def __init__(
        self, workspace: Workspace | None = None, max_parallel: int = 1
    ) -> None:
        self.workspace = workspace or Workspace.default()
        self.store = ExperimentStore(self.workspace.store)
        self.pool = worker_pool.WorkerPool(self.store, max_parallel)
        self._reconciled = False

    # ------------------------------------------------------------------ simulation
    def controllers(self) -> list[ControllerInfo]:
        """The scripted controllers a simulation can use, with their parameters."""
        return [
            ControllerInfo(
                name=spec.name,
                title=spec.title,
                description=spec.description,
                params=[
                    ControllerParam(
                        name=name,
                        label=p.label,
                        default=p.default,
                        low=p.low,
                        high=p.high,
                        help=p.help,
                    )
                    for name, p in spec.params.items()
                ],
            )
            for spec in CATALOG.values()
        ]

    def create_simulation(
        self,
        file: ExperimentFile,
        controller: str,
        params: dict[str, float] | None = None,
        day: str | None = None,
        days: int = 1,
        seed: int = 1,
    ) -> str:
        """Write a run folder (state READY) that plays ``days`` days with a controller.

        Args:
            file: The experiment file (a draft is fine).
            controller: One of ``controllers()``.
            params: The controller's parameters.
            day: First day, ``YYYY-MM-DD``; the start of the time window when
                ``None``.
            days: Number of consecutive days.
            seed: Seed of the first day.

        Returns:
            The new run ID.

        Raises:
            ValueError: Unknown controller or parameter, or a value out of range.
        """
        if controller not in CATALOG:
            raise ValueError(f"Unknown controller {controller!r}")
        params = {k: float(v) for k, v in (params or {}).items()}
        for key, value in params.items():
            spec = CATALOG[controller].params.get(key)
            if spec is None:
                raise ValueError(f"{controller} has no parameter {key!r}")
            if not spec.low <= value <= spec.high:
                raise ValueError(f"{key} must be between {spec.low} and {spec.high}")
        label = f"sim-{day or 'start'}-{days}d"
        for attempt in range(1, 100):
            cell = RunCell(
                kind="simulate",
                sweep_label=label if attempt == 1 else f"{label}-r{attempt}",
                algorithm=controller,
                paradigm="-",
                seed=seed,
                controller_params=params,
                day=day,
                days=days,
            )
            resolved = resolve_run(file, cell)
            run_id = expansion.run_id(file.meta.id, cell, canonical_hash(file))
            try:
                self.store.create_run(
                    file, resolved, build_manifest(file, resolved, cell, run_id)
                )
            except RunExistsError:
                continue
            return run_id
        raise RuntimeError("too many runs with the same settings")

    def create_runs(self, file: ExperimentFile) -> list[str]:
        """Write one run folder per run the file asks for, in state READY.

        Only simulation runs can execute for now; training and baseline runs are
        created but fail with a clear message when started.
        """
        ids = []
        file_hash = canonical_hash(file)
        for cell in expansion.expand(file):
            resolved = resolve_run(file, cell)
            run_id = expansion.run_id(file.meta.id, cell, file_hash)
            if not self.store.exists(run_id):
                self.store.create_run(
                    file, resolved, build_manifest(file, resolved, cell, run_id)
                )
            ids.append(run_id)
        return ids

    # ------------------------------------------------------------------ running
    def start(self, run_ids: list[str]) -> None:
        """Queue runs; the worker pool starts them as slots become free."""
        self.pool.enqueue(run_ids)
        self.pool.poll()

    def cancel(self, run_id: str) -> None:
        """Ask a run to stop; a queued run is cancelled at once."""
        self.pool.cancel(run_id)

    def tick(self) -> None:
        """Poll the worker pool; the Studio's one timer calls this."""
        if not self._reconciled:
            worker_pool.reconcile(self.store)
            self._reconciled = True
        self.pool.poll()

    def snapshot(self, run_id: str) -> RunStatus:
        """Current state, progress, last metrics and log tail of one run."""
        status = self.store.read_status(run_id)
        return RunStatus(
            summary=self._summary(status),
            iteration=status.iteration,
            last_metrics=status.last_metrics,
            log_tail=self.store.log_tail(run_id, 8),
        )

    def list_runs(self, experiment_id: str | None = None) -> list[RunSummary]:
        """All runs, newest first, or only those of one experiment."""
        runs = [self._summary(s) for s in self.store.list_runs(experiment_id)]
        return sorted(runs, key=lambda r: r.started or datetime.min, reverse=True)

    def _summary(self, status) -> RunSummary:
        manifest = self.store.read_manifest(status.run_id)
        source = self.store.read_resolved(status.run_id).grid.source
        started = status.started
        end = status.finished or datetime.now(timezone.utc)
        return RunSummary(
            run_id=status.run_id,
            experiment_id=status.experiment_id,
            cell=manifest.cell,
            network=source.code if source and source.code else "",
            state=status.state,
            progress=status.progress,
            started=started,
            elapsed_s=(end - started).total_seconds() if started else 0.0,
            eta_s=None,
        )

    # ------------------------------------------------------------------ overview
    def estimate(self, file: ExperimentFile) -> RunEstimate:
        """How many runs the file creates.

        Training time is not measured yet, so only the count is given.
        """
        n = len(expansion.expand(file))
        return RunEstimate(
            runs=n,
            estimated_hours=0.0,
            note="Training time is not estimated yet; simulation runs take seconds.",
        )

    def health(self) -> RepositoryHealth:
        """Repository state shown on the Home page."""
        try:
            out = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=worker_pool.REPO,
            )
            dirty = bool(out.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            dirty = False
        return RepositoryHealth(
            git_dirty=dirty,
            validation_progress=0.0,
            dependencies_ok=True,
            messages=[
                "Simulation runs work; training runs are not built yet.",
                "Validation plan: see docs_thesis/thesis/validation.",
            ],
        )
