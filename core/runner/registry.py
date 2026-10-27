"""A read-only view of ``runs/``: which experiments exist and how their runs are doing.

Everything is derived from files, so the CLI and the Studio can call it as often as
they like (every 2 seconds is fine) and see the same thing:

    runs/<experiment>/experiment.json    the spec the runner was started with
    runs/<experiment>/worker.json        pid and start time of the worker process
    runs/<experiment>/slurm.json         the SLURM job array of the experiment, if any
    runs/<experiment>/<run>/status.json  state of one run (written by the runner)
    runs/<experiment>/<run>/run.json     the trainer's record (also in old runs)

States: ``queued``, ``running``, ``completed``, ``failed``, ``stopped``; ``lost``
is derived: the run says it is running but its process is gone (killed, machine
restarted), or it is queued but the worker that should start it is gone. Old run
folders without ``status.json`` get ``completed`` or ``failed`` from their
``run.json``, else ``unknown``.

A run submitted to a SLURM cluster has a ``slurm_job`` (its task id, e.g.
``1042700_3``) in its ``status.json``. Its process is on a compute node, so liveness
comes from the SLURM state of that task instead of a pid: the caller asks SLURM
(``slurm.states``) and passes the answer, a ``{task id: {"state", "node"}}`` map, to
``runs`` and the functions below, which never call SLURM themselves. Without the
map a task counts as unknown: what the status file says stands.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import psutil

from core.runner.spec import runs_root

STATES = ("queued", "running", "completed", "failed", "stopped", "lost", "unknown")
# SLURM task states that end a task / that mean it is on a node.
SLURM_TERMINAL = (
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "OUT_OF_MEMORY",
    "NODE_FAIL",
    "PREEMPTED",
    "BOOT_FAIL",
    "DEADLINE",
)
SLURM_RUNNING = ("RUNNING", "COMPLETING")


# --------------------------------------------------------------------------------------
# Files and processes
# --------------------------------------------------------------------------------------
def read_json(path: Path) -> Optional[dict]:
    """The JSON object in ``path``, or None if missing or half-written."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def process_alive(pid: Optional[int], create_time: Optional[float]) -> bool:
    """Whether ``pid`` is the process that started at ``create_time`` (a reused pid
    has another start time)."""
    if not pid or create_time is None:
        return False
    try:
        process = psutil.Process(int(pid))
        if process.status() == psutil.STATUS_ZOMBIE:
            return False
        return abs(process.create_time() - float(create_time)) < 1.0
    except (psutil.Error, ValueError):
        return False


def worker_info(exp_dir: Path) -> Optional[dict]:
    return read_json(Path(exp_dir) / "worker.json")


def worker_alive(exp_dir: Path) -> bool:
    info = worker_info(exp_dir)
    return bool(info) and process_alive(info.get("pid"), info.get("create_time"))


# --------------------------------------------------------------------------------------
# One run
# --------------------------------------------------------------------------------------
@dataclass
class RunState:
    """How one run is doing (see the module for the states)."""

    name: str
    state: str
    progress: float = 0.0  # 0..1, environment steps done / budget
    env_steps: int = 0
    budget: Optional[int] = None
    started: Optional[str] = None
    elapsed_s: Optional[float] = None
    eta_s: Optional[float] = None
    last_eval: Optional[float] = None  # team return of "trained", latest evaluation
    heldout: Optional[float] = None  # team return of "trained" on the test days
    error: Optional[str] = None
    slurm_state: Optional[str] = None  # the SLURM state of the run's task, if any
    host: Optional[str] = None  # the machine the job ran on


def current_state(
    run_dir: Path, worker_dead: bool = False, slurm: Optional[dict] = None
) -> Optional[str]:
    """Just the state of a run folder (None if it is not a run folder). Cheap.

    ``slurm`` is the map from ``slurm.states``, for runs with a ``slurm_job``."""
    status = read_json(Path(run_dir) / "status.json")

    if status is None:
        return _legacy_state(read_json(Path(run_dir) / "run.json"))

    return _state_of(status, worker_dead, slurm)


