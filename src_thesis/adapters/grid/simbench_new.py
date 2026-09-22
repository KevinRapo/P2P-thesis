"""Facade for the future SimBench/pandapower grid adapter.

No SimBench or pandapower code is implemented yet. This module reserves the
replaceable infrastructure boundary without exposing those libraries to the
marketplace, services, or UI.
"""

from typing import Any, Mapping

from src_thesis.marketplace.grid.contract_new import GridAssessment


class SimBenchGrid:
    """Future adapter for SimBench network loading and pandapower assessment."""

    def __init__(self, grid_spec: Any) -> None:
        raise NotImplementedError

    def reset(self, seed: int | None = None) -> None:
        raise NotImplementedError

    def map_participants(self, participant_bus: Mapping[str, str]) -> None:
        raise NotImplementedError

    def assess(
        self,
        injections: Mapping[str, float],
        timestep_hours: float,
    ) -> GridAssessment:
        raise NotImplementedError
