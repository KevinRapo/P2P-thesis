"""Facade for constructing validated runtime components."""

from typing import Any


class ScenarioFactory:
    """Convert a validated scenario into MARLEM runtime objects."""

    def build(self, scenario: Any) -> Any:
        raise NotImplementedError


class GridAdapterFactory:
    """Select and construct the grid adapter named by a scenario."""

    def create(self, grid_spec: Any) -> Any:
        raise NotImplementedError
