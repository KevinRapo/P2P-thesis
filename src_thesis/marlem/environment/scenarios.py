"""Sanity scenarios: does the chosen network respond the way physics says?

Each scenario takes the experiment's own network and participants, replaces their
profiles with a simple fixture, runs a day with a scripted controller and states
what must happen, e.g. "everyone exports at noon: voltages rise, most at the far
end of the feeder". The expectations are checked against the result and listed,
so a failed one points at the pipeline (profiles, settlement, injections, power
flow) rather than at a policy.

A scenario needs a world to run in: ``build`` turns an ``EngineSpec`` into an
engine and a grid (the platform's factory provides it), so this module stays free
of experiment files.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional

from src_thesis.marlem.core.engine import AgentSpec, EngineSpec, MarketEngine
from src_thesis.marlem.environment.simulation import SimulationResult, run_simulation
from src_thesis.marlem.grid.contract import GridModel, ParticipantInjection
from src_thesis.marlem.policies.registry import get_policy

Build = Callable[[EngineSpec], tuple[MarketEngine, Optional[GridModel]]]
EPS = 1e-6  # pu; below this a voltage change is noise


@dataclass(frozen=True)
class Expectation:
    """One statement a scenario makes about its result.

    Attributes:
        statement: What must hold.
        passed: Whether it did.
        detail: The numbers behind it.
    """

    statement: str
    passed: bool
    detail: str = ""


@dataclass
class ScenarioContext:
    """Everything ``verify`` may look at.

    Attributes:
        spec: The fixture world that was run.
        baseline: The same world with every participant idle (zero profiles).
        test: The scenario's day.
        grid: The grid the days ran on.
        hours: The scenario's active hours.
    """

    spec: EngineSpec
    baseline: SimulationResult
    test: SimulationResult
    grid: GridModel
    hours: range

    def steps(self) -> list[int]:
        """Steps of the active hours."""
        per_hour = round(1 / self.spec.step_hours)
        return [h * per_hour + k for h in self.hours for k in range(per_hour)]

    def voltages(self, result: SimulationResult, step: int) -> dict[str, float]:
        """Bus voltages of ``step``."""
        return result.steps[step]["assessment"]["bus_voltage_pu"]

    def buses_by_distance(self) -> list[str]:
        """Participants' buses, nearest to the slack first."""
        slack = self.grid.topology_view().external_grid_bus
        buses = {a.bus for a in self.spec.agents}
        return sorted(buses, key=lambda b: self.grid.electrical_distance(slack, b))


@dataclass(frozen=True)
class Scenario:
    """A fixture, a controller and what to expect.

    Attributes:
        id: Stable name.
        title: Short title.
        expected: What should happen, in plain words.
        controller: Registry name of the scripted controller.
        fixture: Each agent's profile value of a step: ``(energy_kwh, active, idle)
            -> (generation_kwh, demand_kwh)``, ``active`` inside ``hours``,
            ``idle`` for the baseline run.
        hours: Hours of the day the fixture is active.
        verify: Reads the context and lists the expectations.
    """

    id: str
    title: str
    expected: str
    controller: str
    fixture: Callable[[float, bool, bool], tuple[float, float]]
    hours: range
    verify: Callable[[ScenarioContext], list[Expectation]]


@dataclass
class ScenarioResult:
    """The outcome of one scenario.

    Attributes:
        scenario: The scenario's ID.
        title: Its title.
        expected: What it expected.
        expectations: Each statement and whether it held.
        passed: All statements held.
        result: The scenario's day, for replay.
    """

    scenario: str
    title: str
    expected: str
    expectations: list[Expectation] = field(default_factory=list)
    passed: bool = False
    result: Optional[SimulationResult] = None


def _fixture_world(
    base: EngineSpec, scenario: Scenario, power_kw: float, idle: bool
) -> EngineSpec:
    """The base world with fixture profiles: ``power_kw`` per agent, or nothing."""
    energy = power_kw * base.step_hours
    per_hour = round(1 / base.step_hours)
    active = {h * per_hour + k for h in scenario.hours for k in range(per_hour)}
    agents = []
    for a in base.agents:
        gen, dem = [], []
        for step in range(base.steps):
            g, d = scenario.fixture(energy, step in active, idle)
            gen.append(g)
            dem.append(d)
        agents.append(AgentSpec(a.id, a.bus, energy, tuple(gen), tuple(dem), None))
    market = replace(
        base.market,
        min_quantity=0.0,
        max_quantity=max(base.market.max_quantity, energy),
    )
    return replace(base, agents=tuple(agents), market=market)


