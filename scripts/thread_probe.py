"""How many threads one training run holds, and how that depends on the run.

TalTech allows 4096 threads per user per node (docs/hpc/resources.md), so the threads
of one run decide how many runs share a node. Each case trains one short run as the
runner does (``core.rl.train`` in its own process and Ray instance), from the test
profile of ``experiments/market_3x3.json`` with one setting changed, and samples the
threads of that process tree every second. A thread counts as "working" when it used
more than 1 s of CPU.

On a compute node, from the ``marlem-v2`` root::

    sbatch -p short -c 8 --mem=16G -t 120 --constraint=skylake \
        --wrap "python scripts/thread_probe.py --group k"

Groups: ``all``, ``k``, ``algorithm``, ``paradigm``, ``agents``, ``long``. One line per
case goes to standard output and to ``runs/thread_probe/<group>-<job>.csv``.
"""

from __future__ import annotations

import argparse
import copy
import csv
import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path

import psutil

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # run as a script from the repository root

from core.runner.launch import RAY_THREAD_CAPS  # noqa: E402

TICK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100  # Linux only

# Ray's thread pools at one thread each, as the runner sets them.
CAPS = RAY_THREAD_CAPS

BASE = {
    "algorithm": "ppo",
    "paradigm": "dtde",
    "runners": 3,
    "agents": 5,
    "capped": True,
    "budget": None,
}
GROUPS = {
    "k": [
        {"runners": 0, "capped": False},
        {"runners": 3, "capped": False},
        {"runners": 0},
        {"runners": 1},
        {"runners": 3},
        {"runners": 6},
    ],
    "algorithm": [{"algorithm": "appo"}, {"algorithm": "sac"}],
    "paradigm": [{"paradigm": "ctce"}, {"paradigm": "ctde"}],
    "agents": [{"agents": 13}, {"agents": 40}],
    "long": [{"algorithm": "sac", "budget": 3000}],
}
GROUPS["all"] = [case for cases in GROUPS.values() for case in cases]

# The networks for more participants: one participant per bus with a load, owning
# every load and generator at that bus.
NETWORKS = {13: "1-LV-rural1--0-sw", 40: "1-LV-urban6--0-sw"}


# --------------------------------------------------------------------------------------
# One run (the child process)
# --------------------------------------------------------------------------------------
def scenario(agents: int, template: dict) -> dict:
    """The template scenario, or the same settings on a larger network."""
    if agents == len(template["participants"]):
        return template
    from core.grid.contract import NetworkRef
    from core.grid.simbench import elements

    code = NETWORKS[agents]
    owned = defaultdict(list)
    for element in elements(NetworkRef("simbench", code)):
        if element.element_type in ("load", "sgen"):
            owned[element.bus].append(element)
    buses = [
        b for b, found in owned.items() if any(e.element_type == "load" for e in found)
    ]
    participants = [
        {
            "id": f"P{i + 1}",
            "bus": bus,
            "owns": [e.id for e in owned[bus]],
            "battery": None,
        }
        for i, bus in enumerate(buses[:agents])
    ]
    if len(participants) < agents:
        raise SystemExit(f"{code} has {len(participants)} load buses, not {agents}")
    found = copy.deepcopy(template)
    found["grid"]["code"] = code
    found["participants"] = participants
    return found


def train_one(case: dict, out: str) -> None:
    import logging
    import warnings

    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    import torch

    torch.set_num_threads(1)
    from core.rl import train
    from core.runner.spec import Experiment

    experiment = Experiment.load(REPO / "experiments" / "market_3x3.json")
    experiment = experiment.with_profile("test")
    template = json.loads(experiment.scenario_path.read_text(encoding="utf-8"))
    changes = {
        "algorithms": [case["algorithm"]],
        "paradigms": [case["paradigm"]],
        "num_env_runners": case["runners"],
        "scenario": scenario(case["agents"], template),
    }
    if case["budget"]:
        changes["budget"] = case["budget"]
    experiment = dataclasses.replace(experiment, **changes)
    path = experiment.scenario_file(Path(out))  # where the runs read it
    path.write_text(json.dumps(changes["scenario"]), encoding="utf-8")
    (spec,) = experiment.expand(Path(out))
    train(spec.run())


# --------------------------------------------------------------------------------------
# Measuring (the parent process)
# --------------------------------------------------------------------------------------
def threads(root: psutil.Process) -> dict:
    """``{tid: (name, cpu seconds)}`` of ``root`` and every process below it."""
    try:
        processes = [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        return {}
    found = {}
    for process in processes:
        try:
            for tid in os.listdir(f"/proc/{process.pid}/task"):
                with open(f"/proc/{process.pid}/task/{tid}/stat") as f:
                    stat = f.read()
                name = stat[stat.index("(") + 1 : stat.rindex(")")]
                fields = stat[stat.rindex(")") + 2 :].split()
                found[tid] = (name, (int(fields[11]) + int(fields[12])) / TICK)
        except (FileNotFoundError, ProcessLookupError, ValueError):
            continue
    return found


def measure(case: dict) -> dict:
    out = tempfile.mkdtemp()
    env = os.environ | {"PYTHONPATH": str(REPO)} | (CAPS if case["capped"] else {})
    child = subprocess.Popen(
        [sys.executable, __file__, "--child", json.dumps(case), out],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    root = psutil.Process(child.pid)
    counts, seen = [], {}

    def watch() -> None:
        while child.poll() is None:
            now = threads(root)
            if now:
                counts.append(len(now))
                seen.update(now)
            time.sleep(1.0)

    watcher = threading.Thread(target=watch)
    watcher.start()
    _, error = child.communicate()
    watcher.join()
    by_name = defaultdict(int)
    for name, _ in seen.values():
        by_name[name] += 1
    working = sorted((cpu, name) for name, cpu in seen.values() if cpu > 1.0)[::-1]
    record = {}
    for path in Path(out).rglob("run.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
    timings = record.get("timings", {})
    steps = record.get("env_steps") or record.get("steps")
    train_s = timings.get("train_calls_s")
    return case | {
        "exit": child.returncode,
        "peak": max(counts, default=0),
        "median": sorted(counts)[len(counts) // 2] if counts else 0,
        "last": counts[-1] if counts else 0,
        "working": len(working),
        "cpu_s": round(sum(cpu for _, cpu in seen.values())),
        "steps": steps,
        "train_s": round(train_s, 1) if train_s else None,
        "steps_per_s": round(steps / train_s, 1) if steps and train_s else None,
        "ray_init_s": round(timings.get("ray_init_s", 0), 1),
        "most": " ".join(
            f"{n}={c}" for n, c in sorted(by_name.items(), key=lambda kv: -kv[1])[:6]
        ),
        "busiest": " ".join(f"{n}:{cpu:.0f}s" for cpu, n in working[:5]),
        "error": (
            (error or "").strip().splitlines()[-1][:200] if child.returncode else ""
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--group", default="all", choices=sorted(GROUPS))
    parser.add_argument("--child", nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        train_one(json.loads(args.child[0]), args.child[1])
        return
    job = os.environ.get("SLURM_JOB_ID", "local")
    out = REPO / "runs" / "thread_probe" / f"{args.group}-{job}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"node {os.uname().nodename}, {os.cpu_count()} hardware threads, "
        f"{len(os.sched_getaffinity(0))} allocated",
        flush=True,
    )
    rows = []
    for case in GROUPS[args.group]:
        row = measure(BASE | case)
        rows.append(row)
        print(json.dumps(row), flush=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
