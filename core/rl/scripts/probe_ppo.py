"""Train PPO on the probes in every paradigm and check each network against the
exact answer: the procedure of ``notebooks/rl/probe_paradigms.ipynb``, PPO only,
as one command (run it first after any change to ``core/rl/``).

From the repository root::

    python core/rl/scripts/probe_ppo.py                 # probes 1-6, CTCE, CTDE, DTDE
    python core/rl/scripts/probe_ppo.py --probes 6 --workers 3
    python core/rl/scripts/probe_ppo.py --probes 4 5 6 --budget-scale 2   # twice the steps

Probes 1-5 are the Box probes; probe 6 (``MixedActionProbe``) has a categorical
and a continuous action part with known optima. Each run trains with the fast
preset (2 x 64 network, learning rate 1e-3) for the probe's budget, then the
trained policy (``load_policy``, as a finished run is used) is queried in the
probe's check states:

- values: per agent in DTDE and CTDE, the group's sum in CTCE, within
  ``TOLERANCE`` · max(1, |expected|);
- actions: the continuous mean within ``TOLERANCE``; a categorical part must be
  the expected category exactly.

Runs go to ``runs/probes_ppo/``; finished runs are scored, not trained again
(``--retrain`` trains them again). One line per run, then a table, and
``runs/probes_ppo/summary.csv``. The exit code is 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # core/rl/scripts -> root
sys.path.insert(0, str(ROOT))
os.environ["PYTHONPATH"] = os.pathsep.join(
    filter(None, [str(ROOT), os.environ.get("PYTHONPATH", "")])
)
os.environ.setdefault("PYTHONHASHSEED", "0")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from core.rl import Run, load_policy, train  # noqa: E402
from core.rl.envs.probes import (  # noqa: E402
    ActionProbe,
    ConstantProbe,
    DiscountProbe,
    MixedActionProbe,
    ObsActionProbe,
    ObservationProbe,
)
from core.rl.ctce import GROUP  # noqa: E402

PARADIGMS = ["ctce", "ctde", "dtde"]
TOLERANCE = 0.15
MODEL = {"fcnet_hiddens": [64, 64]}
TRAINING = {
    "lr": 1e-3,
    "train_batch_size_per_learner": 500,
    "minibatch_size": 64,
    "num_epochs": 10,
}
# number: (name, environment, discount, scrambled agent ids, budget)
PROBES = {
    1: ("Constant", ConstantProbe, 0.99, False, 3_000),
    2: ("Observation", ObservationProbe, 0.99, False, 3_000),
    3: ("Discount", DiscountProbe, 0.5, False, 3_000),
    4: ("Action", ActionProbe, 0.99, True, 8_000),
    5: ("Obs -> action", ObsActionProbe, 0.99, True, 15_000),
    6: ("Mixed action", MixedActionProbe, 0.99, True, 10_000),
}
RUNS_DIR = ROOT / "runs" / "probes_ppo"


def make_run(paradigm: str, probe: int, seed: int, scale: float = 1.0) -> Run:
    _, env_class, gamma, scramble, budget = PROBES[probe]
    suffix = "" if scale == 1.0 else f"_x{scale:g}"
    return Run(
        "ppo",
        paradigm,
        env_class,
        {"n_agents": 3, "scramble_ids": scramble},
        budget=int(budget * scale),
        seed=seed,
        eval_episodes=5,
        training=TRAINING | {"gamma": gamma},
        model=MODEL,
        out_dir=RUNS_DIR / f"ppo_{paradigm}_p{probe}_s{seed}{suffix}",
    )


def status(run: Run) -> str:
    """The run's status; a run whose process died (left "running") counts as not
    run, so it is trained again."""
    path = Path(run.out_dir) / "run.json"
    if not path.exists():
        return "not run"
    found = json.loads(path.read_text(encoding="utf-8"))["status"]
    return "not run" if found == "running" else found


def score(run: Run, probe: int) -> pd.DataFrame:
    """One row per checked output: expected, got, tolerance, ok."""
    _, env_class, gamma, _, _ = PROBES[probe]
    policy, _ = load_policy(run.out_dir)
    env = env_class(run.env_config)
    rows = []
    for check in env.checks(gamma):
        if check.value is not None:
            got = policy.values(check.obs)
            expected = (
                dict(check.value)
                if run.paradigm != "ctce"
                else {GROUP: sum(check.value.values())}
            )
            for mid, value in expected.items():
                rows.append(
                    (
                        check.name,
                        f"value {mid}",
                        value,
                        got[mid],
                        TOLERANCE * max(1.0, abs(value)),
                    )
                )
        if check.action is not None:
            got = policy.act(check.obs)
            for agent, value in check.action.items():
                if isinstance(value, dict):  # a mixed action, part by part
                    for part, want in value.items():
                        have = np.asarray(got[agent][part]).reshape(-1)[0]
                        exact = isinstance(want, int)
                        rows.append(
                            (
                                check.name,
                                f"action {agent} {part}",
                                float(want),
                                float(have),
                                0.0 if exact else TOLERANCE,
                            )
                        )
                else:
                    rows.append(
                        (
                            check.name,
                            f"action {agent}",
                            value,
                            float(np.asarray(got[agent]).reshape(-1)[0]),
                            TOLERANCE,
                        )
                    )
    frame = pd.DataFrame(
        rows, columns=["state", "output", "expected", "got", "tolerance"]
    )
    frame["error"] = (frame.got - frame.expected).abs()
    frame["ok"] = frame.error <= frame.tolerance + 1e-9
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--probes", type=int, nargs="+", default=list(PROBES))
    parser.add_argument("--paradigms", nargs="+", default=PARADIGMS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2)
    )
    parser.add_argument("--budget-scale", type=float, default=1.0)
    parser.add_argument("--retrain", action="store_true")
    args = parser.parse_args()

    runs = [
        (probe, make_run(paradigm, probe, args.seed, args.budget_scale))
        for probe in args.probes
        for paradigm in args.paradigms
    ]
    if args.retrain:
        for _, run in runs:
            shutil.rmtree(run.out_dir, ignore_errors=True)
    pending = [run for _, run in runs if status(run) != "completed"]
    start = time.time()
    if pending:
        with ProcessPoolExecutor(max_workers=min(args.workers, len(pending))) as pool:
            futures = {pool.submit(train, run): run for run in pending}
            for future in as_completed(futures):
                run = futures[future]
                try:
                    note = f"trained in {future.result()['duration_s']:.0f} s"
                except Exception as error:  # report and go on with the others
                    note = f"FAILED: {error!r}"[:200]
                print(f"{Path(run.out_dir).name:22s} {note}", flush=True)
        print(f"{len(pending)} runs trained in {time.time() - start:.0f} s")

    summary, failed = [], False
    for probe, run in runs:
        name = PROBES[probe][0]
        if status(run) != "completed":
            summary.append((probe, name, run.paradigm, "NOT RUN", float("nan")))
            failed = True
            continue
        frame = score(run, probe)
        worst = float((frame.error / frame.tolerance.clip(lower=1e-9)).max())
        ok = bool(frame.ok.all())
        failed |= not ok
        summary.append((probe, name, run.paradigm, "PASS" if ok else "FAIL", worst))
        if not ok:
            print(f"\n{name} {run.paradigm.upper()} failed:")
            print(frame[~frame.ok].to_string(index=False))
    table = pd.DataFrame(
        summary,
        columns=["probe", "name", "paradigm", "result", "worst error / tolerance"],
    )
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.budget_scale == 1.0 else f"_x{args.budget_scale:g}"
    table.to_csv(RUNS_DIR / f"summary{suffix}.csv", index=False)
    print()
    print(table.pivot(index=["probe", "name"], columns="paradigm", values="result"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
