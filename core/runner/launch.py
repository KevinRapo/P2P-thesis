"""Start, run and stop experiments as detached processes.

``start`` writes the experiment's folder (``prepare``) and spawns one detached
*worker* that outlives the terminal, the Studio and the Claude session. The worker
keeps up to ``max_parallel`` *job* processes running, one per run; a job trains a
run and evaluates it on the test days. ``slurm.py`` reuses ``prepare`` and ``job``
to run the same runs as a SLURM job array. State lives in files only (see
``registry.py``):

    runs/<experiment>/experiment.json    the spec, as ``Experiment.to_dict`` writes it,
                                         with the scenario in it (``spec.resolve``)
    runs/<experiment>/scenario.json      the scenario the runs read
    runs/<experiment>/worker.json        worker pid and start time
    runs/<experiment>/worker.log         the worker's output
    runs/<experiment>/<run>/status.json  queued -> running -> completed | failed
    runs/<experiment>/<run>/log.txt      the job's output
    runs/<experiment>/<run>/heldout.csv  trained policy and baselines on test days
    runs/<experiment>/<run>/heldout_agents.csv, heldout_episodes.csv
                                         the same per test day and participant, and
                                         per test day (``core/rl/policy.py``)
    runs/<experiment>/<run>/heldout_trace_agents.csv, heldout_trace_steps.csv
                                         with ``results_detail`` "detailed": the
                                         traced test days step by step

Jobs are not killed when the worker dies: they run on to the end and write their
own status, but nothing starts the queued runs behind them until ``start`` is run
again, which skips completed (and still running) runs and re-queues the rest.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil

from core.files import write_json
from core.runner import registry
from core.runner.spec import (
    REPO,
    SCENARIO_FILE,
    Experiment,
    RunSpec,
    SpecError,
    resolve,
    runs_root,
)

POLL_S = 5.0
# Gap between two job starts: Ray's start-up fails more often when several nodes
# start at once on a busy machine.
STAGGER_S = 10.0
PYTHON = sys.executable
# Files a re-queued run must not keep from its earlier attempt.
STALE = (
    "run.json",
    "metrics.csv",
    "evaluation.csv",
    "evaluation_agents.csv",
    "evaluation_episodes.csv",
    "heldout.csv",
    "heldout_agents.csv",
    "heldout_episodes.csv",
    "heldout_trace_agents.csv",
    "heldout_trace_steps.csv",
    "log.txt",
)
# Python orders sets of strings differently in every process unless its hash seed
# is fixed, and RLlib keeps agent ids in sets: without this, the same run seed gives
# a different multi-agent run each time (tests/rl/test_7_same_seed_same_run.py).
JOB_ENV = {"PYTHONHASHSEED": "0", "PYTHONUNBUFFERED": "1"}
# Ray sizes several thread pools in each of its processes by the machine's hardware
# threads (80 on a TalTech green node), and TalTech allows 4096 threads per user per
# node: these set them to one thread each, about 165 + 24 per sampler threads a run
# instead of 480 + 75, without slowing training (docs/hpc/resources.md, threads per
# run). Ray reads them in every process it starts; a job sets them before ray.init
# when its experiment's ``ray_thread_caps`` is true.
RAY_THREAD_CAPS = {
    "RAY_num_server_call_thread": "1",
    "RAY_worker_num_grpc_internal_threads": "1",
    "RAY_num_grpc_internal_threads": "1",
    "RAY_gcs_server_rpc_server_thread_num": "1",
    "RAY_gcs_server_rpc_client_thread_num": "1",
    "RAY_object_manager_rpc_threads_num": "1",
    "RAY_enable_metrics_collection": "0",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
}


def job_environment() -> dict[str, str]:
    """The environment of a runner process: this one's, with the repository on
    ``PYTHONPATH`` and ``JOB_ENV``."""
    return os.environ | {"PYTHONPATH": str(REPO)} | JOB_ENV


# --------------------------------------------------------------------------------------
# Status files
# --------------------------------------------------------------------------------------
def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_status(run_dir: Path, replace: bool = False, **fields) -> dict:
    """Merge ``fields`` into the run's ``status.json`` (or replace it)."""
    run_dir = Path(run_dir)
    status = {} if replace else registry.read_json(run_dir / "status.json") or {}
    status |= fields | {"updated": now()}
    write_json(run_dir / "status.json", status)

    return status


def _self_process() -> dict:
    return {"pid": os.getpid(), "create_time": psutil.Process().create_time()}


# --------------------------------------------------------------------------------------
# start: the folder, the queue and the detached worker
# --------------------------------------------------------------------------------------
def _spawn_detached(args: list[str], log: Path) -> subprocess.Popen:
    """A process that keeps running after the caller (and its terminal) is gone."""
    env = job_environment()
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


