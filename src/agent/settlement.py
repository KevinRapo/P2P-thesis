"""Physical household settlement at the grid-side energy boundary (kWh)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EnergySettlement:
    step: int
    generation: float
    demand: float
    imported: float
    exported: float
    battery_charge: float
    battery_discharge: float
    battery_loss: float
    stored_before: float
    stored_after: float
    served_demand: float
    unserved_demand: float
    curtailed_generation: float

    @property
    def balance_error(self) -> float:
        """Zero when grid-side sources and sinks reconcile."""
        return (self.generation + self.imported + self.battery_discharge
                - self.served_demand - self.exported - self.battery_charge
                - self.curtailed_generation)

    @property
    def storage_error(self) -> float:
        return (self.stored_before + self.battery_charge - self.battery_discharge
                - self.battery_loss - self.stored_after)
