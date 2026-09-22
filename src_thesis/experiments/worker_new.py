"""Worker-process entry boundary for long-running experiments."""

from typing import Any


class ExperimentWorker:
    """Own Ray, simulation execution, logs, and progress for one run."""

    def run(self, run_id: str, scenario: Any) -> None:
        raise NotImplementedError
