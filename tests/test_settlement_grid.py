"""Settlement, injections and the step-time SimBench grid."""

import pytest

from src_thesis.marlem.core.engine import (
    AgentSpec,
    BatterySpec,
    EngineSpec,
    MarketSpec,
    StepOutcome,
)
from src_thesis.marlem.grid import simbench
from src_thesis.marlem.grid.contract import GridLimits, NetworkRef, ParticipantInjection
from src_thesis.marlem.grid.injection import injections
from src_thesis.marlem.market.settlement import settle

CODE = "1-LV-semiurb4--0-sw"
DAY = "2016-06-01"


def world() -> EngineSpec:
    battery = BatterySpec(10.0, 0.0, 1.0, 0.5, 0.8)
    return EngineSpec(
        agents=(
            AgentSpec("a", "bus a", 10.0, (0.0,), (0.0,), battery),
            AgentSpec("b", "bus b", 10.0, (0.0,), (0.0,)),
        ),
        market=MarketSpec(),
        tariffs=None,
        steps=1,
    )


def outcome(before: float, after: float, trades: list[dict]) -> StepOutcome:
    return StepOutcome(
        step=0,
        orders=[],
        trades=trades,
        generation_kwh={"a": 4.0, "b": 0.0},
        demand_kwh={"a": 1.0, "b": 3.0},
        soc_before_kwh={"a": before, "b": None},
        soc_after_kwh={"a": after, "b": None},
        fit=0.1,
        utility_price=0.3,
    )


def trade(buyer: str, seller: str, quantity: float) -> dict:
    return {
        "buyer_id": buyer,
        "seller_id": seller,
        "price": 0.2,
        "quantity_kwh": quantity,
        "distance": 1.0,
        "loss_kwh": 0.0,
        "fees": 0.0,
    }


def test_a_charging_battery_draws_more_than_it_stores() -> None:
    s = settle(outcome(2.0, 3.0, [trade("b", "a", 1.0)]), world())["a"]
    assert s.charge_kwh == pytest.approx(2.0)  # 1 kWh stored at 50 %
    assert s.production_kwh == pytest.approx(4.0)
    assert s.consumption_kwh == pytest.approx(1.0 + 2.0)
    assert s.sold_kwh == 1.0
    # net +1 kWh physically, 1 kWh sold: nothing goes upstream
    assert s.external_kwh == pytest.approx(0.0)


def test_a_discharging_battery_delivers_less_than_it_loses() -> None:
    s = settle(outcome(5.0, 4.0, []), world())["a"]
    assert s.discharge_kwh == pytest.approx(0.8)
    assert s.production_kwh == pytest.approx(4.8)
    assert s.external_kwh == pytest.approx(4.8 - 1.0)  # untraded surplus goes up


def test_an_agent_without_a_battery_has_no_battery_flows() -> None:
    s = settle(outcome(2.0, 2.0, [trade("b", "a", 3.0)]), world())["b"]
    assert (s.charge_kwh, s.discharge_kwh, s.bought_kwh) == (0.0, 0.0, 3.0)
    assert s.external_kwh == pytest.approx(-3.0 + 3.0)


def test_injections_are_power_not_energy() -> None:
    s = settle(outcome(2.0, 2.0, []), world())
    quarter = {i.participant_id: i for i in injections(s.values(), 0.25)}
    assert quarter["a"].net_injection_kw == pytest.approx((4.0 - 1.0) / 0.25)
    assert quarter["b"].consumption_kw == pytest.approx(3.0 / 0.25)


def test_no_participants_reproduces_the_preview_power_flow() -> None:
    ref = NetworkRef("simbench", CODE)
    grid = simbench.SimBenchGrid(ref)
    grid.reset(day=DAY)
    got = grid.assess(12, [])
    want = simbench.preview_powerflow(ref, DAY, 12)
    assert got.converged and want.converged
    assert got.min_voltage_pu == pytest.approx(want.min_voltage_pu, abs=1e-6)
    assert got.external_grid_kwh == pytest.approx(want.external_grid_kwh, rel=1e-6)


def test_exporting_raises_and_importing_lowers_the_voltage() -> None:
    ref = NetworkRef("simbench", CODE)
    grid = simbench.SimBenchGrid(ref)
    grid.reset(day=DAY)
    base = grid.assess(12, [])
    # the feeder end: the bus with the lowest voltage
    bus = min(base.bus_voltage_pu, key=base.bus_voltage_pu.get)
    up = grid.assess(12, [ParticipantInjection("p", bus, 60.0, 0.0, 60.0)])
    down = grid.assess(12, [ParticipantInjection("p", bus, 0.0, 60.0, -60.0)])
    assert up.bus_voltage_pu[bus] > base.bus_voltage_pu[bus]
    assert down.bus_voltage_pu[bus] < base.bus_voltage_pu[bus]
    # the injection is set, not added up: the same call again gives the same
    assert grid.assess(12, [ParticipantInjection("p", bus, 60.0, 0.0, 60.0)]) == up


def test_limits_come_from_the_file_when_set() -> None:
    ref = NetworkRef("simbench", CODE)
    grid = simbench.SimBenchGrid(ref, limits=GridLimits(v_min_pu=1.2))
    grid.reset(day=DAY)
    assert {v.code for v in grid.assess(12, []).violations} == {"V_LOW"}
