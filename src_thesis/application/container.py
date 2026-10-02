"""Wiring of service implementations.

Callers (Studio, CLI, notebooks) obtain every service through `build_services`
and depend only on the protocols in `contracts.py`. Switching from the demo to
the real implementations later changes this module only.

Real implementations replace demo ones one service at a time, in roadmap order,
each behind its own switch: the grid catalog (phase R3) and the experiment-file
service (R7) so far. Real services are imported lazily, so
`build_services("demo")` never loads pandapower.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .contracts import (
    ConfigService,
    ExperimentService,
    GridCatalogService,
    ProfileService,
    ResultService,
    ValidationService,
)

GridBackend = Literal["demo", "pandapower"]
ConfigBackend = Literal["demo", "files"]


@dataclass(frozen=True)
class Services:
    """The six services a caller uses, and which implementation is behind them.

    Attributes:
        config: Experiment files.
        grid: Network catalog.
        profiles: Profiles and participant mapping.
        validation: Preflight checks.
        experiments: Runs.
        results: Reading results.
        mode: ``"demo"`` until every service is real (R7).
        grid_backend: ``"pandapower"`` when the grid catalog is real.
        config_backend: ``"files"`` when experiment files are real.
    """

    config: ConfigService
    grid: GridCatalogService
    profiles: ProfileService
    validation: ValidationService
    experiments: ExperimentService
    results: ResultService
    mode: str
    grid_backend: GridBackend = "demo"
    config_backend: ConfigBackend = "demo"


def build_services(
    mode: Literal["demo", "real"] = "demo",
    grid: GridBackend = "demo",
    config: ConfigBackend = "demo",
    home: Path | None = None,
) -> Services:
    """Build all services.

    Args:
        mode: "demo" for sample data everywhere; "real" is reserved for R6–R7.
        grid: "pandapower" swaps in the real grid catalog (SimBench and
            pandapower built-in networks) while the other services stay demo.
        config: "files" swaps in the real ConfigService: presets from the
            repository, the user's files in the workspace library.
        home: workspace folder; default outside OneDrive (``workspace.py``).
    """
    if mode != "demo":
        raise NotImplementedError(
            "Real services are implemented in roadmap phases R6-R7 "
            "(docs_thesis/thesis/architecture/README.md §4)."
        )
    from .demo import (
        DemoConfigService,
        DemoExperimentService,
        DemoGridCatalogService,
        DemoProfileService,
        DemoResultService,
        DemoValidationService,
    )

    if grid == "pandapower":
        from .grid_catalog import PandapowerGridCatalogService

        grid_service: GridCatalogService = PandapowerGridCatalogService()
    else:
        grid_service = DemoGridCatalogService()

    if config == "files":
        from .config_files import FileConfigService
        from .workspace import Workspace

        workspace = Workspace(home) if home else Workspace.default()
        config_service: ConfigService = FileConfigService(workspace)
    else:
        config_service = DemoConfigService()

    return Services(
        config=config_service,
        grid=grid_service,
        profiles=DemoProfileService(),
        validation=DemoValidationService(),
        experiments=DemoExperimentService(),
        results=DemoResultService(),
        mode="demo",
        grid_backend=grid,
        config_backend=config,
    )
