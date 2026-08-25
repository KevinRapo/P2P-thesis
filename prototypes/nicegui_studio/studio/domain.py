"""A deliberately small illustrative grid model.

This is not a power-flow solver. It gives the Studio something deterministic to
display while the UI architecture is learned. The future SimBench/pandapower
adapter can implement the same result contract without changing the pages.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class GridScenario:
    """Inputs exposed by the first Studio scenario editor."""

    demand_kw: float = 6.0
    pv_kw: float = 5.0
    battery_discharge_kw: float = 0.0

    def validate(self) -> None:
        values = (self.demand_kw, self.pv_kw, self.battery_discharge_kw)
        if not all(isfinite(value) for value in values):
            raise ValueError("All grid inputs must be finite numbers.")
        if self.demand_kw < 0 or self.pv_kw < 0 or self.battery_discharge_kw < 0:
            raise ValueError("Demand, PV, and battery discharge cannot be negative.")
        if self.battery_discharge_kw > self.demand_kw:
            raise ValueError("Battery discharge cannot exceed household demand.")


@dataclass(frozen=True)
class GridResult:
    """Small result surface shared by the service and the UI."""

    scenario: GridScenario
    net_household_kw: float
    feeder_exchange_kw: float
    min_voltage_pu: float
    max_voltage_pu: float
    max_line_loading_percent: float
    transformer_loading_percent: float
    losses_kw: float
    voltage_profile_pu: tuple[float, ...]

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["voltage_profile_pu"] = list(self.voltage_profile_pu)
        return data


class IllustrativeGridModel:
    """Compute stable demo indicators from one household operating point.

    The equations are intentionally transparent and labelled illustrative. A
    later SimBench/pandapower model can replace this class behind the service.
    """

    def run(self, scenario: GridScenario) -> GridResult:
        scenario.validate()
        net_household_kw = (
            scenario.demand_kw - scenario.pv_kw - scenario.battery_discharge_kw
        )
        # Background feeder demand keeps this demo visibly network-shaped while
        # the controls still affect every reported quantity.
        feeder_exchange_kw = 12.0 + net_household_kw
        stress = abs(feeder_exchange_kw)
        voltage_shift = 0.0009 * feeder_exchange_kw
        voltage_profile = tuple(
            round(1.02 - voltage_shift * (index / 7), 5) for index in range(8)
        )
        return GridResult(
            scenario=scenario,
            net_household_kw=round(net_household_kw, 3),
            feeder_exchange_kw=round(feeder_exchange_kw, 3),
            min_voltage_pu=min(voltage_profile),
            max_voltage_pu=max(voltage_profile),
            max_line_loading_percent=round(18.0 + 1.7 * stress, 3),
            transformer_loading_percent=round(28.0 + 1.1 * stress, 3),
            losses_kw=round(0.35 + 0.009 * stress**2, 3),
            voltage_profile_pu=voltage_profile,
        )