def prepare(
    experiment: Experiment, exp_dir: Path, slurm: Optional[dict] = None
) -> list[RunSpec]:
    """Write the experiment's folder and queue its runs, without starting anything.

    An experiment folder keeps the spec it was started with: if ``experiment.json``
    exists and differs from ``experiment``, ``SpecError`` is raised before anything is
    written or reset. Otherwise ``experiment.json`` is written from the experiment,
    ``scenario.json`` from its scenario when the experiment holds it (``spec.resolve``),
    and every run that is not completed or running is reset to ``queued``. ``slurm`` is
    the SLURM state of each task (see ``registry``) for runs that were submitted to a
    cluster.

    Returns:
        One ``RunSpec`` per run of the grid, in order.
    """
    exp_dir = Path(exp_dir)
    _refuse_changed_spec(experiment, exp_dir)
    specs = experiment.expand(exp_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)
    write_json(exp_dir / "experiment.json", experiment.to_dict())

    if isinstance(experiment.scenario, dict):
        write_json(exp_dir / SCENARIO_FILE, experiment.scenario)

    for spec in specs:
        state = registry.current_state(spec.out_dir, slurm=slurm)
        if state not in ("completed", "running"):
            _reset(spec)

    return specs


def _refuse_changed_spec(experiment: Experiment, exp_dir: Path) -> None:
    """Runs of one folder must come from one spec, or the results would mix settings.
    The scenario is compared by its contents; a folder started before experiments
    held their scenario is compared with its scenario file as it is now. Changes to
    the code are not detected."""
    path = exp_dir / "experiment.json"

    if not path.exists():
        return

    try:  # a file that cannot be read back is refused like a changed one
        saved = Experiment.from_dict(
            registry.read_json(path), experiment.name, check_files=False
        ).inline_scenario()
        changed = saved.to_dict() != experiment.inline_scenario().to_dict()
    except SpecError:
        changed = True

    if changed:
        raise SpecError(
            f"the spec of '{experiment.name}' changed since it was started: "
            "start it under a new experiment name"
        )