def _slurm_state(status: dict, slurm: Optional[dict]) -> Optional[str]:
    """The SLURM state of the run's task (None: no task, or SLURM has not said)."""
    task = status.get("slurm_job")
    info = (slurm or {}).get(str(task)) if task else None

    return info.get("state") if info else None


def _state_of(status: dict, worker_dead: bool, slurm: Optional[dict] = None) -> str:
    state = str(status.get("state", "unknown"))

    if status.get("slurm_job"):  # its process is on a node: ask SLURM, not psutil
        slurm_state = _slurm_state(status, slurm)

        if state == "running" and slurm_state in SLURM_TERMINAL:
            return "lost"

        if state == "queued":
            if slurm_state in SLURM_TERMINAL:
                return "lost"
            return "running" if slurm_state in SLURM_RUNNING else "queued"

        return state

    if state == "running" and not process_alive(
        status.get("pid"), status.get("create_time")
    ):
        return "lost"

    if state == "queued" and worker_dead:
        return "lost"

    return state


def _legacy_state(record: Optional[dict]) -> Optional[str]:
    if record is None:
        return None
    state = record.get("status")
    return state if state in ("completed", "failed") else "unknown"


def _complete(text: str) -> list[str]:
    """The lines of ``text`` without a last one still being written (no line end)."""
    lines = text.splitlines()

    if lines and not text.endswith("\n"):
        lines.pop()

    return lines


def _last_row(path: Path) -> Optional[dict]:
    """The last complete row of a CSV as a dict, reading only its first line and
    its end: 8 kB, or more until the end holds a whole row (a run with many agents
    writes rows of more than 8 kB)."""
    try:
        with open(path, "rb") as handle:
            header = handle.readline().decode("utf-8").strip()
            handle.seek(0, 2)
            size = handle.tell()
            window = 8192

            while True:
                start = max(0, size - window)
                handle.seek(start)
                tail = _complete(handle.read().decode("utf-8", errors="replace"))
                # The first line of a window inside the file may be a row's end.
                if start > 0:
                    tail = tail[1:]
                if start == 0 or any(line.strip() for line in tail):
                    break
                window *= 4
    except OSError:
        return None

    lines = [line for line in tail if line.strip()]

    if not lines or lines[-1].strip() == header:
        return None

    try:
        row = next(csv.reader([lines[-1]]))
        return dict(zip(next(csv.reader([header])), row))
    except (StopIteration, csv.Error):
        return None


