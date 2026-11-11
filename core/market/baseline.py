"""The scenario's baseline: its market played with the bidding rule, before learning.

What a scenario does without any learned policy: every participant follows the
market's own rule (``rule_based_bid.net_position``) without its noise, as the
evaluation's ``net_position`` baseline does (``market.bid_jitter`` 0, no preferred
partner), over a window of days, the batteries and reputations carried from one day
to the next. Every step's power flow is kept, so the window shows how stressed the
network is, which fees the stress triggers, and what the rule earns.

    play(scenario, days)          one row per step (``steps``), the line loadings and
                                  bus voltages per step, and their summary
    sweep(scenario, days, ...)    the same for each value of one scenario setting,
                                  e.g. ``grid.generation_scale`` (MP-4i), as one
                                  summary row per value

No Studio code and no RL: the Studio's Market page (Baseline tab), a notebook or the
command line call the same functions. A window is played step by step, about 0.1 s a
step on a 129-bus network: a day in a few seconds, a month in about a minute.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np
import pandas as pd

from core.config.scenario import Scenario
from core.market.lem import LocalEnergyMarket, StepRecord, net_bill

# The fee parts summed per step (``GridFees``), and the loss charge (``dso.losses``).
FEE_PARTS = ("congestion", "thermal", "voltage", "transmission", "zone", "imbalance")
VIOLATIONS = {
    "V_LOW": "voltage_low",
    "V_HIGH": "voltage_high",
    "LINE_OVERLOAD": "line_overload",
    "TRAFO_OVERLOAD": "trafo_overload",
}


@dataclass(frozen=True)
class Baseline:
    """A window played with the rule.

    Attributes:
        steps: One row per step: ``day``, ``step``, ``hour``, the power flow's extremes
            (``max_line_loading_percent``, ``max_trafo_loading_percent``,
            ``min_voltage_pu``, ``max_voltage_pu``), its violations per kind (counts of
            elements), ``converged``, ``grid_losses_kwh``, ``import_kwh`` and
            ``export_kwh`` at the transformer, ``p2p_kwh``, ``dso_kwh``, the fees per
            part summed over the step's trades and the participants' ``loss_charge``,
            and ``team_money``, the participants' net bills.
        line_loading: Every line's loading per step (%), indexed like ``steps``.
        bus_voltage: Every bus's voltage per step (pu), indexed like ``steps``.
    """

    steps: pd.DataFrame
    line_loading: pd.DataFrame = field(default_factory=pd.DataFrame)
    bus_voltage: pd.DataFrame = field(default_factory=pd.DataFrame)

    def summary(self) -> dict[str, float]:
        """The window in one row: the extremes, the steps with a violation, and the
        sums of losses, fees and money."""
        s = self.steps
        fees = [f"fee_{p}" for p in FEE_PARTS] + ["loss_charge"]
        violated = s[list(VIOLATIONS.values())].sum(axis=1) > 0

        return {
            "steps": len(s),
            "line_max_percent": s.max_line_loading_percent.max(),
            "line_p95_percent": s.max_line_loading_percent.quantile(0.95),
            "trafo_max_percent": s.max_trafo_loading_percent.max(),
            "voltage_min_pu": s.min_voltage_pu.min(),
            "voltage_max_pu": s.max_voltage_pu.max(),
            "steps_violated": int(violated.sum()),
            **{f"steps_{v}": int((s[v] > 0).sum()) for v in VIOLATIONS.values()},
            "not_converged": int((~s.converged).sum()),
            "grid_losses_kwh": s.grid_losses_kwh.sum(),
            "fees": s[fees].to_numpy().sum(),
            **{f: s[f].sum() for f in fees},
            "team_money": s.team_money.sum(),
        }

    def worst_step(self) -> Optional[int]:
        """The row of ``steps`` with the highest line loading (None if empty)."""
        if self.steps.empty or self.steps.max_line_loading_percent.isna().all():
            return None
        return int(self.steps.max_line_loading_percent.idxmax())


def rule_scenario(scenario: Scenario) -> Scenario:
    """A copy of ``scenario`` whose participants all follow the bidding rule without
    its noise: the evaluation's ``net_position`` baseline."""
    found = deepcopy(scenario)
    found.market.bid_jitter = 0.0
    found.market.partner_preference = False
    return found


