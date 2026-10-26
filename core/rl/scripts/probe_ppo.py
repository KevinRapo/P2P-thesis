"""Train PPO on the probes in every paradigm and check each network against the
exact answer (``probe_check.py``, next to this file), as one command. Run it first after any
change to ``core/rl/``.

From the repository root::

    python core/rl/scripts/probe_ppo.py                     # probes 1-10, CTCE, CTDE, DTDE
    python core/rl/scripts/probe_ppo.py --probes 7 8a 8b 9 --workers 12
    python core/rl/scripts/probe_ppo.py --probes 4 5 6 --budget-scale 2   # twice the steps
    python core/rl/scripts/probe_ppo.py --escalate 2 4      # failures again at x2, then x4
    python core/rl/scripts/probe_ppo.py --preset fast:A fast:B  # both in one pool
    python core/rl/scripts/probe_ppo.py --preset paper:S --count       # runs in the list
    python core/rl/scripts/probe_ppo.py --preset paper:S --index 7     # train run 7 only

``--index`` trains one run of the list (presets × seeds × probes × paradigms) and
scores nothing: one SLURM array task per run, each released as soon as its run
ends (``hpc/probes.slurm``). Afterwards the same command without ``--index`` finds
the runs finished and only scores them.

Probes 1-5 have a ``Box`` action, 6-9 the market's kind of mixed action, 10 the
market's 24-step day (``core/rl/envs/probes.py``); 8 runs as 8a (coordination,
judged) and 8b (the stag hunt, measured: no pass or fail). Runs go to
``runs/probes_<preset>/``; finished runs are scored, not trained again
(``--retrain`` trains them again). Prints one line per run, then the table, and
writes ``summary.csv`` next to the runs. The exit code is 1 if any check fails
(after ``--escalate``: if any combination never passed).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # core/rl/scripts -> root
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONHASHSEED", "0")

from core.rl.scripts import probe_check  # noqa: E402


def report(args, preset: str) -> bool:
    """Score one preset's runs (training those not finished), print its failures and
    table, escalate if asked. True when something failed."""
    summary, frames = probe_check.check(
        args.probes,
        args.paradigms,
        preset,
        args.seed,
        args.budget_scale,
        args.workers,
        args.retrain,
    )

    for (probe, paradigm), frame in frames.items():
        if not frame.ok.all() and not probe_check.PROBES[probe].measured:
            print(f"\n{probe_check.PROBES[probe].name} {paradigm.upper()} failed:")
            print(frame[~frame.ok].to_string(index=False))

    out = probe_check.runs_dir(preset)
    out.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.budget_scale == 1.0 else f"_x{args.budget_scale:g}"
    suffix += f"_s{args.seed}" if args.seed else ""  # one file per seed
    summary.to_csv(out / f"summary{suffix}.csv", index=False)
    print(f"\n=== {preset}")
    print(probe_check.table(summary))
    failed = bool((~summary.result.isin(["PASS", "MEASURED"])).any())

    if args.escalate and failed:
        passed = probe_check.escalate(
            summary, args.escalate, preset, args.seed, args.workers
        )
        passed.to_csv(out / "escalated.csv", index=False)
        print()
        print(passed.to_string(index=False))
        failed = bool(passed["passed at"].isna().any())

    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--probes", nargs="+", default=list(probe_check.PROBES))
    parser.add_argument("--paradigms", nargs="+", default=probe_check.PARADIGMS)
    parser.add_argument(
        "--preset",
        nargs="+",
        default=["fast"],
        help="fast, thorough, or with a variant (fast:A); several share one pool",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--budget-scale", type=float, default=1.0)
    parser.add_argument("--escalate", type=float, nargs="*", default=None)
    parser.add_argument("--retrain", action="store_true")
    parser.add_argument(
        "--seeds", type=int, nargs="+", default=None, help="several seeds (with --index)"
    )
    parser.add_argument(
        "--index",
        type=int,
        default=None,
        help="train only run number INDEX of the list (--count), e.g. one SLURM "
        "array task; nothing is scored",
    )
    parser.add_argument("--count", action="store_true", help="print the number of runs")
    args = parser.parse_args()

    if args.index is not None or args.count:
        runs = [
            probe_check.make_run(paradigm, probe, preset, seed, args.budget_scale)
            for preset in args.preset
            for seed in (args.seeds or [args.seed])
            for probe in args.probes
            for paradigm in args.paradigms
        ]
        if args.count:
            print(len(runs))
            return 0
        run = runs[args.index]
        print(f"run {args.index} of {len(runs)}: {run.out_dir}", flush=True)
        probe_check.train_runs([run], workers=1, retrain=args.retrain)

        # A failed run is an error of the task, so SLURM shows it (and a scoring
        # job submitted with afterok does not start).
        return 0 if probe_check.status(run) == "completed" else 1

    if len(args.preset) > 1:
        # Every preset's runs in one pool, so the workers stay busy until the last
        # run instead of waiting at the end of each preset; scored below.
        workers, _ = probe_check.parallel_setup(args.workers)
        runs = [
            probe_check.make_run(paradigm, probe, preset, args.seed, args.budget_scale)
            for preset in args.preset
            for probe in args.probes
            for paradigm in args.paradigms
        ]
        probe_check.train_runs(runs, workers, args.retrain)
        args.retrain = False

    failed = [report(args, preset) for preset in args.preset]

    return 1 if any(failed) else 0


if __name__ == "__main__":
    sys.exit(main())
