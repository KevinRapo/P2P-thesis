"""Command line of the runner: ``python -m core.runner <command>``.

start config/experiments/x.json   queue the runs and start them on a target (--target, default
                           local; --profile test: the experiment's small test version);
                           "start -" reads the experiment as JSON from standard input
                           (how this PC starts one on a cluster)
status [experiment]        one line per experiment, or the table of one (--json: the
                           same as one JSON object, with the runs and spec)
stop <experiment> [run]    kill the worker and jobs (or cancel the SLURM tasks)
sync <experiment>          copy the results of a cluster here; prints their folder
check [spec]               whether a target is ready, and the spec can start on it
                           (--json: the report as JSON; exit 1 when not ready)
work <experiment folder>   internal: the worker process
job <run folder>           internal: train one run

Targets are named in hpc/targets.toml; from a machine without ``sbatch`` a SLURM
target is driven over SSH (``remote.py``). Every command but ``work`` and ``job``
takes --json: its answer is then the only thing on stdout, as one JSON object. Errors
print ``error: ...`` and exit with 2 (with --json: ``{"error": ...}`` on stdout).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from core.runner import launch, targets
from core.runner.registry import RunState
from core.runner.spec import PROFILES, Experiment, SpecError


def _duration(seconds) -> str:
    if seconds is None:
        return "-"

    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)

    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}"


def _number(value, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _table(states: list[RunState]) -> str:
    columns = [("run", lambda s: s.name), ("state", lambda s: s.state)]

    if any(s.slurm_state for s in states):
        columns.append(("slurm", lambda s: s.slurm_state or "-"))

    if any(s.host for s in states):
        columns.append(("host", lambda s: s.host or "-"))

    columns += [
        ("progress", lambda s: f"{s.progress:.0%}"),
        ("env steps", lambda s: f"{s.env_steps}/{s.budget if s.budget else '?'}"),
        ("elapsed", lambda s: _duration(s.elapsed_s)),
        ("eta", lambda s: _duration(s.eta_s)),
        ("eval", lambda s: _number(s.last_eval)),
        ("held-out", lambda s: _number(s.heldout)),
    ]
    header = [title for title, _ in columns]
    rows = [[str(get(s)) for _, get in columns] for s in states]
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    lines = [
        "  ".join(str(c).ljust(w) for c, w in zip(r, widths)) for r in [header, *rows]
    ]

    for s in states:
        if s.error:
            lines.append(f"{s.name}: {s.error}")

    return "\n".join(lines)


def _summary(entry: dict) -> str:
    info = entry["summary"]
    counts = ", ".join(f"{n} {state}" for state, n in sorted(info["counts"].items()))
    worker = "worker alive" if info["worker_alive"] else "no worker"

    return (
        f"{entry['name']:<28} {info['runs']:>3} runs  {info['progress']:>4.0%}  "
        f"{counts}  ({worker})"
    )


def _entry_json(entry: dict) -> dict:
    """An entry of ``Target.overview`` as JSON: the runs as plain dicts."""
    return entry | {"runs": [dataclasses.asdict(run) for run in entry["runs"]]}


def _check_text(report: dict) -> str:
    """The report of ``Target.check`` for a person."""
    lines = [f"{report['target']}: {'ready' if report['ok'] else 'NOT ready'}"]
    lines += [f"  problem: {problem}" for problem in report["problems"]]

    for key, title in (("local_commit", "this machine"), ("cluster_commit", "cluster")):
        if report[key]:
            lines.append(f"  commit on {title}: {report[key][:8]}")

    if report["active"]:
        lines.append(
            f"  queued or running: {', '.join(report['active'])} "
            "(do not update or edit the cluster's checkout meanwhile)"
        )

    return "\n".join(lines)


def _folder(target: targets.Target, name: str) -> str:
    """Where the experiment's results are read from here: its folder, or for a cluster
    seen from another machine the folder ``sync`` fills."""
    if isinstance(target, targets.RemoteTarget):
        return str(target.mirror / name)
    return str(target.root / name)


def _spec(text: str) -> str | Experiment:
    """The spec of ``start``: a file, or with ``-`` the experiment on standard
    input."""
    if text != "-":
        return text

    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        raise SpecError(f"standard input: not valid JSON ({error})") from None

    return Experiment.from_dict(data)


def _add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target",
        default="local",
        metavar="NAME",
        help="where the experiment runs, as named in hpc/targets.toml (default: local)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.runner", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("spec", help="config/experiments/<name>.json, or - (standard input)")
    start.add_argument("--profile", choices=PROFILES, default="full")
    status = commands.add_parser("status")
    status.add_argument("experiment", nargs="?")
    stop = commands.add_parser("stop")
    stop.add_argument("experiment")
    stop.add_argument("run", nargs="?")
    sync = commands.add_parser("sync")
    sync.add_argument("experiment")
    check = commands.add_parser("check")
    check.add_argument("spec", nargs="?", help="config/experiments/<name>.json")

    for command in (start, status, stop, sync, check):
        command.add_argument("--json", action="store_true")
        _add_target(command)

    commands.add_parser("work").add_argument("exp_dir")
    commands.add_parser("job").add_argument("run_dir")
    args = parser.parse_args(argv)

    target = None

    try:
        if args.command not in ("work", "job"):
            target = targets.get(args.target)
        if args.command == "start":
            name = target.start(_spec(args.spec), args.profile)
            if args.json:
                answer = {"target": target.name, "experiment": name}
                print(json.dumps(answer | {"folder": _folder(target, name)}))
            else:
                print(f"started {name} on {target.name}")

                if isinstance(target, targets.DirectTarget):
                    print(f"results in {target.root / name}")

                more = "" if target.name == "local" else f" --target {target.name}"
                print(f"watch with: python -m core.runner status {name}{more}")

                if isinstance(target, targets.RemoteTarget):
                    print(
                        f"fetch results with: python -m core.runner sync {name}{more}"
                    )
        elif args.command == "status":
            entries = target.overview(args.experiment)
            if args.json and args.experiment:
                answer = {"target": target.name, "experiment": args.experiment}
                print(json.dumps(answer | _entry_json(entries[0]), default=str))
            elif args.json:
                answer = {"experiments": [_entry_json(entry) for entry in entries]}
                print(json.dumps({"target": target.name} | answer, default=str))
            elif args.experiment:
                runs = entries[0]["runs"]
                print(_table(runs) if runs else f"no runs in '{args.experiment}'")
            else:
                text = "\n".join(map(_summary, entries))
                print(text if entries else "no experiments")
        elif args.command == "stop":
            result = target.stop(args.experiment, args.run)
            if args.json:
                answer = {"target": target.name, "experiment": args.experiment}
                print(json.dumps(result | answer))
            else:
                done = "cancelled" if "cancelled" in result else "killed"
                print(f"{done} {result[done]}, marked stopped {result['stopped']}")
        elif args.command == "sync":
            folder = target.sync(args.experiment)
            if args.json:
                answer = {"target": target.name, "experiment": args.experiment}
                answer |= {"folder": None if folder is None else str(folder)}
                print(json.dumps(answer | {"copied": target.copied}))
            elif folder is None:
                print(f"no results of '{args.experiment}' on target '{target.name}'")
            else:
                print(folder)
                if target.copied is not None:
                    print(f"copied {target.copied} file(s)")
        elif args.command == "check":
            report = target.check(args.spec)
            print(json.dumps(report) if args.json else _check_text(report))
            return 0 if report["ok"] else 1
        elif args.command == "work":
            launch.work(args.exp_dir)
        else:
            launch.job(args.run_dir)
    except (SpecError, RuntimeError, FileNotFoundError) as error:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(error)}))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 2
    finally:
        if target is not None:
            target.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
