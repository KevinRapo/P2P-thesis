"""Facade for experiment lifecycle management."""

from typing import Any


class ExperimentService:
    """Create runs, start or cancel workers, and query run status."""

    def create_run(self, scenario_id: str) -> Any:
        raise NotImplementedError

    def start(self, run_id: str) -> Any:
        raise NotImplementedError

    def cancel(self, run_id: str) -> Any:
        raise NotImplementedError

    def status(self, run_id: str) -> Any:
        raise NotImplementedError
