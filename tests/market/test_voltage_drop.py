"""The DSO's voltage drop (``DsoSetup.voltage_drop``): from the distance (eq. 8f) or
measured in the power flow, as the largest deviation from the voltage the network is
held at (the external grid's set point) on the trade's path (MP-4l)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from core.config.scenario import DsoSetup
from core.grid.contract import GridAssessment, GridPath
from core.grid.simbench import _slack_voltage
from core.market.dso import Dso


def observed(dso: Dso, slack: float | None = None, **voltages: float) -> None:
    dso.observe(
        GridAssessment(
            step=0, converged=True, min_voltage_pu=1.0, max_voltage_pu=1.03,
            max_line_loading_percent=0.0, max_trafo_loading_percent=None,
            losses_kwh=0.0, external_grid_kwh=0.0,
            bus_voltage_pu=voltages, violations=(), slack_voltage_pu=slack,
        )
    )


def test_measured_voltage_drop_is_the_largest_deviation_from_nominal_without_a_slack():
    """Without a set point from the flow, the reference is nominal, 1 pu; without the
    path's buses listed, the two ends stand for it."""
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, x=1.03, y=1.01)
    path = GridPath(distance_km=0.2, bus_a="x", bus_b="y")
    assert dso.voltage_drop_of(path) == pytest.approx(0.03)
    fees = dso.fees_of(quantity=2.0, price=0.2, path=path, loss_kwh=0.0)
    assert fees.voltage == pytest.approx(0.03 * 2.0 * 0.2)
    distance = Dso(DsoSetup())
    assert distance.voltage_drop_of(path) == pytest.approx(0.15 * 0.2)


def test_a_network_at_its_slack_voltage_pays_no_voltage_fee():
    """SimBench's external grids hold 1.025 pu: with nothing drawn, every bus is at
    that, and the deviation from the slack is 0 (from nominal it was 0.025)."""
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, slack=1.025, x=1.025, y=1.025)
    path = GridPath(bus_a="x", bus_b="y", buses=("x", "y"))
    assert dso.voltage_drop_of(path) == pytest.approx(0.0)
    assert dso.fees_of(2.0, 0.2, path, 0.0).voltage == pytest.approx(0.0)


def test_the_deviation_is_read_from_the_slack_both_ways():
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, slack=1.025, x=1.05, y=0.99)
    assert dso.voltage_drop_of(GridPath(bus_a="x", bus_b="x")) == pytest.approx(0.025)
    assert dso.voltage_drop_of(GridPath(bus_a="y", bus_b="y")) == pytest.approx(0.035)


def test_two_neighbours_at_the_same_high_voltage_still_pay_for_it():
    """The difference between the ends was 0 here although the feeder sits at the
    voltage limit: what a trade adds to a high feeder is its distance from the slack."""
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, slack=1.025, x=1.05, y=1.05)
    assert dso.voltage_drop_of(GridPath(bus_a="x", bus_b="y")) == pytest.approx(0.025)


def test_every_bus_on_the_path_counts_not_only_its_ends():
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, slack=1.025, x=1.03, mid=1.05, y=1.04)
    ends = GridPath(bus_a="x", bus_b="y")
    along = GridPath(bus_a="x", bus_b="y", buses=("x", "mid", "y"))
    assert dso.voltage_drop_of(ends) == pytest.approx(0.015)
    assert dso.voltage_drop_of(along) == pytest.approx(0.025)


def test_unknown_buses_cost_nothing_and_the_fee_is_capped():
    dso = Dso(DsoSetup(voltage_drop="measured"))
    assert dso.voltage_drop_of(GridPath(bus_a="x", bus_b="y")) == 0.0
    observed(dso, slack=1.0, x=1.12)
    fees = dso.fees_of(1.0, 1.0, GridPath(bus_a="x", bus_b="x"), 0.0)
    assert fees.voltage == pytest.approx(dso.setup.voltage_threshold)


def test_the_slack_is_the_external_grids_set_point_the_feeding_one_with_several():
    one = SimpleNamespace(
        ext_grid=pd.DataFrame({"vm_pu": [1.025], "in_service": [True]}),
        res_ext_grid=pd.DataFrame({"p_mw": [0.1]}),
    )
    assert _slack_voltage(one) == pytest.approx(1.025)

    two = SimpleNamespace(
        ext_grid=pd.DataFrame(
            {"vm_pu": [1.02, 1.03, 1.04], "in_service": [True, True, False]}
        ),
        res_ext_grid=pd.DataFrame({"p_mw": [0.05, -0.2, 9.0]}),
    )
    assert _slack_voltage(two) == pytest.approx(1.03)  # the one delivering the most
    none = SimpleNamespace(
        ext_grid=pd.DataFrame({"vm_pu": [1.0], "in_service": [False]}),
        res_ext_grid=pd.DataFrame({"p_mw": [0.0]}),
    )
    assert _slack_voltage(none) is None


def test_the_power_flow_reports_the_slack_and_a_quiet_network_pays_nothing():
    from pathlib import Path

    from core.config import store
    from core.market.lem import LocalEnergyMarket

    path = Path(__file__).resolve().parents[2] / "config/scenarios/thesis_rural1.json"
    scenario = store.load(path)
    market = LocalEnergyMarket(scenario)
    market.reset()
    record = market.step({})
    assert record.grid.slack_voltage_pu == pytest.approx(1.025)
    assert scenario.dso.voltage_drop == "measured"
    # a night step: every bus within 0.01 pu of the slack, not 0.025 off nominal
    assert market.dso.slack_voltage_pu == pytest.approx(1.025)
    assert max(record.grid.bus_voltage_pu.values()) - 1.025 < 0.01
    assert all(t.fee_parts.voltage < 0.01 * t.quantity * t.price for t in record.untraded)
