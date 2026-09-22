"""Facade for scenario authoring and persistence.

This module intentionally contains no scenario behavior yet. The service will
be the stable entry point for NiceGUI, the CLI, and experiment creation.
"""

from pathlib import Path
from typing import Any


class ScenarioService:
    """Create, load, normalize, clone, and save scenario specifications."""

    def create(self, request: Any) -> Any:
        raise NotImplementedError

    def load(self, scenario_id: str) -> Any:
        raise NotImplementedError

    def save(self, scenario: Any, path: Path) -> None:
        raise NotImplementedError

    def clone(self, scenario_id: str, name: str) -> Any:
        raise NotImplementedError