def start(
    spec: str | Path | Experiment, root: Optional[Path] = None, profile: str = "full"
) -> Path:
    """Queue an experiment and start its worker; returns at once.

    Starting an experiment that already has runs resumes it: completed runs (and
    runs still alive) stay, failed, stopped and lost runs start again from scratch.
    The spec must be the one it was started with (see ``prepare``).

    Args:
        spec: The experiment file, or the ``Experiment`` itself (``spec.resolve``).
        root: The folder with the experiments (default: the runs root).
        profile: ``"full"``, or ``"test"`` for the experiment's test version
            (``Experiment.test_version``), which has a folder of its own.

    Returns:
        The experiment's folder.
    """
    experiment = resolve(spec, profile)
    exp_dir = (Path(root) if root else runs_root()) / experiment.name

    if registry.worker_alive(exp_dir):
        raise RuntimeError(
            f"experiment '{experiment.name}' already has a running worker "
            f"(pid {registry.worker_info(exp_dir)['pid']}); stop it first with "
            f"`python -m core.runner stop {experiment.name}`"
        )

    prepare(experiment, exp_dir)
    process = _spawn_detached(["work", str(exp_dir)], exp_dir / "worker.log")
    write_json(
        exp_dir / "worker.json",
        {
            "pid": process.pid,
            "create_time": psutil.Process(process.pid).create_time(),
            "started": now(),
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
    write_json(exp_dir / "worker.json", _self_process() | {"started": now()})
    children: dict[str, subprocess.Popen] = {}
    print(f"[{now()}] worker for {experiment.name}: {len(specs)} runs", flush=True)

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
            print(f"[{now()}] started {spec.name}", flush=True)
            time.sleep(STAGGER_S)

        time.sleep(POLL_S)

    print(f"[{now()}] worker done", flush=True)


def _start_job(spec: RunSpec) -> subprocess.Popen:
    env = job_environment()
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
        started=now(),
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

        if experiment.ray_thread_caps:  # before torch and Ray start their threads
            os.environ.update(RAY_THREAD_CAPS)

        import torch

        torch.set_num_threads(experiment.torch_threads)
        write_status(
            run_dir,
            state="running",
            started=now(),
            host=socket.gethostname(),
            **_self_process(),
        )
        from core.rl import train

        run = spec.run()
        train(run)

        if experiment.test_days and experiment.is_market:
            _heldout(experiment, run, run_dir, spec.variant)

        write_status(
            run_dir,
            state="completed",
            finished=now(),
            duration_s=round(time.time() - started, 1),
        )
    except BaseException as error:  # also KeyboardInterrupt / SystemExit
        traceback.print_exc()
        write_status(
            run_dir,
            state="failed",
            finished=now(),
            duration_s=round(time.time() - started, 1),
            error=repr(error),
        )
        sys.exit(1)


def heldout_env_config(
    experiment: Experiment, exp_dir: Path, variant: Optional[str], record: dict
) -> dict:
    """The environment config of a run's held-out evaluation: the test days
    (``Experiment.heldout_config``) with the energy and reward scales the run
    resolved on its training days (``record``, its run.json), never scales
    computed from the test days."""
    from core.env import SCALE_KEYS

    trained = record.get("env_config", {})
    config = experiment.heldout_config(exp_dir, variant)

    return config | {key: trained[key] for key in SCALE_KEYS if trained.get(key)}


def _heldout(
    experiment: Experiment, run, run_dir: Path, variant: Optional[str] = None
) -> None:
    """The trained policy against the baselines on every test day once ->
    ``heldout*.csv`` (see the module). The test days are played with the scales
    the run resolved on its training days (``run.json``), not ones computed from
    the test days, so observations and rewards mean what they meant in training."""
    from core.env import net_position_policy, zero_policy
    from core.rl import evaluation, load_policy

    policy, record = load_policy(run_dir)
    config = heldout_env_config(experiment, run_dir.parent, variant, record)
    env = run.env_class(config)
    policies = {
        "trained": policy,
        "zero": zero_policy(env),
        "net_position": net_position_policy(env),
    }
    episodes = experiment.heldout_episodes()
    traced = set(experiment.traced_days())
    found = evaluation(
        run.env_class,
        config,
        policies,
        [seed for seed, _ in episodes],
        options=[{"day": day} for _, day in episodes],
        trace=[i for i, (_, day) in enumerate(episodes) if day in traced],
    )

    for name, frame in (
        ("heldout", found.summary),
        ("heldout_agents", found.agents),
        ("heldout_episodes", found.episodes),
        ("heldout_trace_agents", found.trace_agents),
        ("heldout_trace_steps", found.trace_steps),
    ):
        if frame is not None:
            frame.to_csv(run_dir / f"{name}.csv", index=False)


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


def experiment_dir(experiment: str, root: Optional[Path] = None) -> Path:
    """The folder of an experiment that exists (``FileNotFoundError`` otherwise)."""
    exp_dir = (Path(root) if root else runs_root()) / experiment

    if not exp_dir.is_dir():
        raise FileNotFoundError(f"no experiment '{experiment}' in {exp_dir.parent}")

    return exp_dir


def mark_stopped(exp_dir: Path, run: Optional[str] = None, kill: bool = True) -> dict:
    """Mark the queued and running runs of an experiment (or just ``run``) as
    ``stopped``; completed, failed and stopped runs stay as they are.

    ``kill`` ends a running run's recorded process first (a run that left its
    process on another machine, e.g. a SLURM task, is cancelled by its backend).

    Returns:
        ``{"killed": [...], "stopped": [...]}``, run names.
    """
    exp_dir = Path(exp_dir)
    names = [run] if run else [p.name for p in exp_dir.iterdir() if p.is_dir()]
    killed, stopped = [], []

    for name in names:
        run_dir = exp_dir / name
        status = registry.read_json(run_dir / "status.json")

        if status is None:
            if run:
                raise FileNotFoundError(
                    f"no run '{run}' in experiment '{exp_dir.name}'"
                )
            continue

        state = status.get("state")

        if state == "running":
            if kill and _kill_tree(status.get("pid"), status.get("create_time")):
                killed.append(name)
        elif state != "queued":
            continue

        write_status(run_dir, state="stopped", finished=now())
        stopped.append(name)

    return {"killed": killed, "stopped": stopped}


def stop(
    experiment: str, run: Optional[str] = None, root: Optional[Path] = None
) -> dict:
    """Stop a whole experiment (worker, running jobs; queued runs become
    ``stopped``) or just one run.

    Returns:
        ``{"killed": [run names whose process was killed], "stopped": [run names
        now marked stopped]}``.
    """
    exp_dir = experiment_dir(experiment, root)

    if run is None:  # the worker first, or it would start the next queued run
        info = registry.worker_info(exp_dir) or {}
        _kill_tree_worker(info)

    return mark_stopped(exp_dir, run)


def _kill_tree_worker(info: dict) -> None:
    # Not the job processes below it: those are found through the status files.
    if registry.process_alive(info.get("pid"), info.get("create_time")):
        try:
            psutil.Process(int(info["pid"])).kill()
        except psutil.Error:
            pass
