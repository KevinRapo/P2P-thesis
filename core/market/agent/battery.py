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

from typing import Optional


class Battery:
    """One participant's battery during a market day.

    Args:
        capacity_kwh: Nominal capacity C.
        min_soc: Lowest state of charge, 0 to 1.
        max_soc: Highest state of charge, 0 to 1.
        charge_efficiency: Share of the energy taken from the bus that is stored.
        discharge_efficiency: Share of the stored energy taken out that reaches the
            bus.
        initial_soc: State of charge at the start of the day.
        max_power_kw: Charging and discharging power limit (``None``: no limit).
            [P1] §3.4 names rate limits, but eq. 16 has none.
        step_hours: Length of a market step, for the power limit.
    """

    def __init__(
        self,
        capacity_kwh: float,
        min_soc: float,
        max_soc: float,
        charge_efficiency: float,
        discharge_efficiency: float,
        initial_soc: float,
        max_power_kw: Optional[float],
        step_hours: float,
    ) -> None:
        self.capacity_kwh = capacity_kwh
        self.min_soc = min_soc
        self.max_soc = max_soc
        self.charge_efficiency = charge_efficiency
        self.discharge_efficiency = discharge_efficiency
        self.initial_soc = initial_soc
        self.max_power_kw = max_power_kw
        self.step_hours = step_hours
        self._check()
        self.energy_kwh = 0.0
        self.reset()

    def _check(self) -> None:
        """Reject a battery eq. 16 cannot run: no capacity, an empty or out-of-range
        state-of-charge window, an efficiency outside (0, 1], a start outside the
        window, a power limit that is not positive."""
        problems = []

        if self.capacity_kwh <= 0:
            problems.append(f"capacity {self.capacity_kwh} kWh is not positive")

        if not 0 <= self.min_soc < self.max_soc <= 1:
            problems.append(
                f"SoC window {self.min_soc}-{self.max_soc} is not inside 0-1"
            )

        for name in ("charge_efficiency", "discharge_efficiency"):
            if not 0 < getattr(self, name) <= 1:
                problems.append(f"{name} {getattr(self, name)} is not in (0, 1]")

        if not self.min_soc <= self.initial_soc <= self.max_soc:
            problems.append(f"initial SoC {self.initial_soc} is outside the window")

        if self.max_power_kw is not None and self.max_power_kw <= 0:
            problems.append(f"power limit {self.max_power_kw} kW is not positive")

        if problems:
            raise ValueError("Battery: " + "; ".join(problems))

    def reset(self) -> None:
        """Back to the initial state of charge."""
        self.energy_kwh = self.initial_soc * self.capacity_kwh

    # --- State -----------------------------------------------------------------------
    @property
    def min_kwh(self) -> float:
        """Lowest energy the battery may hold."""
        return self.min_soc * self.capacity_kwh

    @property
    def max_kwh(self) -> float:
        """Highest energy the battery may hold."""
        return self.max_soc * self.capacity_kwh

    @property
    def soc(self) -> float:
        """State of charge, 0 to 1."""
        return self.energy_kwh / self.capacity_kwh

    # --- What it can take or give this step (eq. 15c-d) ------------------------------
    def _power_cap_kwh(self) -> float:
        if self.max_power_kw is None:
            return float("inf")
        return self.max_power_kw * self.step_hours

    @property
    def chargeable_kwh(self) -> float:
        """Energy the battery can still take from the bus this step ([P1] eq. 15d,
        with η_charge and the power limit)."""
        room = max(0.0, self.max_kwh - self.energy_kwh) / self.charge_efficiency
        return min(room, self._power_cap_kwh())

    @property
    def dischargeable_kwh(self) -> float:
        """Energy the battery can still give to the bus this step ([P1] eq. 15c,
        with η_discharge and the power limit)."""
        room = max(0.0, self.energy_kwh - self.min_kwh) * self.discharge_efficiency
        return min(room, self._power_cap_kwh())

    # --- Charging and discharging (eq. 16) -------------------------------------------
    def charge(self, kwh: float) -> float:
        """Take up to ``kwh`` from the bus; returns what it took."""
        taken = min(max(0.0, kwh), self.chargeable_kwh)
        # [P1] eq. 16, charging: min(E + E_in · η_charge, SoC_max · C)
        self.energy_kwh = min(
            self.max_kwh, self.energy_kwh + taken * self.charge_efficiency
        )

        return taken

    def discharge(self, kwh: float) -> float:
        """Give up to ``kwh`` to the bus; returns what it gave."""
        given = min(max(0.0, kwh), self.dischargeable_kwh)
        # [P1] eq. 16, discharging: max(E − E_out / η_discharge, SoC_min · C)
        self.energy_kwh = max(
            self.min_kwh, self.energy_kwh - given / self.discharge_efficiency
        )

        return given
