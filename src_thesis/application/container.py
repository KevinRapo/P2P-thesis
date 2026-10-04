"""Wiring of service implementations.

Callers (Studio, CLI, notebooks) obtain every service through `build_services`
and depend only on the service protocols. Each service has one module holding its
protocol, its final implementation and its demo implementation:

    config_service        FileConfigService (final)           DemoConfigService
    grid_catalog_service  PandapowerGridCatalogService (final) DemoGridCatalogService
    profile_service       SimBenchProfileService (not built)   DemoProfileService
    validation_service    PreflightValidationService (not built) DemoValidationService
    experiment_service    StoreExperimentService (not built)   DemoExperimentService
    result_service        StoreResultService (not built)       DemoResultService

Final implementations replace demo ones one service at a time, each behind its
own switch: the grid catalog and the experiment files so far. None of these
modules loads pandapower when imported (the adapter imports it inside functions).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src_thesis.env import load_env

load_env()  # MARLEM_HOME and the other settings from .env, for every caller

from src_thesis.application.config_service import (  # noqa: E402
    ConfigService,
    DemoConfigService,
    FileConfigService,
)
from src_thesis.application.experiment_service import (  # noqa: E402
    DemoExperimentService,
    ExperimentService,
)
from src_thesis.application.grid_catalog_service import (  # noqa: E402
    DemoGridCatalogService,
    GridCatalogService,
    PandapowerGridCatalogService,
)
from src_thesis.application.profile_service import (  # noqa: E402
    DemoProfileService,
    ProfileService,
)
from src_thesis.application.result_service import (  # noqa: E402
    DemoResultService,
    ResultService,
)
from src_thesis.application.validation_service import (  # noqa: E402
    DemoValidationService,
    ValidationService,
)
from src_thesis.application.workspace import Workspace  # noqa: E402

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
    if grid == "pandapower":
        grid_service: GridCatalogService = PandapowerGridCatalogService()
    else:
        grid_service = DemoGridCatalogService()

    if config == "files":
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
