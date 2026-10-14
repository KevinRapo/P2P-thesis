"""Start, run and stop experiments as detached processes.

``start`` writes the experiment's folder and spawns one detached *worker* that
outlives the terminal, the Studio and the Claude session. The worker keeps up to
``max_parallel`` *job* processes running, one per run; a job trains a run and
evaluates it on the test days. State lives in files only (see ``registry.py``):

    runs/<experiment>/experiment.json    copy of the spec (name filled in)
    runs/<experiment>/worker.json        worker pid and start time
    runs/<experiment>/worker.log         the worker's output
    runs/<experiment>/<run>/status.json  queued -> running -> completed | failed
    runs/<experiment>/<run>/log.txt      the job's output
    runs/<experiment>/<run>/heldout.csv  trained policy and baselines on test days

Jobs are not killed when the worker dies: they run on to the end and write their
own status, but nothing starts the queued runs behind them until ``start`` is run
again, which skips completed (and still running) runs and re-queues the rest.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil

from core.runner import registry
from core.runner.spec import REPO, Experiment, RunSpec, runs_root

POLL_S = 5.0
# Gap between two job starts: Ray's start-up fails more often when several nodes
# start at once on a busy machine.
STAGGER_S = 10.0
PYTHON = sys.executable
# Files a re-queued run must not keep from its earlier attempt.
STALE = ("run.json", "metrics.csv", "evaluation.csv", "heldout.csv", "log.txt")


# --------------------------------------------------------------------------------------
# Status files
# --------------------------------------------------------------------------------------
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_json(path: Path, data: dict) -> None:
    """Replace a JSON file in one step, so a reader never sees half of it."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    for attempt in range(20):  # Windows refuses while a reader has the file open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def write_status(run_dir: Path, replace: bool = False, **fields) -> dict:
    """Merge ``fields`` into the run's ``status.json`` (or replace it)."""
    run_dir = Path(run_dir)
    status = {} if replace else registry.read_json(run_dir / "status.json") or {}
    status |= fields | {"updated": _now()}
    _write_json(run_dir / "status.json", status)
    return status


def _self_process() -> dict:
    return {"pid": os.getpid(), "create_time": psutil.Process().create_time()}


