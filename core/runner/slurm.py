"""Run an experiment on a SLURM cluster: one array task per run, through submitit.

Call it where ``sbatch`` and ``sacct`` exist: a cluster's login node, or inside a
job. Every task of the job array calls ``launch.job(run_dir)``, the same function a
local worker's job process runs, so a run means the same on both: it trains, evaluates
on the test days and writes its ``status.json``. Only the process around it differs:
SLURM starts, limits and ends it instead of a worker.

What it adds next to the usual files (see ``launch.py``):

    runs/<experiment>/slurm/             submitit's: batch script, pickles, task logs
    runs/<experiment>/slurm.json         array_id, submitted, partition, account,
                                         resources, tasks ({run name: task id})
    runs/<experiment>/<run>/status.json  gets ``slurm_job``: the task id (1042700_3)

``registry`` never calls SLURM: it receives the answer of ``states`` (one ``sacct``
call) and tells from it whether a run is alive.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Iterator, Optional

import submitit

from core.runner import launch, registry
from core.runner.spec import REPO, Experiment, SpecError, runs_root

SACCT_TIMEOUT_S = 30
TERMINAL = registry.SLURM_TERMINAL


# --------------------------------------------------------------------------------------
# Asking SLURM how the tasks are doing
# --------------------------------------------------------------------------------------
# A job id as `sacct -X` prints it: one task (1042700_3), the tasks still pending, as
# a range with an optional step and throttle (1042700_[4-9%3], 1042700_[1,3-5:2]),
# or a plain job (1042700: submitit submits an array of one run as a single job).
_TASK = re.compile(r"^(\d+)(?:_(?:(\d+)|\[([\d,:-]+)(?:%\d+)?\]))?$")


def _indices(spec: str) -> Iterator[int]:
    """The task numbers in ``4-9``, ``1,3-5`` or ``0-10:5``."""
    for part in spec.split(","):
        part, _, step = part.partition(":")
        first, _, last = part.partition("-")
        yield from range(int(first), int(last or first) + 1, int(step or 1))


def parse_sacct(text: str) -> dict[str, dict]:
    """The tasks in the output of ``sacct -n -P -X -o JobID,State,NodeList``.

    Returns:
        ``{task id: {"state": first word of the state, "node": node name or
        None}}``; a pending range such as ``1042700_[4-9%3]`` is one entry per task.
    """
    tasks: dict[str, dict] = {}
    for line in text.splitlines():
        fields = line.strip().split("|")
        match = _TASK.match(fields[0]) if len(fields) >= 3 else None
        if not match or not fields[1].split():
            continue
        node = fields[2].strip()
        info = {
            "state": fields[1].split()[0].rstrip("+"),
            "node": None if node in ("", "None assigned") else node,
        }
        array_id, one, many = match.groups()
        if one is None and many is None:  # a plain job
            tasks[array_id] = info
            continue
        for index in _indices(one or many):
            tasks[f"{array_id}_{index}"] = dict(info)
    return tasks


def states(exp_dir: Path) -> dict[str, dict]:
    """How SLURM sees the tasks of the experiment's job array: one ``sacct`` call.

    Returns:
        ``{task id: {"state", "node"}}`` (see ``parse_sacct``), or ``{}`` when the
        experiment was never submitted or ``sacct`` is missing or fails.
    """
    info = registry.read_json(Path(exp_dir) / "slurm.json")
    if not info or not info.get("array_id"):
        return {}
    command = ["sacct", "-j", str(info["array_id"])]
    command += ["-n", "-P", "-X", "-o", "JobID,State,NodeList"]
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=SACCT_TIMEOUT_S
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_sacct(done.stdout) if done.returncode == 0 else {}


# --------------------------------------------------------------------------------------
# start: one job array for the runs that need to run
# --------------------------------------------------------------------------------------
def choose_partition(partitions: list[dict], minutes: int) -> dict:
    """The first partition (``{"name", "max_minutes"}``) that allows ``minutes``."""
    for partition in partitions:
        if partition["max_minutes"] >= minutes:
            return partition
    longest = max((p["max_minutes"] for p in partitions), default=0)
    raise SpecError(
        f"no partition allows {minutes} minutes per run (the longest allows "
        f"{longest}); lower 'resources.minutes' in the experiment"
    )


def start(
    spec_path: str | Path,
    *,
    account: str,
    partitions: list[dict],
    root: Optional[Path] = None,
    profile: str = "full",
) -> Path:
    """Queue an experiment and submit its runs as one job array; returns at once.

    Like ``launch.start`` it resumes: completed runs stay, the others are queued
    again from scratch and submitted. Refuses while the previous array of the
    experiment still has tasks queued or running.

    Args:
        spec_path: The experiment file.
        account: The SLURM account to charge.
        partitions: ``[{"name", "max_minutes"}, ...]`` in order of preference; the
            first that allows the runs' ``resources.minutes`` is used.
        root: The folder with the experiments (default: the runs root).
        profile: ``"full"`` or ``"test"`` (``Experiment.test_version``).

    Returns:
        The experiment's folder.
    """
    experiment = Experiment.load(spec_path).with_profile(profile)
    exp_dir = (Path(root) if root else runs_root()) / experiment.name
    resources = experiment.run_resources
    partition = choose_partition(partitions, resources["minutes"])
    if shutil.which("sbatch") is None:
        raise RuntimeError(
            "sbatch not found: run this on the cluster (its login node), or use a "
            "target that drives the cluster from here"
        )
    tasks = _refuse_while_alive(experiment.name, exp_dir)
    specs = launch.prepare(experiment, exp_dir, slurm=tasks)
    queued = [s for s in specs if registry.current_state(s.out_dir) == "queued"]
    if not queued:  # every run is completed or running
        return exp_dir
    executor = submitit.AutoExecutor(folder=exp_dir / "slurm", cluster="slurm")
    executor.update_parameters(
        name=f"marlem-{experiment.name}",
        timeout_min=int(resources["minutes"]),
        cpus_per_task=int(resources["cpus"]),
        mem_gb=resources["mem_gb"],
        slurm_partition=partition["name"],
        slurm_account=account,
        slurm_array_parallelism=experiment.max_parallel,
        slurm_setup=[
            f"export PYTHONPATH={shlex.quote(str(REPO))}",
            *(f"export {key}={value}" for key, value in launch.JOB_ENV.items()),
        ],
    )
    jobs = executor.map_array(launch.job, [str(s.out_dir) for s in queued])
    launch.write_json(
        exp_dir / "slurm.json",
        {
            "array_id": jobs[0].job_id.split("_")[0],
            "submitted": launch.now(),
            "partition": partition["name"],
            "account": account,
            "resources": dict(resources),
            "tasks": {s.name: job.job_id for s, job in zip(queued, jobs)},
        },
    )
    for spec, job in zip(queued, jobs):
        launch.write_status(spec.out_dir, slurm_job=job.job_id)
    return exp_dir


def _refuse_while_alive(name: str, exp_dir: Path) -> dict[str, dict]:
    """The SLURM states of the experiment's earlier array, if no task of it is still
    queued or running (``RuntimeError`` otherwise, so nothing runs twice)."""
    info = registry.read_json(exp_dir / "slurm.json")
    if info is None:  # never submitted
        return {}
    tasks = states(exp_dir)
    if not tasks:
        raise RuntimeError(
            f"cannot tell whether SLURM job {info.get('array_id')} of experiment "
            f"'{name}' is still running (sacct gave no answer); once it is not, "
            f"remove {exp_dir / 'slurm.json'} and start again"
        )
    alive = [t for t, found in tasks.items() if found["state"] not in TERMINAL]
    if alive:
        raise RuntimeError(
            f"experiment '{name}' still has {len(alive)} task(s) queued or running on "
            f"SLURM (job {info['array_id']}); stop it first with "
            f"`python -m core.runner stop {name}` (and the same --target)"
        )
    return tasks


# --------------------------------------------------------------------------------------
# stop
# --------------------------------------------------------------------------------------
def stop(
    experiment: str, run: Optional[str] = None, root: Optional[Path] = None
) -> dict:
    """Cancel a whole experiment's job array (or just one run's task), then mark its
    queued and running runs ``stopped``.

    ``scancel`` must succeed first: if it fails, ``RuntimeError`` carries its message
    and no run is marked, so a task SLURM still runs never shows as stopped.

    Returns:
        ``{"cancelled": [job or task ids passed to scancel], "stopped": [run names
        now marked stopped]}``.
    """
    exp_dir = launch.experiment_dir(experiment, root)
    if run is None:
        info = registry.read_json(exp_dir / "slurm.json") or {}
        ids = [str(info["array_id"])] if info.get("array_id") else []
    else:
        status = registry.read_json(exp_dir / run / "status.json") or {}
        ids = [str(status["slurm_job"])] if status.get("slurm_job") else []
    if ids:
        done = subprocess.run(["scancel", *ids], capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(
                f"scancel {' '.join(ids)} failed (exit status {done.returncode}): "
                f"{done.stderr.strip() or 'no message'}; nothing was marked stopped"
            )
    stopped = launch.mark_stopped(exp_dir, run, kill=False)["stopped"]
    return {"cancelled": ids, "stopped": stopped}