def _trained_return(path: Path, last: bool) -> Optional[float]:
    """Team return of the policy ``trained`` in an evaluation CSV (latest row, or
    the only one)."""
    try:
        lines = _complete(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None

    rows = [r for r in csv.DictReader(lines) if r.get("policy") == "trained"]

    if not rows:
        return None

    try:
        return float(rows[-1 if last else 0]["team_return_mean"])
    except (KeyError, ValueError):
        return None


def _parse_time(text: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(text))
    except ValueError:
        return None


def _elapsed(run_dir: Path, state: str, status: dict, record: dict) -> Optional[float]:
    if status.get("duration_s") is not None:
        return float(status["duration_s"])

    started = _parse_time(status.get("started") or record.get("started"))

    if state == "running" and started:
        return max(0.0, (datetime.now() - started).total_seconds())

    if started is None:
        duration = record.get("duration_s")
        return float(duration) if duration is not None else None

    finished = _parse_time(status.get("finished") or record.get("finished"))

    if finished:
        return max(0.0, (finished - started).total_seconds())

    if state in ("lost", "failed", "stopped"):  # last sign of life
        try:
            return max(0.0, (run_dir / "log.txt").stat().st_mtime - started.timestamp())
        except OSError:
            return None

    return None


def run_state(
    run_dir: Path, worker_dead: bool = False, slurm: Optional[dict] = None
) -> Optional[RunState]:
    """The state of one run folder, or None if it is not a run folder."""
    run_dir = Path(run_dir)
    status = read_json(run_dir / "status.json")
    record = read_json(run_dir / "run.json") or {}

    if status is None and not record:
        return None

    state = _state_of(status, worker_dead, slurm) if status else _legacy_state(record)
    status = status or {}
    budget = status.get("budget") or record.get("budget_env_steps")
    last = _last_row(run_dir / "metrics.csv")

    try:
        env_steps = int(float(last["env_steps"])) if last else 0
    except (KeyError, ValueError, TypeError):
        env_steps = 0

    env_steps = max(env_steps, int(record.get("env_steps") or 0))
    progress = min(1.0, env_steps / budget) if budget else 0.0

    if state == "completed":
        progress = 1.0

    elapsed = _elapsed(run_dir, state, status, record) if state != "queued" else None
    eta = None

    if state == "running" and elapsed and 0 < progress < 1:
        eta = elapsed * (1 - progress) / progress

    return RunState(
        name=run_dir.name,
        state=state,
        progress=progress,
        env_steps=env_steps,
        budget=int(budget) if budget else None,
        started=status.get("started") or record.get("started"),
        elapsed_s=elapsed,
        eta_s=eta,
        last_eval=_trained_return(run_dir / "evaluation.csv", last=True),
        heldout=_trained_return(run_dir / "heldout.csv", last=False),
        error=status.get("error")
        or (record.get("error") if state == "failed" else None),
        slurm_state=_slurm_state(status, slurm),
        host=status.get("host"),
    )


# --------------------------------------------------------------------------------------
# Experiments
# --------------------------------------------------------------------------------------
def _is_run_dir(path: Path) -> bool:
    return path.is_dir() and (
        (path / "status.json").exists() or (path / "run.json").exists()
    )


def experiments(root: Optional[Path] = None) -> list[str]:
    """Names of the folders in ``runs/`` that hold runs, sorted."""
    root = Path(root) if root else runs_root()

    if not root.is_dir():
        return []

    found = []

    for folder in sorted(root.iterdir()):
        try:
            if folder.is_dir() and any(_is_run_dir(c) for c in folder.iterdir()):
                found.append(folder.name)
        except OSError:
            continue

    return found


def runs(
    experiment: str, root: Optional[Path] = None, slurm: Optional[dict] = None
) -> list[RunState]:
    """The runs of an experiment in the order of its grid (else by name).

    ``slurm`` is the map from ``slurm.states`` (see the module)."""
    root = Path(root) if root else runs_root()
    exp_dir = root / experiment
    info = worker_info(exp_dir)
    worker_dead = bool(info) and not worker_alive(exp_dir)
    entries = []

    for folder in exp_dir.iterdir() if exp_dir.is_dir() else []:
        if not _is_run_dir(folder):
            continue
        state = run_state(folder, worker_dead, slurm)
        if state is not None:
            index = (read_json(folder / "status.json") or {}).get("index", 10**9)
            entries.append((index, folder.name, state))

    return [state for _, _, state in sorted(entries, key=lambda e: e[:2])]


def summary(
    experiment: str, root: Optional[Path] = None, slurm: Optional[dict] = None
) -> dict[str, Any]:
    """Counts per state, the mean progress and whether a worker is alive."""
    return summarize(runs(experiment, root, slurm), experiment, root)


def summarize(
    states: list[RunState], experiment: str, root: Optional[Path] = None
) -> dict[str, Any]:
    """``summary`` of run states already read (``runs``)."""
    counts: dict[str, int] = {}

    for state in states:
        counts[state.state] = counts.get(state.state, 0) + 1

    exp_dir = (Path(root) if root else runs_root()) / experiment

    return {
        "runs": len(states),
        "counts": counts,
        "progress": sum(s.progress for s in states) / len(states) if states else 0.0,
        "worker_alive": worker_alive(exp_dir),
    }
