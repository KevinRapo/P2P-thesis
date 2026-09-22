"""Technology-neutral grid contract used by application and market code.

Only data contracts and method signatures live here initially. The existing
NetworkX implementation remains available through its legacy adapter until
the boundary has been characterized.
"""

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class GridViolation:
    """A physical-grid constraint violation reported by an adapter."""

    code: str
    message: str
    element_id: str | None = None


@dataclass(frozen=True)
class GridAssessment:
    """Technology-neutral result of assessing one simulation step."""

    converged: bool
    total_losses_kwh: float
    bus_voltages_pu: Mapping[str, float]
    line_loading_percent: Mapping[str, float]
    transformer_loading_percent: Mapping[str, float]
    violations: Sequence[GridViolation]


class GridModel(Protocol):
    """Interface implemented by legacy and SimBench grid adapters."""

    def reset(self, seed: int | None = None) -> None: ...

    def map_participants(self, participant_bus: Mapping[str, str]) -> None: ...

    def assess(
        self,
        injections: Mapping[str, float],
        timestep_hours: float,
    ) -> GridAssessment: ...
