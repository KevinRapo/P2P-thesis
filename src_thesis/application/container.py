"""Wiring of service implementations.

Callers (Studio, CLI, notebooks) obtain every service through `build_services`
and depend only on the protocols in `contracts.py`. Switching from the demo to
the real implementations later changes this module only.
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


@dataclass(frozen=True)
class Services:
    config: ConfigService
    grid: GridCatalogService
    profiles: ProfileService
    validation: ValidationService
    experiments: ExperimentService
    results: ResultService
    mode: str


def build_services(mode: Literal["demo", "real"] = "demo") -> Services:
    if mode == "demo":
        from .demo import (
            DemoConfigService,
            DemoExperimentService,
            DemoGridCatalogService,
            DemoProfileService,
            DemoResultService,
            DemoValidationService,
        )

        return Services(
            config=DemoConfigService(),
            grid=DemoGridCatalogService(),
            profiles=DemoProfileService(),
            validation=DemoValidationService(),
            experiments=DemoExperimentService(),
            results=DemoResultService(),
            mode="demo",
        )
    raise NotImplementedError(
        "Real services are implemented in roadmap phases P6-P7 "
        "(docs/thesis/architecture/README.md §4)."
    )
