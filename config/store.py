"""Saving and loading scenarios as JSON files."""

from __future__ import annotations

from pathlib import Path

from config.scenario import Scenario


def load(path: Path) -> Scenario:
    """The scenario saved at ``path``."""
    raise NotImplementedError


def save(scenario: Scenario, path: Path) -> None:
    """Write ``scenario`` to ``path``."""
    raise NotImplementedError
