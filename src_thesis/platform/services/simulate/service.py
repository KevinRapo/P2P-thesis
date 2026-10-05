"""SimulateService: builds simulation runs from a draft, a controller and days.

A simulation run is an ordinary run folder (kind ``simulate``); starting, watching
and cancelling it is ``ExperimentService``'s job. Flow of the page:
``studio/pages/simulate/page.py``.
"""

from __future__ import annotations

from src_thesis.marlem.simulation.catalog import CONTROLLERS
from src_thesis.platform.kernel.models import expand as expansion
from src_thesis.platform.kernel.models.files import canonical_hash
from src_thesis.platform.kernel.models.manifest import build_manifest
from src_thesis.platform.kernel.models.resolve import resolve_run
from src_thesis.platform.kernel.store.filesystem import (
    ExperimentStore,
    RunExistsError,
)
from src_thesis.platform.services.models import ExperimentFile, RunCell
from src_thesis.platform.services.simulate.models import (
    ControllerInfo,
    ControllerParam,
)
from src_thesis.platform.services.workspace import Workspace


class SimulateService:
    """Controllers and simulation runs.

    Args:
        workspace: Where the store lives; the default workspace when ``None``.
    """

    SAMPLE_DATA = False

    def __init__(self, workspace: Workspace | None = None) -> None:
        self.workspace = workspace or Workspace.default()
        self.store = ExperimentStore(self.workspace.store)

    def controllers(self) -> list[ControllerInfo]:
        """The scripted controllers a simulation can use, with their parameters."""
        return [
            ControllerInfo(
                name=spec.name,
                title=spec.title,
                description=spec.description,
                params=[
                    ControllerParam(
                        name=name,
                        label=p.label,
                        default=p.default,
                        low=p.low,
                        high=p.high,
                        help=p.help,
                    )
                    for name, p in spec.params.items()
                ],
            )
            for spec in CONTROLLERS.values()
        ]

    def create_simulation(
        self,
        file: ExperimentFile,
        controller: str,
        params: dict[str, float] | None = None,
        day: str | None = None,
        days: int = 1,
        seed: int = 1,
    ) -> str:
        """Write a run folder (state READY) that plays ``days`` days with a controller.

        Args:
            file: The experiment file (a draft is fine).
            controller: One of ``controllers()``.
            params: The controller's parameters.
            day: First day, ``YYYY-MM-DD``; the start of the time window when
                ``None``.
            days: Number of consecutive days.
            seed: Seed of the first day.

        Returns:
            The new run ID.

        Raises:
            ValueError: Unknown controller or parameter, or a value out of range.
        """
        if controller not in CONTROLLERS:
            raise ValueError(f"Unknown controller {controller!r}")
        params = {k: float(v) for k, v in (params or {}).items()}
        for key, value in params.items():
            spec = CONTROLLERS[controller].params.get(key)
            if spec is None:
                raise ValueError(f"{controller} has no parameter {key!r}")
            if not spec.low <= value <= spec.high:
                raise ValueError(f"{key} must be between {spec.low} and {spec.high}")
        label = f"sim-{day or 'start'}-{days}d"
        for attempt in range(1, 100):
            cell = RunCell(
                kind="simulate",
                sweep_label=label if attempt == 1 else f"{label}-r{attempt}",
                algorithm=controller,
                paradigm="-",
                seed=seed,
                controller_params=params,
                day=day,
                days=days,
            )
            resolved = resolve_run(file, cell)
            run_id = expansion.run_id(file.meta.id, cell, canonical_hash(file))
            try:
                self.store.create_run(
                    file, resolved, build_manifest(file, resolved, cell, run_id)
                )
            except RunExistsError:
                continue
            return run_id
        raise RuntimeError("too many runs with the same settings")
