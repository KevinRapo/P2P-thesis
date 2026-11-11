"""The DSO's voltage drop (``DsoSetup.voltage_drop``): from the distance (eq. 8f) or
measured in the power flow, as the largest deviation from nominal on the path."""

from __future__ import annotations

import pytest

from core.config.scenario import DsoSetup
from core.grid.contract import GridAssessment, GridPath
from core.market.dso import Dso


def observed(dso: Dso, **voltages: float) -> None:
    dso.observe(
        GridAssessment(
            step=0, converged=True, min_voltage_pu=1.0, max_voltage_pu=1.03,
            max_line_loading_percent=0.0, max_trafo_loading_percent=None,
            losses_kwh=0.0, external_grid_kwh=0.0,
            bus_voltage_pu=voltages, violations=(),
        )
    )


def test_measured_voltage_drop_is_the_largest_deviation_from_nominal_at_the_ends():
    """Without the path's buses listed, the two ends stand for it."""
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, x=1.03, y=1.01)
    path = GridPath(distance_km=0.2, bus_a="x", bus_b="y")
    assert dso.voltage_drop_of(path) == pytest.approx(0.03)
    fees = dso.fees_of(quantity=2.0, price=0.2, path=path, loss_kwh=0.0)
    assert fees.voltage == pytest.approx(0.03 * 2.0 * 0.2)
    distance = Dso(DsoSetup())
    assert distance.voltage_drop_of(path) == pytest.approx(0.15 * 0.2)


def test_two_neighbours_at_the_same_high_voltage_still_pay_for_it():
    """The old measure, |V_a - V_b|, was 0 here although the feeder sits at the
    voltage limit: what a trade adds to a high feeder is the voltage itself."""
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, x=1.05, y=1.05)
    path = GridPath(bus_a="x", bus_b="y")
    assert dso.voltage_drop_of(path) == pytest.approx(0.05)


def test_a_low_voltage_counts_as_much_as_a_high_one():
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, x=0.96, y=1.01)
    assert dso.voltage_drop_of(GridPath(bus_a="x", bus_b="y")) == pytest.approx(0.04)


def test_every_bus_on_the_path_counts_not_only_its_ends():
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, x=1.01, mid=1.045, y=1.02)
    ends = GridPath(bus_a="x", bus_b="y")
    along = GridPath(bus_a="x", bus_b="y", buses=("x", "mid", "y"))
    assert dso.voltage_drop_of(ends) == pytest.approx(0.02)
    assert dso.voltage_drop_of(along) == pytest.approx(0.045)


def test_unknown_buses_cost_nothing_and_the_fee_is_capped():
    dso = Dso(DsoSetup(voltage_drop="measured"))
    assert dso.voltage_drop_of(GridPath(bus_a="x", bus_b="y")) == 0.0
    observed(dso, x=1.12)
    fees = dso.fees_of(1.0, 1.0, GridPath(bus_a="x", bus_b="x"), 0.0)
    assert fees.voltage == pytest.approx(dso.setup.voltage_threshold)
