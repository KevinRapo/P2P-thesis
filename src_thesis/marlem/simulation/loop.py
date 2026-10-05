"""Run one day: controllers, market, settlement, grid, checks.

Each step: the controller sees the agents' views and gives intents; the engine
clears the market; settlement turns the outcome into physical flows; the grid
assesses those flows; the checks look at all of it; one record is kept. The
loop knows nothing about which engine, controller or grid it was given.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from src_thesis.marlem.simulation.checks import (
    Finding,
    check_day,
    check_step,
    summarize,
)
from src_thesis.marlem.simulation.spec import EngineSpec, MarketEngine
from src_thesis.marlem.simulation.policy import Policy
from src_thesis.marlem.grid.contract import GridModel
from src_thesis.marlem.simulation.injection import injections
from src_thesis.marlem.simulation.settlement import settle


@dataclass
class SimulationResult:
    """One simulated day.

    Attributes:
        day: The day, ``YYYY-MM-DD``.
        seed: Seed of the day.
        steps: One record per step: ``step``, ``orders``, ``trades``,
            ``settlement`` (per agent), ``assessment`` (grid, as a dict),
            ``prices``, ``findings``.
        findings: Every failed check, with the day-level ones.
        checks: Every check with its failure count (``checks.summarize``).
        summary: Totals of the day.
        stopped: Whether the loop was stopped before the last step.
        warnings: Things changed while building the world.
    """

    day: str
    seed: int
    steps: list[dict[str, Any]] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    stopped: bool = False
    warnings: list[str] = field(default_factory=list)


def run_simulation(
    engine: MarketEngine,
    spec: EngineSpec,
    policy: Policy,
    grid: Optional[GridModel] = None,
    seed: Optional[int] = None,
    on_step: Optional[Callable[[dict[str, Any]], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> SimulationResult:
    """Play ``spec.steps`` steps of one day.

    Args:
        engine: The market, built from ``spec``.
        spec: The day's world.
        policy: The controller.
        grid: The step-time grid; none runs the market without a power flow.
        seed: Seed of the day; the spec's when ``None``.
        on_step: Called with each step record as soon as it exists.
        should_stop: Polled before each step; true ends the day early.
    """
    seed = spec.seed if seed is None else seed
    result = SimulationResult(spec.day, seed, warnings=list(engine.warnings))
    policy.reset(seed)
    engine.reset(seed)
    if grid is not None:
        grid.reset(seed, spec.day)
    outcomes = []
    for _ in range(engine.n_steps):
        if should_stop is not None and should_stop():
            result.stopped = True
            break
        outcome = engine.step(policy.act(engine.views()))
        outcomes.append(outcome)
        settlements = settle(outcome, spec)
        assessment = None
        if grid is not None:
            assessment = asdict(
                grid.assess(
                    outcome.step, injections(settlements.values(), spec.step_hours)
                )
            )
        findings = check_step(spec, outcome, settlements, assessment)
        record = {
            "step": outcome.step,
            "orders": outcome.orders,
            "trades": outcome.trades,
            "settlement": {k: asdict(v) for k, v in settlements.items()},
            "assessment": assessment,
            "prices": {
                "fit": outcome.fit,
                "utility": outcome.utility_price,
                "clearing": outcome.clearing_price,
            },
            "soc_kwh": outcome.soc_after_kwh,
            "findings": [asdict(f) for f in findings],
        }
        result.findings += findings
        result.steps.append(record)
        if on_step is not None:
            on_step(record)
    if not result.stopped:
        result.findings += check_day(spec, outcomes)
    result.checks = summarize(result.findings)
    result.summary = _summary(result, outcomes)
    return result


def _summary(result: SimulationResult, outcomes: list) -> dict[str, Any]:
    """Totals of a played day."""
    assessments = [s["assessment"] for s in result.steps if s["assessment"]]
    voltages = [
        a["min_voltage_pu"] for a in assessments if a["min_voltage_pu"] is not None
    ]
    highs = [
        a["max_voltage_pu"] for a in assessments if a["max_voltage_pu"] is not None
    ]
    return {
        "steps_played": len(outcomes),
        "trades": sum(len(o.trades) for o in outcomes),
        "p2p_kwh": sum(o.p2p_kwh for o in outcomes),
        "dso_kwh": sum(o.dso_kwh for o in outcomes),
        "min_voltage_pu": min(voltages) if voltages else None,
        "max_voltage_pu": max(highs) if highs else None,
        "not_converged": sum(1 for a in assessments if not a["converged"]),
        "grid_violations": sum(len(a["violations"]) for a in assessments),
        "failed_invariants": sum(
            1 for c in result.checks if c["severity"] == "invariant" and c["failures"]
        ),
        "engine_faults_seen": [
            c["issue"]
            for c in result.checks
            if c["severity"] == "engine_fault" and c["failures"]
        ],
    }
