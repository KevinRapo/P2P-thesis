"""Wiring of service implementations.

Callers (Studio, CLI, notebooks) obtain every service through `build_services`
and depend only on the protocols in `contracts.py`. Switching from the demo to
the real implementations later changes this module only.

Real implementations replace demo ones one service at a time, in roadmap order:
the grid catalog (phase P3) is the first. Real services are imported lazily, so
`build_services("demo")` never loads pandapower.
"""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class Services:
    config: ConfigService
    grid: GridCatalogService
    profiles: ProfileService
    validation: ValidationService
    experiments: ExperimentService
    results: ResultService
    mode: str
    grid_backend: GridBackend = "demo"


def build_services(
    mode: Literal["demo", "real"] = "demo", grid: GridBackend = "demo"
) -> Services:
    """Build all services.

    Args:
        mode: "demo" for sample data everywhere; "real" is reserved for P6–P7.
        grid: "pandapower" swaps in the real grid catalog (SimBench and
            pandapower built-in networks) while the other services stay demo.
    """
    if mode != "demo":
        raise NotImplementedError(
            "Real services are implemented in roadmap phases P6-P7 "
            "(docs/thesis/architecture/README.md §4)."
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

    return Services(
        config=DemoConfigService(),
        grid=grid_service,
        profiles=DemoProfileService(),
        validation=DemoValidationService(),
        experiments=DemoExperimentService(),
        results=DemoResultService(),
        mode="demo",
        grid_backend=grid,
    )
