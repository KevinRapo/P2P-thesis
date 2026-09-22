"""Facade for querying experiment results and derived artifacts."""

from typing import Any


class ResultService:
    """Return stable, UI-ready views over stored experiment results."""

    def summary(self, run_id: str) -> Any:
        raise NotImplementedError

    def artifacts(self, run_id: str) -> Any:
        raise NotImplementedError

    def series(self, run_id: str, name: str) -> Any:
        raise NotImplementedError
