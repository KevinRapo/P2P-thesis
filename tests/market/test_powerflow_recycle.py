"""pandapower's ``recycle`` in the step power flow gives the same grid results.

``SimBenchGrid`` reuses pandapower's internal network model between steps
(``core/grid/powerflow.py``). These tests play the same days with and without it,
with the market's own bidding rule and with random orders, and compare every
number of every step's ``GridAssessment``.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from core.config import store
from core.grid.powerflow import RECYCLE, SimBenchGrid
from core.market.lem import LocalEnergyMarket, OrderIntent

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"
TOL = 1e-8


def play(recycle, day: str, random_orders: bool) -> list:
    """Every step's grid assessment of one day."""
    SimBenchGrid.recycle = recycle
    try:
        scenario = store.load(SCENARIO)
        scenario.grid.day = day
        market = LocalEnergyMarket(scenario)
        market.reset()
        rng = np.random.default_rng(0)
        out = []

        while not market.done:
            intents = None
            if random_orders:
                intents = {
                    pid: OrderIntent(
                        pid,
                        bool(rng.integers(2)),
                        float(rng.uniform(0.08, 0.3)),
                        float(rng.uniform(0, 3)),
                    )
                    for pid in market.participants
                }
            out.append(market.step(intents).grid)

        return out
    finally:
        SimBenchGrid.recycle = RECYCLE


def same(a, b) -> bool:
    if a is None or b is None:
        return a is b

    if isinstance(a, float):
        return math.isclose(a, b, rel_tol=0, abs_tol=TOL)

    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)

    return a == b


@pytest.mark.parametrize(
    "day, random_orders",
    [("2016-06-15", False), ("2016-06-15", True), ("2016-01-10", True)],
)
def test_recycle_gives_the_same_grid_results(day, random_orders):
    """Every step: convergence, voltages, loadings, losses, external exchange,
    each bus's voltage and each line's loading agree to 1e-8 with and without
    recycle (the same Newton-Raphson solve, only the set-up is reused)."""
    plain = play(None, day, random_orders)
    fast = play(RECYCLE, day, random_orders)
    assert len(plain) == len(fast) == 24
    fields = [
        "converged",
        "min_voltage_pu",
        "max_voltage_pu",
        "max_line_loading_percent",
        "max_trafo_loading_percent",
        "losses_kwh",
        "external_grid_kwh",
        "bus_voltage_pu",
        "line_loading_percent",
        "violations",
    ]

    for step, (a, b) in enumerate(zip(plain, fast)):
        for name in fields:
            x, y = getattr(a, name), getattr(b, name)
            x = dict(x) if hasattr(x, "items") else x
            y = dict(y) if hasattr(y, "items") else y
            assert same(x, y), f"step {step}, {name}: {x} != {y}"