def play(
    scenario: Scenario,
    days: Sequence[str],
    progress: Optional[Callable[[int, int], None]] = None,
) -> Baseline:
    """``scenario`` played with the rule on ``days`` in order, the batteries and
    reputations carried from each day to the next; ``progress(done, total)`` after
    every step."""
    market = LocalEnergyMarket(rule_scenario(scenario))
    total = len(days) * market.n_steps
    rows, lines, buses = [], [], []
    battery = reputation = None

    for day in days:
        market.scenario.grid.day = day
        market.reset(battery, reputation)

        while not market.done:
            record = market.step()
            rows.append(_row(day, record, market))
            lines.append(dict(record.grid.line_loading_percent))
            buses.append(dict(record.grid.bus_voltage_pu))
            if progress is not None:
                progress(len(rows), total)

        people = market.participants.items()
        battery = {pid: p.battery.energy_kwh for pid, p in people if p.battery}
        reputation = {pid: p.reputation for pid, p in people}

    return Baseline(
        steps=pd.DataFrame(rows),
        line_loading=pd.DataFrame(lines),
        bus_voltage=pd.DataFrame(buses),
    )


def sweep(
    scenario: Scenario,
    days: Sequence[str],
    setting: str,
    values: Sequence[float],
    progress: Optional[Callable[[int, int], None]] = None,
) -> pd.DataFrame:
    """The baseline for each value of one setting, ``"<section>.<field>"`` of the
    scenario (e.g. ``"grid.generation_scale"``): one ``summary`` row per value, the
    scenario itself unchanged."""
    section, name = setting.split(".")
    rows = []
    per = len(days) * round(24 / scenario.grid.step_hours)

    for k, value in enumerate(values):
        trial = deepcopy(scenario)
        setattr(getattr(trial, section), name, value)
        tick = None
        if progress is not None:
            tick = lambda done, _total, k=k: progress(k * per + done, per * len(values))
        rows.append({setting: value, **play(trial, days, tick).summary()})

    return pd.DataFrame(rows)


def _row(day: str, record: StepRecord, market: LocalEnergyMarket) -> dict:
    """One step's row of ``Baseline.steps``."""
    g = record.grid
    hours = market.scenario.grid.step_hours
    exchange = g.external_grid_kwh if g.converged and g.external_grid_kwh else 0.0
    kinds = [v.code for v in g.violations]
    fees = {f"fee_{p}": 0.0 for p in FEE_PARTS}

    for t in record.trades:
        for p in FEE_PARTS:
            fees[f"fee_{p}"] += getattr(t.fee_parts, p, 0.0) if t.fee_parts else 0.0

    return {
        "day": day,
        "step": record.step,
        "hour": record.step * hours,
        "converged": g.converged,
        "max_line_loading_percent": _number(g.max_line_loading_percent),
        "max_trafo_loading_percent": _number(g.max_trafo_loading_percent),
        "min_voltage_pu": _number(g.min_voltage_pu),
        "max_voltage_pu": _number(g.max_voltage_pu),
        **{name: kinds.count(code) for code, name in VIOLATIONS.items()},
        "grid_losses_kwh": float(g.losses_kwh or 0.0) if g.converged else 0.0,
        "import_kwh": max(exchange, 0.0),
        "export_kwh": max(-exchange, 0.0),
        "p2p_kwh": record.p2p_kwh,
        "dso_kwh": record.dso_kwh,
        **fees,
        "loss_charge": sum(o.loss_charge for o in record.participants.values()),
        "team_money": sum(net_bill(record, pid) for pid in record.participants),
    }


def _number(value: Optional[float]) -> float:
    return float(value) if value is not None else np.nan
