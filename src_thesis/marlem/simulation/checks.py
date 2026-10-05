"""Checks of a simulated day: does the market and the network behave as expected?

Pure functions over plain data (the engine's outcome, the settlement and the grid
assessment as a dict). Three kinds, so a red row is never misread:

- ``invariant``: must hold for any correct engine. A failure is a bug in the
  engine, the adapter or the experiment file.
- ``engine_fault``: a known defect of the original market (issue ``I-nn``). It is
  expected to fire on the original engine and must not fire on a clean one.
- ``physical``: a limit of the network observed in the result (voltage, loading,
  power-flow convergence). Not a bug: it is what the day does to the grid.

Only failures are recorded (``Finding``); ``summarize`` lists every check with
its failure count, so a check that never failed shows as passing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from src_thesis.marlem.simulation.spec import EngineSpec, Settlement, StepOutcome

TOL = 1e-3  # kWh; orders pass through float32


@dataclass(frozen=True)
class CheckInfo:
    """What a check is.

    Attributes:
        id: Stable name.
        title: Short title.
        severity: ``invariant``, ``engine_fault`` or ``physical``.
        issue: Issue register ID of the known defect, for ``engine_fault``.
        explanation: What it checks and what a failure means, in a sentence or two.
    """

    id: str
    title: str
    severity: str
    explanation: str
    issue: Optional[str] = None


@dataclass(frozen=True)
class Finding:
    """One failed check.

    Attributes:
        check: The check's ID.
        step: The step; ``None`` for the whole day.
        agent: The agent, bus or element concerned, if any.
        observed: Value found.
        limit: Value expected or limit exceeded.
        message: What happened, in one line.
    """

    check: str
    step: Optional[int]
    message: str
    agent: Optional[str] = None
    observed: Optional[float] = None
    limit: Optional[float] = None


CATALOG: dict[str, CheckInfo] = {
    c.id: c
    for c in (
        CheckInfo(
            "steps_played",
            "Every step of the day was played",
            "invariant",
            "The engine must run all steps of the day. The original market stops one "
            "early (I-01); the adapter configures one extra step to avoid that.",
        ),
        CheckInfo(
            "trade_integrity",
            "Trades are well-formed",
            "invariant",
            "Positive quantity, a price within the market bounds, buyer different "
            "from seller, both parties known.",
        ),
        CheckInfo(
            "order_respected",
            "Nobody trades more than they ordered",
            "engine_fault",
            "An agent's traded energy on its side never exceeds its order. The "
            "original market tops up transmission losses from the DSO and trades "
            "them again, so buyers receive more than they asked for.",
            "I-14",
        ),
        CheckInfo(
            "soc_limits",
            "Battery energy stays within its limits",
            "invariant",
            "State of charge between the minimum and maximum of the battery.",
        ),
        CheckInfo(
            "battery_direction",
            "The battery moves with the energy balance",
            "engine_fault",
            "An agent with energy left over (generation − demand − sales + purchases) "
            "should charge, one with a shortfall should discharge. The original "
            "market reverses the trade term, so selling charges the battery.",
            "I-18",
        ),
        CheckInfo(
            "battery_refused_charge",
            "A charge that nearly fills the battery is still made",
            "engine_fault",
            "The original battery refuses a charge entirely if it would reach the "
            "maximum state of charge instead of filling up to it.",
            "I-19",
        ),
        CheckInfo(
            "battery_power_limit",
            "The battery respects its power limit",
            "engine_fault",
            "The original battery model has no charge or discharge power limit.",
            "I-71",
        ),
        CheckInfo(
            "grid_converged",
            "The power flow converged",
            "physical",
            "A step whose power flow did not converge has no voltages or loadings.",
        ),
        CheckInfo(
            "voltage_limits",
            "Bus voltages within limits",
            "physical",
            "Every bus voltage between its minimum and maximum.",
        ),
        CheckInfo(
            "line_loading",
            "Line loading within limits",
            "physical",
            "Every line loaded below its limit.",
        ),
        CheckInfo(
            "trafo_loading",
            "Transformer loading within limits",
            "physical",
            "Every transformer loaded below its limit.",
        ),
    )
}
_GRID_CODES = {
    "NOT_CONVERGED": "grid_converged",
    "V_LOW": "voltage_limits",
    "V_HIGH": "voltage_limits",
    "LINE_OVERLOAD": "line_loading",
    "TRAFO_OVERLOAD": "trafo_loading",
}


def check_step(
    spec: EngineSpec,
    outcome: StepOutcome,
    settlements: Mapping[str, Settlement],
    assessment: Optional[Mapping[str, Any]] = None,
) -> list[Finding]:
    """The failed checks of one step.

    Args:
        spec: The world (market bounds, batteries).
        outcome: What the engine reported.
        settlements: Per agent, from ``market.settlement.settle``.
        assessment: The grid assessment as a dict; ``None`` without a grid.
    """
    found: list[Finding] = []
    step = outcome.step
    market = spec.market
    known = {a.id for a in spec.agents} | {"DSO"}
    for trade in outcome.trades:
        who = f"{trade['buyer_id']}<-{trade['seller_id']}"
        problem = None
        if trade["quantity_kwh"] <= 0:
            problem = f"quantity {trade['quantity_kwh']:.4g} is not positive"
        elif not market.min_price - TOL <= trade["price"] <= market.max_price + TOL:
            problem = f"price {trade['price']:.4g} is outside the market bounds"
        elif trade["buyer_id"] == trade["seller_id"]:
            problem = "buyer and seller are the same"
        elif trade["buyer_id"] not in known or trade["seller_id"] not in known:
            problem = "unknown party"
        if problem:
            found.append(Finding("trade_integrity", step, f"{who}: {problem}", who))
    ordered = {o["agent_id"]: o for o in outcome.orders}
    for agent in spec.agents:
        s = settlements[agent.id]
        order = ordered.get(agent.id)
        if order is not None:
            traded = s.bought_kwh if order["is_buy"] else s.sold_kwh
            other = s.sold_kwh if order["is_buy"] else s.bought_kwh
            if traded > order["quantity_kwh"] + TOL or other > TOL:
                found.append(
                    Finding(
                        "order_respected",
                        step,
                        f"{agent.id} ordered {order['quantity_kwh']:.4g} kWh "
                        f"({'buy' if order['is_buy'] else 'sell'}) but traded "
                        f"{s.bought_kwh:.4g} bought / {s.sold_kwh:.4g} sold",
                        agent.id,
                        max(traded, other),
                        order["quantity_kwh"],
                    )
                )
        battery = agent.battery
        after = outcome.soc_after_kwh.get(agent.id)
        before = outcome.soc_before_kwh.get(agent.id)
        if battery is None or after is None or before is None:
            continue
        low = battery.min_soc * battery.capacity_kwh
        high = battery.max_soc * battery.capacity_kwh
        if not low - TOL <= after <= high + TOL:
            found.append(
                Finding(
                    "soc_limits",
                    step,
                    f"{agent.id}: energy {after:.4g} kWh outside [{low:.4g}, "
                    f"{high:.4g}]",
                    agent.id,
                    after,
                    high if after > high else low,
                )
            )
        left = (s.generation_kwh - s.demand_kwh) - (s.sold_kwh - s.bought_kwh)
        delta = s.soc_delta_kwh
        if (left > TOL and delta < -TOL) or (left < -TOL and delta > TOL):
            found.append(
                Finding(
                    "battery_direction",
                    step,
                    f"{agent.id}: {left:+.4g} kWh left over, battery changed by "
                    f"{delta:+.4g} kWh",
                    agent.id,
                    delta,
                    left,
                )
            )
        if left > TOL and high - before > TOL and abs(delta) <= TOL:
            found.append(
                Finding(
                    "battery_refused_charge",
                    step,
                    f"{agent.id}: {left:+.4g} kWh left over, "
                    f"{high - before:.4g} kWh of room, nothing charged",
                    agent.id,
                    delta,
                    min(left, high - before),
                )
            )
        if battery.max_power_kw is not None:
            power = abs(delta) / spec.step_hours
            if power > battery.max_power_kw + TOL:
                found.append(
                    Finding(
                        "battery_power_limit",
                        step,
                        f"{agent.id}: battery moved at {power:.4g} kW, limit "
                        f"{battery.max_power_kw:.4g} kW",
                        agent.id,
                        power,
                        battery.max_power_kw,
                    )
                )
    for violation in (assessment or {}).get("violations", ()):
        check = _GRID_CODES.get(violation["code"])
        if check is None:
            continue
        where = violation.get("element_id")
        found.append(
            Finding(
                check,
                step,
                f"{violation['code']}"
                + (f" at {where}" if where else "")
                + (
                    f": {violation['observed']:.4g} vs limit {violation['limit']:.4g}"
                    if violation.get("observed") is not None
                    else ""
                ),
                where,
                violation.get("observed"),
                violation.get("limit"),
            )
        )
    return found


def check_day(spec: EngineSpec, outcomes: Sequence[StepOutcome]) -> list[Finding]:
    """The failed checks that concern the whole day."""
    if len(outcomes) == spec.steps:
        return []
    return [
        Finding(
            "steps_played",
            None,
            f"{len(outcomes)} of {spec.steps} steps were played",
            None,
            float(len(outcomes)),
            float(spec.steps),
        )
    ]


def summarize(findings: Sequence[Finding]) -> list[dict[str, Any]]:
    """Every check with how often it failed and where first, in catalogue order."""
    out = []
    for info in CATALOG.values():
        mine = [f for f in findings if f.check == info.id]
        steps = [f.step for f in mine if f.step is not None]
        out.append(
            {
                "id": info.id,
                "title": info.title,
                "severity": info.severity,
                "issue": info.issue,
                "explanation": info.explanation,
                "failures": len(mine),
                "first_step": min(steps) if steps else None,
            }
        )
    return out
