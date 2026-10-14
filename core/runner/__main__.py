"""Command line of the runner: ``python -m core.runner <command>``.

start experiments/x.json   queue the runs and start a detached worker; returns
status [experiment]        one line per experiment, or the table of one
stop <experiment> [run]    kill the worker and jobs (or one run's job)
work <experiment folder>   internal: the worker process
job <run folder>           internal: train one run
"""

from __future__ import annotations

import argparse
import sys

from core.runner import registry
from core.runner.spec import SpecError, runs_root


def _duration(seconds) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}"


def _number(value, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _table(experiment: str) -> str:
    states = registry.runs(experiment)
    if not states:
        return f"no runs in '{experiment}' (runs folder: {runs_root()})"
    header = [
        "run",
        "state",
        "progress",
        "env steps",
        "elapsed",
        "eta",
        "eval",
        "held-out",
    ]
    rows = [
        [
            s.name,
            s.state,
            f"{s.progress:.0%}",
            f"{s.env_steps}/{s.budget if s.budget else '?'}",
            _duration(s.elapsed_s),
            _duration(s.eta_s),
            _number(s.last_eval),
            _number(s.heldout),
        ]
        for s in states
    ]
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]
    lines = [
        "  ".join(str(c).ljust(w) for c, w in zip(r, widths)) for r in [header, *rows]
    ]
    for s in states:
        if s.error:
            lines.append(f"{s.name}: {s.error}")
    return "\n".join(lines)


def _summary(experiment: str) -> str:
    info = registry.summary(experiment)
    counts = ", ".join(f"{n} {state}" for state, n in sorted(info["counts"].items()))
    worker = "worker alive" if info["worker_alive"] else "no worker"
    return (
        f"{experiment:<28} {info['runs']:>3} runs  {info['progress']:>4.0%}  "
        f"{counts}  ({worker})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.runner", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("start").add_argument("spec", help="experiments/<name>.json")
    status = commands.add_parser("status")
    status.add_argument("experiment", nargs="?")
    stop = commands.add_parser("stop")
    stop.add_argument("experiment")
    stop.add_argument("run", nargs="?")
    commands.add_parser("work").add_argument("exp_dir")
    commands.add_parser("job").add_argument("run_dir")
    args = parser.parse_args(argv)

    from core.runner import launch

    try:
        if args.command == "start":
            exp_dir = launch.start(args.spec)
            print(f"started {exp_dir.name}: {exp_dir}")
            print(f"watch with: python -m core.runner status {exp_dir.name}")
        elif args.command == "status":
            if args.experiment:
                print(_table(args.experiment))
            else:
                names = registry.experiments()
                print("\n".join(map(_summary, names)) if names else "no experiments")
        elif args.command == "stop":
            result = launch.stop(args.experiment, args.run)
            print(f"killed {result['killed']}, marked stopped {result['stopped']}")
        elif args.command == "work":
            launch.work(args.exp_dir)
        else:
            launch.job(args.run_dir)
    except (SpecError, RuntimeError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
