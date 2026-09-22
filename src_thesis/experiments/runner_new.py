"""Facade for running an experiment inside an owned worker process."""

from typing import Any


class ExperimentRunner:
    """Coordinate one baseline, training, evaluation, or inference run."""

    def run(self, run_id: str, scenario: Any) -> Any:
        raise NotImplementedError
