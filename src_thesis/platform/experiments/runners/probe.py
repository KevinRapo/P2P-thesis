"""Short checks that build a world and look at it: a dry run and sanity scenarios.

They need the market, the network and pandapower, which the Studio never loads, so
they run in a subprocess:

    python -m src_thesis.platform.experiments.runners.probe dry-run < file.json
    python -m src_thesis.platform.experiments.runners.probe scenario <id> < file.json

The file (resolved or not) comes in on stdin, one JSON result goes out on stdout.
``run_probe`` is the caller's side and needs only the standard library.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
MODULE = "src_thesis.platform.experiments.runners.probe"


def run_probe(command: str, file_json: str, *args: str, timeout_s: float = 600) -> dict:
    """Run a probe in a subprocess and return its JSON result.

    Args:
        command: ``"dry-run"`` or ``"scenario"``.
        file_json: The experiment file as JSON text.
        *args: Command arguments (the scenario ID).
        timeout_s: Give up after this long.

    Returns:
        The result; ``{"error": ...}`` when the probe crashed or timed out.
    """
    try:
        done = subprocess.run(
            [sys.executable, "-m", MODULE, command, *args],
            input=file_json,
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"{command} took longer than {timeout_s:g} s"}
    lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
    if done.returncode != 0 or not lines:
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:]
        return {"error": tail[0] if tail else f"{command} failed"}
    return json.loads(lines[-1])


def _world(text: str) -> Any:
    from src_thesis.platform.experiments.models.records import ExperimentFile
    from src_thesis.platform.experiments.models.resolve import resolve

    resolved = resolve(ExperimentFile.model_validate_json(text))
    return resolved


def dry_run(text: str) -> dict:
    """Build one day, take the first step with nobody ordering, assess the grid."""
    from src_thesis.marlem.simulation.loop import run_simulation
    from src_thesis.marlem.simulation.controllers import get_policy
    from src_thesis.platform.experiments.factory.environment import (
        build_engine_spec,
        build_grid,
        build_grid_view,
    )
    from src_thesis.marlem.simulation.lem_engine import build_engine

    resolved = _world(text)
    spec = build_engine_spec(resolved)
    engine = build_engine(spec, build_grid_view(resolved, spec))
    grid = build_grid(resolved, spec)
    engine.n_steps = 1  # one step is enough to catch what is wrong
    result = run_simulation(engine, spec, get_policy("no_order"), grid)
    step = result.steps[0]
    assessment = step["assessment"] or {}
    invariants = [c for c in result.checks if c["severity"] == "invariant"]
    failed = [
        c
        for c in result.checks
        if c["failures"]
        and c["severity"] != "physical"
        and c["id"] != "steps_played"  # one step was asked for
    ]
    return {
        "ok": bool(assessment.get("converged"))
        and not [c for c in failed if c["severity"] == "invariant"],
        "power_flow_converged": assessment.get("converged"),
        "settlement_residual_kwh": None,  # no independent balance to compare to
        "messages": [
            f"Built {len(spec.agents)} participants on day {spec.day}, "
            f"{spec.steps} steps of {spec.step_hours:g} h.",
            *(f"Warning: {w}" for w in spec.warnings),
            *(
                f"{'Known engine fault ' + c['issue'] if c['issue'] else 'Failed'}: "
                f"{c['title']}"
                for c in failed
            ),
            f"{len(invariants)} invariants checked.",
        ],
    }


def scenario(text: str, scenario_id: str) -> dict:
    """Run one sanity scenario on the file's network and participants."""
    from src_thesis.marlem.simulation.scenarios import SCENARIOS, run_scenario
    from src_thesis.platform.experiments.factory.environment import (
        build_engine_spec,
        world_builder,
    )

    resolved = _world(text)
    base = build_engine_spec(resolved)
    out = run_scenario(SCENARIOS[scenario_id], base, world_builder(resolved))

    def low(result, key):
        return [(s["assessment"] or {}).get(key) for s in result.steps]

    return {
        "scenario": out.scenario,
        "title": out.title,
        "expected": out.expected,
        "passed": out.passed,
        "expectations": [
            {"statement": e.statement, "passed": e.passed, "detail": e.detail}
            for e in out.expectations
        ],
        "hours": [i * base.step_hours for i in range(base.steps)],
        "series": {
            "min voltage, idle (pu)": low(out.baseline, "min_voltage_pu"),
            "min voltage, scenario (pu)": low(out.result, "min_voltage_pu"),
            "max voltage, idle (pu)": low(out.baseline, "max_voltage_pu"),
            "max voltage, scenario (pu)": low(out.result, "max_voltage_pu"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point; reads the file from stdin and prints one JSON line."""
    argv = list(sys.argv[1:] if argv is None else argv)
    text = sys.stdin.read()
    if argv[0] == "dry-run":
        result = dry_run(text)
    elif argv[0] == "scenario":
        result = scenario(text, argv[1])
    else:
        print(f"unknown command {argv[0]!r}", file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
