"""Battery settings, validation and state across charging, discharging and reset."""

import pytest

from core.config.scenario import BatterySetup, ParticipantSetup, Scenario
from core.market.agent.battery import Battery


def test_settings_are_copied_and_energy_changes_separately():
    setup = BatterySetup(
        capacity_kwh=10.0,
        max_power_kw=2.0,
        charge_efficiency=0.8,
        discharge_efficiency=0.5,
    )
    battery = Battery(setup, step_hours=0.25)
    setup.capacity_kwh = 100.0
    setup.initial_soc = 0.9
    setup.max_power_kw = 50.0

    assert battery.charge(5.0) == 0.5  # 2 kW for 15 minutes, at the bus
    assert battery.energy_kwh == pytest.approx(5.4)
    assert battery.discharge(5.0) == 0.5
    assert battery.energy_kwh == pytest.approx(4.4)
    assert battery.setup.initial_soc == 0.5

    battery.reset()
    assert battery.energy_kwh == 5.0
    assert battery.soc == 0.5


@pytest.mark.parametrize(
    "changes",
    [
        {"capacity_kwh": 0.0},
        {"min_soc": 0.9},
        {"max_soc": 1.1},
        {"charge_efficiency": 0.0},
        {"discharge_efficiency": 1.1},
        {"initial_soc": 0.0},
        {"max_power_kw": 0.0},
        {"max_power_kw": None},
    ],
)
def test_scenario_and_constructor_report_the_same_invalid_settings(changes):
    setup = BatterySetup(**({"capacity_kwh": 10.0, "max_power_kw": 5.0} | changes))
    scenario = Scenario(participants=[ParticipantSetup("A", "bus", battery=setup)])
    problems = setup.problems()
    assert problems
    assert scenario.problems() == [f"A battery: {p}" for p in problems]

    with pytest.raises(ValueError) as error:
        Battery(setup, step_hours=1.0)

    assert str(error.value) == "Battery: " + "; ".join(problems)


def test_a_household_short_of_energy_sells_only_what_its_battery_has_left():
    """MP-2c: the battery covers the household's own deficit before anything is for
    sale; a surplus adds to the battery's energy as in eq. 15a."""
    from core.market.agent.der import Participant

    setup = BatterySetup(capacity_kwh=10.0, max_power_kw=10.0, charge_efficiency=1.0,
                         discharge_efficiency=1.0)  # 4 kWh above SoC_min at the start

    def most(generation, demand):
        me = Participant("A", "bus", [], [generation], [demand], Battery(setup, 1.0))
        return me.max_sell_kwh(0)

    assert most(3.0, 1.0) == pytest.approx(2.0 + 4.0)  # surplus plus the battery
    assert most(1.0, 2.0) == pytest.approx(4.0 - 1.0)  # its own deficit first
    assert most(1.0, 6.0) == 0.0                       # the battery cannot cover it
