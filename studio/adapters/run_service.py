"""RunService: what the Runs page reads about training experiments, and what it starts.

A thin wrapper over ``core.runner``. An experiment runs on a **target** (``targets.py``,
named in ``hpc/targets.toml``): this PC, or a cluster driven over SSH. The service holds
one target object per name for the life of the Studio (a cluster's target keeps its SSH
connection open) and passes the calls on: ``overview``, ``check``, ``start``, ``stop``,
``sync``. The runner's records (the target's entries and report) are returned as they
are; every method is synchronous and may take seconds on a cluster, so the pages call
them through ``run.io_bound``.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from core.runner import targets
from core.runner.spec import REPO, Experiment


# --------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------
class RunService:
    """The experiments of the targets and their runs.

    Args:
        root: The folder with this PC's experiments; default ``$MARLEM_RUNS`` or
            ``<repo>/runs``.
        specs: The folder with the experiment specs; default ``<repo>/experiments``.
    """

    def __init__(
        self, root: Optional[Path] = None, specs: Optional[Path] = None
    ) -> None:
        self._root = Path(root) if root else None
        self._specs = Path(specs) if specs else REPO / "experiments"
        self._targets: dict[str, targets.Target] = {}
        self._made = threading.Lock()  # a target is made once, from whichever thread
        self._syncing = threading.Lock()  # one copy at a time: ``copied`` is per target

    # --- Targets ---------------------------------------------------------------------
    def target_names(self) -> list[tuple[str, str]]:
        """``(name, label)`` of every target in ``targets.toml``: the label is its
        ``label`` there, else its name."""
        return [
            (name, cfg.get("label", name)) for name, cfg in targets.settings().items()
        ]

    def target(self, name: str) -> targets.Target:
        """The target called ``name``, made on first use and kept (nothing connects
        until a call needs it)."""
        with self._made:
            if name not in self._targets:
                # ``root`` is this PC's folder; a cluster keeps its own copy elsewhere.
                root = self._root if name == "local" else None
                self._targets[name] = targets.get(name, root=root)
            return self._targets[name]

    def close(self) -> None:
        """Close every target made (the SSH connections)."""
        with self._made:
            made, self._targets = list(self._targets.values()), {}
        for target in made:
            target.close()

    # --- On a target -----------------------------------------------------------------
    def overview(self, target: str) -> list[dict]:
        """Every experiment of the target with its summary, runs and spec (see
        ``Target.overview``), the most recently changed first."""
        entries = self.target(target).overview()
        return sorted(
            entries, key=lambda entry: entry.get("modified", 0.0), reverse=True
        )

    def check(self, target: str, spec: Optional[targets.Spec] = None) -> dict:
        """Whether the target is ready (with ``spec``, a file or an ``Experiment``: to
        start that experiment), as the report of ``Target.check``."""
        return self.target(target).check(spec)

    def start(self, target: str, spec: targets.Spec, profile: str = "full") -> str:
        """Queue and start the experiment ``spec`` (a file or an ``Experiment``;
        ``profile`` ``"full"`` or ``"test"``); returns its name. It checks first and
        raises ``TargetError`` with the problems if the target is not ready."""
        return self.target(target).start(spec, profile)

    def stop(self, target: str, experiment: str, run: Optional[str] = None) -> dict:
        """Stop a whole experiment, or one run of it (see ``Target.stop``). Kills
        processes or cancels SLURM tasks, so it can take a few seconds."""
        return self.target(target).stop(experiment, run)

    def sync(self, target: str, experiment: str) -> tuple[Optional[Path], int]:
        """Copy the experiment's results to this PC: ``(folder, files copied)``. On this
        PC the files are there already: 0 copied."""
        with self._syncing:
            found = self.target(target)
            folder = found.sync(experiment)
            return folder, found.copied or 0

    # --- Experiment specs ------------------------------------------------------------
    def spec_files(self) -> list[dict]:
        """The specs in the specs folder, by file name, with what the start dialog
        shows. Each: ``path``, ``name``, ``description``, ``runs`` (of the full
        experiment) and ``test_runs``, ``budget`` and ``test_budget`` (environment steps
        per run, an int or one per algorithm), ``resources`` and ``test_resources``
        (cpus, mem_gb and minutes per run on a cluster) and ``error``: why the file does
        not load (the other fields are then None)."""
        found = []
        for path in sorted(self._specs.glob("*.json")):
            record: dict = {
                "path": path,
                "name": path.stem,
                "description": None,
                "runs": None,
                "test_runs": None,
                "budget": None,
                "test_budget": None,
                "resources": None,
                "test_resources": None,
                "error": None,
            }
            try:
                experiment = Experiment.load(path)
                test = experiment.test_version()
            except (OSError, ValueError) as error:  # a SpecError is a ValueError
                record["error"] = str(error)
            else:
                record |= {
                    "name": experiment.name,
                    "description": experiment.description,
                    "runs": len(experiment.expand()),
                    "test_runs": len(test.expand()),
                    "budget": experiment.budget,
                    "test_budget": test.budget,
                    "resources": experiment.run_resources,
                    "test_resources": test.run_resources,
                }
            found.append(record)
        return found
