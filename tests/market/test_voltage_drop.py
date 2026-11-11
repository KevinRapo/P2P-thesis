"""The DSO's voltage drop (``DsoSetup.voltage_drop``): from the distance (eq. 8f) or
measured in the power flow."""

from __future__ import annotations

import pytest

from core.config.scenario import DsoSetup
from core.grid.contract import GridAssessment, GridPath
from core.market.dso import Dso


def test_measured_voltage_drop_is_the_difference_at_the_paths_ends():
    dso = Dso(DsoSetup(voltage_drop="measured"))
    grid = GridAssessment(
        step=0, converged=True, min_voltage_pu=1.0, max_voltage_pu=1.03,
        max_line_loading_percent=0.0, max_trafo_loading_percent=None,
        losses_kwh=0.0, external_grid_kwh=0.0,
        bus_voltage_pu={"x": 1.03, "y": 1.01}, violations=(),
    )
    dso.observe(grid)
    path = GridPath(distance_km=0.2, bus_a="x", bus_b="y")
    assert dso.voltage_drop_of(path) == pytest.approx(0.02)
    fees = dso.fees_of(quantity=2.0, price=0.2, path=path, loss_kwh=0.0)
    assert fees.voltage == pytest.approx(0.02 * 2.0 * 0.2)
    distance = Dso(DsoSetup())
    assert distance.voltage_drop_of(path) == pytest.approx(0.15 * 0.2)
