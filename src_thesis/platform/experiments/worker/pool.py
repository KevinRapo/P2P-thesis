"""Starting, watching and cancelling worker processes.

Why: something has to start the worker processes, keep only as many running as the
machine can take (one RLlib run already uses every core), notice processes that died,
and pass on cancel requests. It lives in the process that owns ``ExperimentService``
(Studio or CLI) and is polled by the Studio's timer instead of running its own thread,
which keeps it free of thread-safety issues. Closing the Studio never stops a worker.

Lives in the process that owns ``ExperimentService`` (the Studio or the CLI).
The pool is polled, not threaded: each ``poll()`` reaps finished workers and
starts queued runs while there are free slots. Closing the Studio never stops
a worker; ``reconcile`` marks runs whose worker died as FAILED.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from src_thesis.platform.experiments.models.records import RunState
from src_thesis.platform.experiments.store.filesystem import ExperimentStore

REPO = Path(__file__).resolve().parents[4]


def spawn(run_dir: str | Path) -> subprocess.Popen:
    """Start ``python -m src_thesis.platform.experiments.worker`` in its own process group."""
    run_dir = Path(run_dir)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    out = open(run_dir / "logs" / "worker.stdout", "a", encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "src_thesis.platform.experiments.worker",
            "--run-dir",
            str(run_dir),
        ],
        cwd=REPO,
        stdout=out,
        stderr=subprocess.STDOUT,
        creationflags=flags,
        start_new_session=os.name != "nt",
    )


def pid_alive(pid: int) -> bool:
    """Whether a process with this ID still runs. On Windows via ``OpenProcess``,
    because ``os.kill(pid, 0)`` is not a check there.
    """
    if os.name == "nt":
        import ctypes

        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # query
        if not process:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(process)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def reconcile(store: ExperimentStore) -> list[str]:
    """Mark RUNNING / CANCELLING runs whose worker process is gone as FAILED."""
    failed = []
    for status in store.list_runs():
        if status.state in (RunState.RUNNING, RunState.CANCELLING):
            if status.pid is None or not pid_alive(status.pid):
                store.set_state(status.run_id, RunState.FAILED, message="worker died")
                failed.append(status.run_id)
    return failed


class WorkerPool:
    """Starts, watches and cancels worker processes; polled by the Studio or CLI, not
    threaded.

    Args:
        store: The experiment store.
        max_parallel: Runs at once; default 1, because one RLlib run already uses every
            core.
    """

    def __init__(self, store: ExperimentStore, max_parallel: int = 1) -> None:
        self.store = store
        self.max_parallel = max(1, max_parallel)
        self._queue: list[str] = []
        self._running: dict[str, subprocess.Popen] = {}

    def enqueue(self, run_ids: list[str]) -> None:
        """Mark runs QUEUED; ``poll`` starts them as slots become free."""
        for run_id in run_ids:
            self.store.set_state(run_id, RunState.QUEUED)
            self._queue.append(run_id)

    def poll(self) -> dict[str, RunState]:
        """Reap finished workers, start queued runs; returns the states it knows."""
        for run_id, process in list(self._running.items()):
            if process.poll() is not None:
                del self._running[run_id]
                if self.store.read_status(run_id).state not in (
                    RunState.COMPLETED,
                    RunState.FAILED,
                    RunState.CANCELLED,
                ):
                    self.store.set_state(
                        run_id, RunState.FAILED, message="worker exited early"
                    )
        while self._queue and len(self._running) < self.max_parallel:
            run_id = self._queue.pop(0)
            if self.store.read_status(run_id).state == RunState.QUEUED:
                self._running[run_id] = spawn(self.store.run_dir(run_id))
        return {
            r: self.store.read_status(r).state for r in [*self._running, *self._queue]
        }

    def cancel(self, run_id: str, force_after_s: float | None = None) -> None:
        """Ask a run to stop; queued runs are cancelled at once."""
        if run_id in self._queue:
            self._queue.remove(run_id)
            self.store.set_state(
                run_id, RunState.CANCELLED, message="cancelled in queue"
            )
            return
        self.store.request_cancel(run_id)
        if self.store.read_status(run_id).state == RunState.RUNNING:
            self.store.set_state(run_id, RunState.CANCELLING)
        process = self._running.get(run_id)
        if force_after_s is not None and process is not None:
            try:
                process.wait(timeout=force_after_s)
            except subprocess.TimeoutExpired:
                process.kill()

    def wait_all(self, timeout_s: float = 60.0, interval_s: float = 0.2) -> None:
        """Poll until nothing is queued or running (for the CLI and tests)."""
        deadline = time.monotonic() + timeout_s
        while (self._queue or self._running) and time.monotonic() < deadline:
            self.poll()
            time.sleep(interval_s)
        self.poll()