# --------------------------------------------------------------------------------------
# start: the folder, the queue and the detached worker
# --------------------------------------------------------------------------------------
def _spawn_detached(args: list[str], log: Path) -> subprocess.Popen:
    """A process that keeps running after the caller (and its terminal) is gone."""
    env = os.environ | {"PYTHONPATH": str(REPO), "PYTHONUNBUFFERED": "1"}
    options: dict = dict(
        args=[PYTHON, "-m", "core.runner", *args],
        cwd=REPO,
        env=env,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    with open(log, "ab") as out:
        options |= {"stdout": out, "stderr": subprocess.STDOUT}
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            try:  # leave the caller's job object, if it allows it
                return subprocess.Popen(
                    creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB,
                    **options,
                )
            except OSError:
                return subprocess.Popen(creationflags=flags, **options)
        return subprocess.Popen(start_new_session=True, **options)


def start(spec_path: str | Path, root: Optional[Path] = None) -> Path:
    """Queue an experiment and start its worker; returns at once.

    Starting an experiment that already has runs resumes it: completed runs (and
    runs still alive) stay, failed, stopped and lost runs start again from scratch.

    Returns:
        The experiment's folder.
    """
    experiment = Experiment.load(spec_path)
    exp_dir = (Path(root) if root else runs_root()) / experiment.name
    if registry.worker_alive(exp_dir):
        raise RuntimeError(
            f"experiment '{experiment.name}' already has a running worker "
            f"(pid {registry.worker_info(exp_dir)['pid']}); stop it first with "
            f"`python -m core.runner stop {experiment.name}`"
        )
    specs = experiment.expand(exp_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    _write_json(exp_dir / "experiment.json", data | {"name": experiment.name})
    for spec in specs:
        if registry.current_state(spec.out_dir) in ("completed", "running"):
            continue
        _reset(spec)
    process = _spawn_detached(["work", str(exp_dir)], exp_dir / "worker.log")
    _write_json(
        exp_dir / "worker.json",
        {
            "pid": process.pid,
            "create_time": psutil.Process(process.pid).create_time(),
            "started": _now(),
        },
    )
    return exp_dir


def _reset(spec: RunSpec) -> None:
    """Queue a run: forget the files of an earlier attempt."""
    spec.out_dir.mkdir(parents=True, exist_ok=True)
    for name in STALE:
        (spec.out_dir / name).unlink(missing_ok=True)
    shutil.rmtree(spec.out_dir / "checkpoint", ignore_errors=True)
    write_status(
        spec.out_dir, replace=True, state="queued", index=spec.index, budget=spec.budget
    )


# --------------------------------------------------------------------------------------
# work: the loop that keeps the jobs going
# --------------------------------------------------------------------------------------
def work(exp_dir: str | Path) -> None:
    """The worker: run the queued runs, ``max_parallel`` at a time, until none is
    queued or running. Reads everything from ``experiment.json`` and the status
    files, so it can be started again at any time."""
    exp_dir = Path(exp_dir).resolve()
    experiment = Experiment.load(exp_dir / "experiment.json")
    specs = experiment.expand(exp_dir)
    _write_json(exp_dir / "worker.json", _self_process() | {"started": _now()})
    children: dict[str, subprocess.Popen] = {}
    print(f"[{_now()}] worker for {experiment.name}: {len(specs)} runs", flush=True)
    while True:
        states = {s.name: registry.current_state(s.out_dir) for s in specs}
        for name, process in list(children.items()):
            if process.poll() is not None:  # reaped; its status file says the rest
                del children[name]
        live = sum(state == "running" for state in states.values())
        queued = [s for s in specs if states[s.name] == "queued"]
        if not queued and not live:
            break
        for spec in queued[: max(0, experiment.max_parallel - live)]:
            children[spec.name] = _start_job(spec)
            print(f"[{_now()}] started {spec.name}", flush=True)
            time.sleep(STAGGER_S)
        time.sleep(POLL_S)
    print(f"[{_now()}] worker done", flush=True)


def _start_job(spec: RunSpec) -> subprocess.Popen:
    env = os.environ | {"PYTHONPATH": str(REPO), "PYTHONUNBUFFERED": "1"}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with open(spec.out_dir / "log.txt", "wb") as log:
        process = subprocess.Popen(
            [PYTHON, "-m", "core.runner", "job", str(spec.out_dir)],
            cwd=REPO,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=flags,
        )
    # Running from now on, so the next poll counts it even before the job starts.
    write_status(
        spec.out_dir,
        state="running",
        pid=process.pid,
        create_time=psutil.Process(process.pid).create_time(),
        started=_now(),
    )
    return process


# --------------------------------------------------------------------------------------
# job: train one run, then evaluate it on the test days
# --------------------------------------------------------------------------------------
def job(run_dir: str | Path) -> None:
    """Train one run in this process and write ``heldout.csv`` and the status."""
    import logging
    import warnings

    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)  # Ray and RLlib are noisy
    run_dir = Path(run_dir).resolve()
    started = time.time()
    try:
        experiment = Experiment.load(run_dir.parent / "experiment.json")
        spec = next(
            s for s in experiment.expand(run_dir.parent) if s.name == run_dir.name
        )
        import torch

        torch.set_num_threads(experiment.torch_threads)
        write_status(run_dir, state="running", started=_now(), **_self_process())
        from core.rl import train

        run = spec.run()
        train(run)
        if experiment.test_days and experiment.is_market:
            _heldout(experiment, run, run_dir)
        write_status(
            run_dir,
            state="completed",
            finished=_now(),
            duration_s=round(time.time() - started, 1),
        )
    except BaseException as error:  # also KeyboardInterrupt / SystemExit
        traceback.print_exc()
        write_status(
            run_dir,
            state="failed",
            finished=_now(),
            duration_s=round(time.time() - started, 1),
            error=repr(error),
        )
        sys.exit(1)


def _heldout(experiment: Experiment, run, run_dir: Path) -> None:
    """The trained policy against the baselines on the test days -> heldout.csv."""
    from core.env import net_position_policy, zero_policy
    from core.rl import evaluate, load_policy

    config = experiment.heldout_config()
    env = run.env_class(config)
    policies = {
        "trained": load_policy(run_dir)[0],
        "zero": zero_policy(env),
        "net_position": net_position_policy(env),
    }
    frame = evaluate(run.env_class, config, policies, experiment.heldout_seed_list())
    frame.to_csv(run_dir / "heldout.csv", index=False)


# --------------------------------------------------------------------------------------
# stop
# --------------------------------------------------------------------------------------
def _kill_tree(pid: Optional[int], create_time: Optional[float]) -> bool:
    """Kill a process and everything it started (Ray's processes), after checking
    that the pid is still the process that was recorded."""
    if not registry.process_alive(pid, create_time):
        return False
    try:
        process = psutil.Process(int(pid))
        victims = process.children(recursive=True) + [process]
    except psutil.Error:
        return False
    for victim in victims:
        try:
            victim.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(victims, timeout=15)
    return True


def stop(
    experiment: str, run: Optional[str] = None, root: Optional[Path] = None
) -> dict:
    """Stop a whole experiment (worker, running jobs; queued runs become
    ``stopped``) or just one run.

    Returns:
        ``{"killed": [run names whose process was killed], "stopped": [run names
        now marked stopped]}``.
    """
    exp_dir = (Path(root) if root else runs_root()) / experiment
    if not exp_dir.is_dir():
        raise FileNotFoundError(f"no experiment '{experiment}' in {exp_dir.parent}")
    if run is None:  # the worker first, or it would start the next queued run
        info = registry.worker_info(exp_dir) or {}
        _kill_tree_worker(info)
    names = [run] if run else [p.name for p in exp_dir.iterdir() if p.is_dir()]
    killed, stopped = [], []
    for name in names:
        run_dir = exp_dir / name
        status = registry.read_json(run_dir / "status.json")
        if status is None:
            if run:
                raise FileNotFoundError(f"no run '{run}' in experiment '{experiment}'")
            continue
        state = status.get("state")
        if state == "running":
            if _kill_tree(status.get("pid"), status.get("create_time")):
                killed.append(name)
        elif state != "queued":
            continue
        write_status(run_dir, state="stopped", finished=_now())
        stopped.append(name)
    return {"killed": killed, "stopped": stopped}


def _kill_tree_worker(info: dict) -> None:
    # Not the job processes below it: those are found through the status files.
    if registry.process_alive(info.get("pid"), info.get("create_time")):
        try:
            psutil.Process(int(info["pid"])).kill()
        except psutil.Error:
            pass
