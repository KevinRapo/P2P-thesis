"""ExperimentService: creating, starting and watching runs (04 §5, 03).

Every method still returns invented runs and starts nothing; each docstring says
what the final version will call. Everything it needs below already exists in
``experiments/`` (R7). The sample constants are shared with ``result_service``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from src_thesis.application.models import (
    ExperimentFile,
    RepositoryHealth,
    RunCell,
    RunEstimate,
    RunState,
    RunStatus,
    RunSummary,
)
from src_thesis.experiments.models.expand import expand

PARADIGMS = ["ctce", "ctde", "dtde"]


ALGORITHMS = ["ppo", "appo", "sac"]


SAMPLE_NOW = datetime(2026, 9, 23, 12, 0)


class ExperimentService:
    """Creating, starting, watching and cancelling runs (the experiment layer, 03).

    Every method returns sample data until it is built; its docstring says what the
    final version will do.
    """

    SAMPLE_DATA = True  # shown in the Studio's header until the service is built

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
                    started=SAMPLE_NOW - timedelta(hours=9 - i),
                    elapsed_s=3600 * (9 - i) * progress,
                    eta_s=3600 * 2.5 if state == RunState.RUNNING else None,
                )
            )
        return runs

    def create_runs(self, file: ExperimentFile) -> list[str]:
        """Validate, expand and write one run folder per run, in state READY.

        Sample data for now. The final version will validate, then ``expand``; per cell
        ``resolve_run``, ``run_id``, ``build_manifest`` and
        ``ExperimentStore.create_run`` (state READY).

        Returns:
            The new run IDs.
        """
        return [
            f"{file.meta.id}__{c.algorithm}-{c.paradigm}__s{c.seed}"
            for c in expand(file)
        ]

    def start(self, run_ids: list[str]) -> None:
        """Queue runs; the worker pool starts them as slots become free.

        Sample data for now. The final version will call ``WorkerPool.enqueue``; the
        Studio's timer then calls ``poll``.
        """
        return None

    def cancel(self, run_id: str) -> None:
        """Ask a run to stop; a queued run is cancelled at once.

        Sample data for now. The final version will call ``WorkerPool.cancel`` (queued:
        at once; running: cancel request).
        """
        return None

    def snapshot(self, run_id: str) -> RunStatus:
        """Current state, progress, last metrics and log tail of one run.

        Sample data for now. The final version will combine
        ``ExperimentStore.read_status`` and ``log_tail``.
        """
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
        """All runs, or only those of one experiment.

        Sample data for now. The final version will call ``ExperimentStore.list_runs``;
        ``reconcile`` once at start-up.
        """
        return [
            r
            for r in self._runs
            if experiment_id is None or r.experiment_id == experiment_id
        ]

    def estimate(self, file: ExperimentFile) -> RunEstimate:
        """How many runs the file creates and roughly how long they take.

        Sample data for now. The final version will count ``expand(file)`` and multiply
        by stored benchmark timings.
        """
        n = len(expand(file))
        return RunEstimate(
            runs=n,
            estimated_hours=round(n * 3.2, 1),
            note="Sample estimate from placeholder benchmarks.",
        )

    def health(self) -> RepositoryHealth:
        """Repository and environment state shown on the Home page.

        Sample data for now. The final version will read git state, the installed
        packages and validation progress.
        """
        return RepositoryHealth(
            git_dirty=True,
            validation_progress=0.0,
            dependencies_ok=True,
            messages=[
                "Sample data: runs and health are not built yet.",
                "Validation plan: 0 of 80 issues closed.",
            ],
        )
