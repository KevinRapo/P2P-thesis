"""Facade for portable experiment-directory persistence."""

from typing import Any


class ExperimentStore:
    """Persist scenarios, manifests, status, logs, and result indexes."""

    def write(self, run_id: str, name: str, value: Any) -> None:
        raise NotImplementedError

    def read(self, run_id: str, name: str) -> Any:
        raise NotImplementedError
