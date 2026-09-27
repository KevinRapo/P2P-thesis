"""The worker process: runs exactly one run (06-experiment-layer.md §3.10, 04 §4).

    python -m src_thesis.experiments.worker --run-dir <store>/runs/<run_id>

Steps: verify the manifest hash → RUNNING (with pid) → runner → terminal state.
Any exception ends in FAILED with the traceback in ``logs/worker.log``. If Ray
was started by the runner, it is shut down in ``finally``.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

from ..models.files import canonical_hash
from ..models.records import RunState
from .runner import Runner, RunContext, RunOutcome, select_runner
from ..store.filesystem import ExperimentStore


def run_one(run_dir: str | Path, runner: Runner | None = None) -> RunState:
    """Execute the run in ``run_dir`` and return its terminal state."""
    run_dir = Path(run_dir).resolve()
    store = ExperimentStore(run_dir.parents[1])
    run_id = run_dir.name
    try:
        manifest = store.read_manifest(run_id)
        resolved = store.read_resolved(run_id)
        if canonical_hash(resolved) != manifest.resolved_hash:
            return _finish(
                store,
                run_id,
                RunOutcome(
                    RunState.FAILED,
                    "resolved.json changed since the manifest was written",
                ),
            )
        if store.cancel_requested(run_id):
            return _finish(
                store, run_id, RunOutcome(RunState.CANCELLED, "cancelled before start")
            )
        store.set_state(run_id, RunState.RUNNING, pid=os.getpid(), message="")
        store.append_log(run_id, f"worker {os.getpid()} started ({manifest.cell.kind})")
        ctx = RunContext(store, run_id, resolved, manifest)
        outcome = (runner or select_runner(manifest.cell)).run(ctx)
    except Exception as error:  # noqa: BLE001  every failure becomes FAILED
        store.append_log(run_id, traceback.format_exc())
        outcome = RunOutcome(RunState.FAILED, f"{type(error).__name__}: {error}")
    finally:
        _shutdown_ray()
    return _finish(store, run_id, outcome)


def _finish(store: ExperimentStore, run_id: str, outcome: RunOutcome) -> RunState:
    if outcome.artifacts:
        store.write_artifacts(run_id, outcome.artifacts)
    status = store.read_status(run_id)
    state = outcome.state  # a run that finished while CANCELLING stays COMPLETED
    if status.state != state:
        store.set_state(run_id, state, message=outcome.message)
    store.append_log(run_id, f"finished: {state.value} {outcome.message}".rstrip())
    return state


def _shutdown_ray() -> None:
    ray = sys.modules.get("ray")  # only if a runner imported it
    if ray is not None and ray.is_initialized():
        ray.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one MARLEM experiment run.")
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    state = run_one(args.run_dir)
    return 0 if state in (RunState.COMPLETED, RunState.CANCELLED) else 1
