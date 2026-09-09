"""
Battery storage model for DER agents in the Local Energy Market.

This module implements a simplified battery model that focuses on energy level
tracking and efficiency losses during charging and discharging operations.
"""

from enum import Enum
from typing import Dict, Optional, Tuple


class BatteryState(Enum):
    """Possible states of a battery."""

    CHARGING = "charging"
    DISCHARGING = "discharging"
    IDLE = "idle"


class Battery:
    """Battery storage model focusing on energy level and efficiency."""

    def __init__(self,
                 nominal_capacity: float,
                 min_soc: float = 0.0,
                 max_soc: float = 1.0,
                 charge_efficiency: float = 1.0,
                 discharge_efficiency: float = 1.0,
                 max_charge_power: Optional[float] = None,
                 max_discharge_power: Optional[float] = None,
                 time_step_hours: float = 1.0,
                 initial_soc: Optional[float] = None) -> None:
        """Initialize the battery model.

        Args:
            nominal_capacity: Nominal internal energy capacity in kWh
            min_soc: Minimum state of charge (0-1)
            max_soc: Maximum state of charge (0-1)
            charge_efficiency: Charging efficiency (0-1)
            discharge_efficiency: Grid-side delivery efficiency (0-1)
            max_charge_power: Optional grid-side charging limit in kW
            max_discharge_power: Optional grid-side discharging limit in kW
            time_step_hours: Duration of one simulation step in hours
            initial_soc: Fixed initial SOC. Defaults to the midpoint of SOC bounds.
        """
        self.nominal_capacity = nominal_capacity
        self.min_soc = min_soc
        self.max_soc = max_soc
        self.charge_efficiency = charge_efficiency
        self.discharge_efficiency = discharge_efficiency
        self.max_charge_power = max_charge_power
        self.max_discharge_power = max_discharge_power
        self.time_step_hours = time_step_hours
        self.initial_soc = (min_soc + max_soc) / 2 if initial_soc is None else initial_soc

        # Initialize state
        self.state: BatteryState = None
        self.energy_level: float = None
        self.cumulative_charge: float = None
        self.cumulative_discharge: float = None
        self.reset()

    def reset(self, seed: Optional[int] = None) -> None:
        """Reset the battery state.

        Args:
            seed: Retained for backwards compatibility. Battery reset is
                deterministic and always restores ``initial_soc``.
        """
        # Reset state
        self.state = BatteryState.IDLE
        self.energy_level = self.initial_soc * self.nominal_capacity
        self.cumulative_charge = 0.0
        self.cumulative_discharge = 0.0

        # Check reset
        self._check_init()

    def _check_init(self) -> None:
        """Validate battery specifications after initialization.

        Raises:
            ValueError: If nominal capacity is less than or equal to zero
            ValueError: If min SOC is not between 0 and 1
            ValueError: If max SOC is not between 0 and 1
            ValueError: If min SOC is greater than max SOC
        """
        if self.nominal_capacity <= 0:
            raise ValueError("Nominal capacity must be greater than zero.")
        if not 0 <= self.min_soc <= 1:
            raise ValueError("Min SOC must be between 0 and 1.")
        if not 0 <= self.max_soc <= 1:
            raise ValueError("Max SOC must be between 0 and 1.")
        if self.min_soc >= self.max_soc:
            raise ValueError("Min SOC must be less than Max SOC.")
        if not 0 <= self.charge_efficiency <= 1:
            raise ValueError("Charge efficiency must be between 0 and 1.")
        if not 0 <= self.discharge_efficiency <= 1:
            raise ValueError("Discharge efficiency must be between 0 and 1.")
        if self.max_charge_power is not None and self.max_charge_power <= 0:
            raise ValueError("Maximum charge power must be greater than zero.")
        if self.max_discharge_power is not None and self.max_discharge_power <= 0:
            raise ValueError("Maximum discharge power must be greater than zero.")
        if self.time_step_hours <= 0:
            raise ValueError("Time step must be greater than zero.")
        if not self.min_soc <= self.initial_soc <= self.max_soc:
            raise ValueError("Initial SOC must be between min SOC and max SOC.")
        if self.energy_level < self.min_soc * self.nominal_capacity or self.energy_level > self.max_soc * self.nominal_capacity:
            raise ValueError("Energy level must be between min SOC and max SOC.")

    def _can_charge(self, energy: float) -> bool:
        """Check if charging is possible.

        Args:
            energy: Charging energy in kWh

        Returns:
            True if charging is possible
        """
        if energy <= 0:
            return False

        return self.energy_level < self.max_soc * self.nominal_capacity

    def _can_discharge(self, energy: float) -> bool:
        """Check if discharging is possible.

        Args:
            energy: Discharge energy in kWh

        Returns:
            True if discharging is possible
        """
        if energy <= 0:
            return False

        return self.energy_level > self.min_soc * self.nominal_capacity

    def charge(self, energy: float) -> float:
        """Charge the battery.

        Args:
            energy: Grid-side charging energy in kWh

        Returns:
            Internal energy stored in the battery (kWh)
        """
        if self._can_charge(energy):
            headroom = self.max_soc * self.nominal_capacity - self.energy_level
            power_limit = float("inf") if self.max_charge_power is None else self.max_charge_power * self.time_step_hours
            grid_energy = min(energy, headroom / self.charge_efficiency, power_limit) if self.charge_efficiency else 0.0
            energy_stored = grid_energy * self.charge_efficiency

            # Update state
            self.energy_level += energy_stored
            self.cumulative_charge += energy_stored
            self.state = BatteryState.CHARGING

            return energy_stored

        else:
            self.state = BatteryState.IDLE
            return 0.0

    def discharge(self, energy: float) -> float:
        """Discharge the battery.

        Args:
            energy: Requested grid-side delivered energy in kWh

        Returns:
            Grid-side energy delivered by the battery (kWh)
        """
        if self._can_discharge(energy):
            available_internal = self.energy_level - self.min_soc * self.nominal_capacity
            power_limit = float("inf") if self.max_discharge_power is None else self.max_discharge_power * self.time_step_hours
            energy_discharged = min(energy, available_internal * self.discharge_efficiency, power_limit)
            removed_from_storage = energy_discharged / self.discharge_efficiency if self.discharge_efficiency else 0.0

            # Update state
            self.energy_level -= removed_from_storage
            self.cumulative_discharge += energy_discharged
            self.state = BatteryState.DISCHARGING

            return energy_discharged

        else:
            self.state = BatteryState.IDLE
            return 0.0

    def idle(self) -> None:
        """Update battery state for a time step."""
        self.state = BatteryState.IDLE

    def get_state(self) -> Dict:
        """Get current battery state.

        Returns:
            Dictionary containing battery state information
        """
        available_charge, available_discharge = self.estimate_available_energy()

        return {"state": self.state,
                "energy_level": self.energy_level,
                "soc": self.energy_level / self.nominal_capacity,
                "available_charge": available_charge,
                "available_discharge": available_discharge,
                "cumulative_charge": self.cumulative_charge,
                "cumulative_discharge": self.cumulative_discharge}

    def estimate_available_energy(self) -> Tuple[float, float]:
        """Estimate available energy for charging and discharging.

        Returns:
            Tuple of (available charge capacity, available discharge capacity)
        """
        headroom = self.max_soc * self.nominal_capacity - self.energy_level
        available_internal = self.energy_level - self.min_soc * self.nominal_capacity
        charge_limit = float("inf") if self.max_charge_power is None else self.max_charge_power * self.time_step_hours
        discharge_limit = float("inf") if self.max_discharge_power is None else self.max_discharge_power * self.time_step_hours
        available_charge = min(headroom / self.charge_efficiency, charge_limit) if self.charge_efficiency else 0.0
        available_discharge = min(available_internal * self.discharge_efficiency, discharge_limit)

        return (available_charge, available_discharge)
