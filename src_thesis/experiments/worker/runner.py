"""What a worker actually runs (05-experiment-layer.md §3.9).

A runner executes one run inside the worker process. It never touches the
status file itself: it reports progress through its ``RunContext`` and returns
a ``RunOutcome``; the worker turns that into the terminal state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..models.records import ExperimentFile, Manifest, RunCell, RunState
from ..store.recorder import EpisodeRecorder
from ..store.filesystem import ExperimentStore


@dataclass
class RunContext:
    """What a runner may use: progress, log, cancel check and step recorder.

    A runner never writes ``status.json``; the worker sets the final state from
    the returned ``RunOutcome``.

    Attributes:
        store: The experiment store.
        run_id: The run.
        resolved: The run's fully resolved experiment file.
        manifest: The run's manifest.
    """

    store: ExperimentStore
    run_id: str
    resolved: ExperimentFile
    manifest: Manifest

    @property
    def cell(self) -> RunCell:
        """The run's cell: algorithm, paradigm, seed and sweep point."""
        return self.manifest.cell

    def should_stop(self) -> bool:
        """True once a cancel was requested; check at iteration or episode ends."""
        return self.store.cancel_requested(self.run_id)

    def report(
        self, progress: float, iteration: int, metrics: dict[str, float] | None = None
    ) -> None:
        """Record progress (0..1 of the budget), iteration and latest metrics."""
        self.store.update_progress(self.run_id, progress, iteration, metrics)

    def log(self, message: str) -> None:
        """Append a line to the run's log."""
        self.store.append_log(self.run_id, message)

    def recorder(self) -> EpisodeRecorder:
        """An ``EpisodeRecorder`` in the file's ``outputs.record_steps`` mode."""
        mode = self.resolved.outputs.get("record_steps", "evaluation")
        return EpisodeRecorder(self.store, self.run_id, mode)


@dataclass(frozen=True)
class RunOutcome:
    """How a runner ended; the worker turns it into the terminal state.

    Attributes:
        state: COMPLETED, CANCELLED or FAILED.
        message: Shown with the run in the Studio.
        artifacts: Output files (name → path in the run folder) to index.
    """

    state: RunState  # COMPLETED, CANCELLED or FAILED
    message: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)


class Runner(Protocol):
    """What every runner implements."""

    def run(self, ctx: RunContext) -> RunOutcome:
        """Execute the run and say how it ended."""
        ...


class NoopRunner:
    """A smoke run: a few iterations that only report progress and honour cancel."""

    def __init__(self, iterations: int = 3, delay_s: float = 0.0) -> None:
        self.iterations = iterations
        self.delay_s = delay_s

    def run(self, ctx: RunContext) -> RunOutcome:
        """Report a few iterations; ends CANCELLED early if a cancel was requested."""
        for i in range(1, self.iterations + 1):
            if ctx.should_stop():
                return RunOutcome(
                    RunState.CANCELLED, f"cancelled after {i - 1} iterations"
                )
            time.sleep(self.delay_s)
            ctx.report(i / self.iterations, i, {"noop": float(i)})
            ctx.store.append_metrics_row(ctx.run_id, "training", {"iteration": i})
        return RunOutcome(RunState.COMPLETED, "noop run finished")


class BaselineRunner:
    """Scripted policies (no order, random, rule-based) on the eval days (02 §3.10)."""

    def run(self, ctx: RunContext) -> RunOutcome:
        """Not implemented: needs ``factory.build_env`` (R1, R4) and
        ``marl/baselines.py``.
        """
        raise NotImplementedError(
            "baselines need factory.build_env (R1, R4) and marl/baselines.py"
        )


class TrainingRunner:
    """RLlib training with evaluation; owns ``ray.init`` / ``ray.shutdown`` (05 §3.10)."""

    def run(self, ctx: RunContext) -> RunOutcome:
        """Not implemented: training runs are built in validation stage D."""
        raise NotImplementedError("training runs are built in validation stage D")


RUNNERS: dict[str, Callable[[], Runner]] = {
    "noop": NoopRunner,
    "baseline": BaselineRunner,
    "train": TrainingRunner,
}


def select_runner(cell: RunCell) -> Runner:
    """A new runner for the cell's kind (``train``, ``baseline`` or ``noop``)."""
    return RUNNERS[cell.kind]()
