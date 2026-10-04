"""ExperimentService: creating, starting and watching runs (04 §5, 03).

Final implementation: ``StoreExperimentService``, not built yet (R7); everything it
needs below exists in ``experiments/``. Demo: ``DemoExperimentService`` (invented
runs; nothing is started).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol
from src_thesis.application.config_service import (
    ALGORITHMS,
    PARADIGMS,
    _NOW,
    DemoConfigService,
)
from src_thesis.application.models import (
    ExperimentFile,
    RepositoryHealth,
    RunCell,
    RunEstimate,
    RunState,
    RunStatus,
    RunSummary,
)


# ---------------------------------------------------------------------- protocol
class ExperimentService(Protocol):
    """Creating, starting, watching and cancelling runs (the experiment layer, 03)."""

    def create_runs(self, file: ExperimentFile) -> list[str]:
        """Validate, expand and write one run folder per run, in state READY.

        Returns:
            The new run IDs.
        """
        ...

    def start(self, run_ids: list[str]) -> None:
        """Queue runs; the worker pool starts them as slots become free."""
        ...

    def cancel(self, run_id: str) -> None:
        """Ask a run to stop; a queued run is cancelled at once."""
        ...

    def snapshot(self, run_id: str) -> RunStatus:
        """Current state, progress, last metrics and log tail of one run."""
        ...

    def list_runs(self, experiment_id: str | None = None) -> list[RunSummary]:
        """All runs, or only those of one experiment."""
        ...

    def estimate(self, file: ExperimentFile) -> RunEstimate:
        """How many runs the file creates and roughly how long they take."""
        ...

    def health(self) -> RepositoryHealth:
        """Repository and environment state shown on the Home page."""
        ...


# ---------------------------------------------------------------------- final implementation (skeleton)
_NOT_BUILT = (
    "Not built yet: the final implementation of this service waits for its "
    "roadmap phase; the Studio uses the demo implementation until then."
)


class StoreExperimentService:
    """The final ``ExperimentService`` over the experiment store and worker pool (R7).

    Not implemented yet; every method raises. Everything it needs below exists:
    ``experiments.models``, ``experiments.store.filesystem``,
    ``experiments.worker.pool`` (03).
    """

    def create_runs(self, file: ExperimentFile) -> list[str]:
        """Will validate, then ``expand``; per cell ``resolve_run``, ``run_id``,
        ``build_manifest`` and ``ExperimentStore.create_run`` (state READY)."""
        raise NotImplementedError(_NOT_BUILT)

    def start(self, run_ids: list[str]) -> None:
        """Will call ``WorkerPool.enqueue``; the Studio's timer then calls ``poll``."""
        raise NotImplementedError(_NOT_BUILT)

    def cancel(self, run_id: str) -> None:
        """Will call ``WorkerPool.cancel`` (queued: at once; running: cancel request)."""
        raise NotImplementedError(_NOT_BUILT)

    def snapshot(self, run_id: str) -> RunStatus:
        """Will combine ``ExperimentStore.read_status`` and ``log_tail``."""
        raise NotImplementedError(_NOT_BUILT)

    def list_runs(self, experiment_id: str | None = None) -> list[RunSummary]:
        """Will call ``ExperimentStore.list_runs``; ``reconcile`` once at start-up."""
        raise NotImplementedError(_NOT_BUILT)

    def estimate(self, file: ExperimentFile) -> RunEstimate:
        """Will count ``expand(file)`` and multiply by stored benchmark timings."""
        raise NotImplementedError(_NOT_BUILT)

    def health(self) -> RepositoryHealth:
        """Will read git state, the installed packages and validation progress."""
        raise NotImplementedError(_NOT_BUILT)


# ---------------------------------------------------------------------- demo implementation
class DemoExperimentService:
    """Demo ``ExperimentService``: invented runs; nothing is started. Shown as DEMO DATA
    in the Studio.
    """

    def __init__(self) -> None:
        self._runs = self._seed_runs()

    @staticmethod
    def _seed_runs() -> list[RunSummary]:
        states = [RunState.COMPLETED] * 5 + [
            RunState.RUNNING,
            RunState.RUNNING,
            RunState.QUEUED,
            RunState.FAILED,
        ]
        runs = []
        for i, (m, a) in enumerate((m, a) for m in PARADIGMS for a in ALGORITHMS):
            state = states[i]
            progress = {
                RunState.COMPLETED: 1.0,
                RunState.RUNNING: 0.35 + 0.2 * i / 9,
                RunState.QUEUED: 0.0,
                RunState.FAILED: 0.62,
            }[state]
            runs.append(
                RunSummary(
                    run_id=f"case6-3x3__{a}-{m}__s1__{1000 + i:x}",
                    experiment_id="case6-3x3",
                    cell=RunCell(algorithm=a, paradigm=m, seed=1),
                    network="1-LV-semiurb4--0-sw",
                    state=state,
                    progress=round(progress, 2),
                    started=_NOW - timedelta(hours=9 - i),
                    elapsed_s=3600 * (9 - i) * progress,
                    eta_s=3600 * 2.5 if state == RunState.RUNNING else None,
                )
            )
        return runs

    def create_runs(self, file: ExperimentFile) -> list[str]:
        """Sample-data version of ``ExperimentService.create_runs``."""
        return [
            f"{file.meta.id}__{c.algorithm}-{c.paradigm}__s{c.seed}"
            for c in DemoConfigService().expand(file)
        ]

    def start(self, run_ids: list[str]) -> None:
        """Sample-data version of ``ExperimentService.start``."""
        return None

    def cancel(self, run_id: str) -> None:
        """Sample-data version of ``ExperimentService.cancel``."""
        return None

    def snapshot(self, run_id: str) -> RunStatus:
        """Sample-data version of ``ExperimentService.snapshot``."""
        run = next((r for r in self._runs if r.run_id == run_id), self._runs[0])
        it = int(run.progress * 200)
        return RunStatus(
            summary=run,
            iteration=it,
            last_metrics={
                "episode_return_mean": round(-40 + 60 * run.progress, 2),
                "violations_per_episode": round(8 * (1 - run.progress), 2),
            },
            log_tail=[
                f"[iter {max(0, it - k)}] episode_return_mean={-40 + 60 * run.progress - k:.2f}"
                for k in range(5, 0, -1)
            ],
        )

    def list_runs(self, experiment_id: str | None = None) -> list[RunSummary]:
        """Sample-data version of ``ExperimentService.list_runs``."""
        return [
            r
            for r in self._runs
            if experiment_id is None or r.experiment_id == experiment_id
        ]

    def estimate(self, file: ExperimentFile) -> RunEstimate:
        """Sample-data version of ``ExperimentService.estimate``."""
        n = len(DemoConfigService().expand(file))
        return RunEstimate(
            runs=n,
            estimated_hours=round(n * 3.2, 1),
            note="Demo estimate from placeholder benchmarks.",
        )

    def health(self) -> RepositoryHealth:
        """Sample-data version of ``ExperimentService.health``."""
        return RepositoryHealth(
            git_dirty=True,
            validation_progress=0.0,
            dependencies_ok=True,
            messages=[
                "Demo services active: no MARLEM code is executed.",
                "Validation plan: 0 of 80 issues closed.",
            ],
        )
