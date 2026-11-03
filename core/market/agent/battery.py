"""A participant's battery: its energy and how charging and discharging change it.

[P1] eq. 15c-d (what the battery can still take or give) and eq. 16 (its energy
after a step). Energy in and out is counted at the bus; the efficiencies sit
between the bus and the stored energy:

    charging      E ← E + E_in · η_charge        the bus gives E_in
    discharging   E ← E − E_out / η_discharge    the bus gets E_out

The stored energy stays in [SoC_min · C, SoC_max · C]. Seen from the bus, the
battery can take (E_max − E) / η_charge and give (E − E_min) · η_discharge, and
at most ``max_power_kw · step_hours`` either way.
"""

from __future__ import annotations

from dataclasses import replace

from core.config.scenario import BatterySetup


class Battery:
    """One participant's battery during a market day.

    Args:
        setup: Capacity, state-of-charge limits, efficiencies and power limit
            (``BatterySetup``), copied so later edits to the caller's settings
            do not change this battery. Stored energy is kept separately.
        step_hours: Length of a market step, for the power limit.
    """

    def __init__(
        self,
        setup: BatterySetup,
        step_hours: float,
    ) -> None:
        self.setup = replace(setup)
        self.step_hours = step_hours
        problems = self.setup.problems()

        if problems:
            raise ValueError("Battery: " + "; ".join(problems))

        self.reset()

    def reset(self) -> None:
        """Back to the initial state of charge."""
        self.energy_kwh = self.setup.initial_soc * self.setup.capacity_kwh

    # --- State -----------------------------------------------------------------------
    @property
    def min_kwh(self) -> float:
        """Lowest energy the battery may hold."""
        return self.setup.min_soc * self.setup.capacity_kwh

    @property
    def max_kwh(self) -> float:
        """Highest energy the battery may hold."""
        return self.setup.max_soc * self.setup.capacity_kwh

    @property
    def soc(self) -> float:
        """State of charge, 0 to 1."""
        return self.energy_kwh / self.setup.capacity_kwh

    # --- What it can take or give this step (eq. 15c-d) ------------------------------
    def _power_cap_kwh(self) -> float:
        if self.setup.max_power_kw is None:
            return float("inf") # OPEN MP-1d: why inf here?
        return self.setup.max_power_kw * self.step_hours

    @property
    def chargeable_kwh(self) -> float:
        """Energy the battery can still take from the bus this step ([P1] eq. 15d,
        with η_charge and the power limit)."""
        room = max(0.0, self.max_kwh - self.energy_kwh) / self.setup.charge_efficiency
        return min(room, self._power_cap_kwh())

    @property
    def dischargeable_kwh(self) -> float:
        """Energy the battery can still give to the bus this step ([P1] eq. 15c,
        with η_discharge and the power limit)."""
        room = (
            max(0.0, self.energy_kwh - self.min_kwh) * self.setup.discharge_efficiency
        )
        return min(room, self._power_cap_kwh())

    # --- Charging and discharging (eq. 16) -------------------------------------------
    def charge(self, kwh: float) -> float:
        """Take up to ``kwh`` from the bus; returns what it took."""
        taken = min(max(0.0, kwh), self.chargeable_kwh)
        # [P1] eq. 16, charging: min(E + E_in · η_charge, SoC_max · C)
        self.energy_kwh = min(
            self.max_kwh, self.energy_kwh + taken * self.setup.charge_efficiency
        )

        return taken

    def discharge(self, kwh: float) -> float:
        """Give up to ``kwh`` to the bus; returns what it gave."""
        given = min(max(0.0, kwh), self.dischargeable_kwh)
        # [P1] eq. 16, discharging: max(E − E_out / η_discharge, SoC_min · C)
        self.energy_kwh = max(
            self.min_kwh, self.energy_kwh - given / self.setup.discharge_efficiency
        )

        return given
