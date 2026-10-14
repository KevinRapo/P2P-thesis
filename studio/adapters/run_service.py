"""RunService: what the Runs page reads about training experiments.

A thin wrapper over ``core.runner``: ``registry`` (a read-only view of ``runs/``) and
``launch.stop``. Everything is read from files at each call, so the page can ask every
couple of seconds and sees what ``python -m core.runner status`` shows. The registry's
records (``RunState``) are returned as they are.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.runner import launch, registry
from core.runner.registry import RunState
from core.runner.spec import runs_root


# --------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------
class RunService:
    """The experiments in ``runs/`` and their runs.

    Args:
        root: The folder with the experiments; default ``$MARLEM_RUNS`` or
            ``<repo>/runs``, looked up at each call.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = Path(root) if root else None

    @property
    def root(self) -> Path:
        return self._root or runs_root()

    # --- Reading ---------------------------------------------------------------------
    def experiments(self) -> list[str]:
        """Names of the experiments, the most recently changed folder first."""
        root = self.root

        def changed(name: str) -> float:
            try:
                return (root / name).stat().st_mtime
            except OSError:
                return 0.0

        return sorted(registry.experiments(root), key=changed, reverse=True)

    def runs(self, experiment: str) -> list[RunState]:
        """The runs of an experiment with their states, in the order of its grid."""
        return registry.runs(experiment, self.root)

    def spec(self, experiment: str) -> Optional[dict]:
        """The experiment's ``experiment.json`` (None for runs made without the
        runner)."""
        return registry.read_json(self.root / experiment / "experiment.json")

    def worker_alive(self, experiment: str) -> bool:
        """Whether the experiment's worker process is still running."""
        return registry.worker_alive(self.root / experiment)

    # --- Stopping --------------------------------------------------------------------
    def stop(self, experiment: str, run: Optional[str] = None) -> dict:
        """Stop a whole experiment, or one run of it (see ``launch.stop``). Kills
        processes, so it can take a few seconds."""
        return launch.stop(experiment, run, self.root)