def _flow(
    s: Scenario, spec: EngineSpec, build: Build, controller: str, idle: bool
) -> tuple[SimulationResult, GridModel]:
    world = _fixture_world(spec, s, _POWER_KW, idle)
    engine, grid = build(world)
    result = run_simulation(engine, world, get_policy(controller), grid, world.seed)
    return result, grid


_POWER_KW = 25.0


def run_scenario(scenario: Scenario, base: EngineSpec, build: Build) -> ScenarioResult:
    """Run a scenario on the world of ``base``.

    Args:
        scenario: What to run.
        base: The experiment's world (its agents give the buses).
        build: Turns a spec into an engine and a grid.
    """
    baseline, _ = _flow(scenario, base, build, "no_order", True)
    test, grid = _flow(scenario, base, build, scenario.controller, False)
    spec = _fixture_world(base, scenario, _POWER_KW, False)
    context = ScenarioContext(spec, baseline, test, grid, scenario.hours)
    expectations = scenario.verify(context)
    return ScenarioResult(
        scenario.id,
        scenario.title,
        scenario.expected,
        expectations,
        all(e.passed for e in expectations),
        test,
    )


# ------------------------------------------------------------------ expectations
def _no_orders(c: ScenarioContext) -> list[Expectation]:
    trades = sum(len(s["trades"]) for s in c.test.steps)
    out = [Expectation("No trades happen", trades == 0, f"{trades} trades")]
    worst = 0.0
    kw = _POWER_KW
    c.grid.reset(c.spec.seed, c.spec.day)
    injected = [ParticipantInjection(a.id, a.bus, 0.0, kw, -kw) for a in c.spec.agents]
    for step in range(c.spec.steps):
        direct = c.grid.assess(step, injected)
        got = c.test.steps[step]["assessment"]
        for bus, v in direct.bus_voltage_pu.items():
            worst = max(worst, abs(v - got["bus_voltage_pu"][bus]))
    out.append(
        Expectation(
            "The grid sees exactly the participants' own load",
            worst < EPS,
            f"largest voltage difference to a direct power flow: {worst:.2e} pu",
        )
    )
    return out


def _rises(c: ScenarioContext, sign: int) -> list[Expectation]:
    """Voltage moves in ``sign`` direction at the participants' buses, more with
    distance from the slack bus."""
    word = "rise" if sign > 0 else "fall"
    buses = c.buses_by_distance()
    deltas: dict[str, float] = {}
    for bus in buses:
        moves = [
            sign * (c.voltages(c.test, s)[bus] - c.voltages(c.baseline, s)[bus])
            for s in c.steps()
        ]
        deltas[bus] = min(moves)
    moved = [b for b in buses if deltas[b] > EPS]
    near, far = deltas[buses[0]], deltas[buses[-1]]
    return [
        Expectation(
            f"Voltage {word}s at every participant's bus in the active hours",
            len(moved) == len(buses),
            f"{len(moved)} of {len(buses)} buses moved by more than {EPS:g} pu",
        ),
        Expectation(
            f"The {word} is larger at the far end of the feeder than near the slack",
            far > near,
            f"{word} at the farthest bus {far:.5f} pu, nearest {near:.5f} pu",
        ),
    ]


SCENARIOS: dict[str, Scenario] = {
    s.id: s
    for s in (
        Scenario(
            "idle_market",
            "Own load only, nobody orders",
            "The market stays silent and the grid sees only what the participants "
            "themselves consume.",
            "no_order",
            lambda e, active, idle: (0.0, 0.0 if idle else e),
            range(0, 24),
            _no_orders,
        ),
        Scenario(
            "export_at_noon",
            "Everyone exports at noon",
            "Voltage rises at the participants' buses around noon, and rises most "
            "at the far end of the feeder.",
            "net_position",
            lambda e, active, idle: (e if active and not idle else 0.0, 0.0),
            range(11, 14),
            lambda c: _rises(c, 1),
        ),
        Scenario(
            "import_in_the_evening",
            "Everyone imports in the evening",
            "Voltage falls at the participants' buses in the evening, and falls "
            "most at the far end of the feeder.",
            "net_position",
            lambda e, active, idle: (0.0, e if active and not idle else 0.0),
            range(18, 21),
            lambda c: _rises(c, -1),
        ),
    )
}


def names() -> list[str]:
    """IDs of all scenarios."""
    return list(SCENARIOS)


def describe() -> list[dict[str, Any]]:
    """ID, title and expectation of every scenario, as plain data."""
    return [
        {"id": s.id, "title": s.title, "expected": s.expected}
        for s in SCENARIOS.values()
    ]
