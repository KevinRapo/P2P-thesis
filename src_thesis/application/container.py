"""The services every caller uses, built in one place.

Callers (Studio, CLI, notebooks) obtain every service through ``build_services``.
Each service is one class in its own module:

    config_service        ConfigService        experiment files (built)
    grid_catalog_service  GridCatalogService   networks via pandapower (built)
    profile_service       ProfileService       sample data until R3
    validation_service    ValidationService    sample data until R6-R7
    experiment_service    ExperimentService    sample data until R7
    result_service        ResultService        sample data until R7

A service is built by replacing its sample method bodies with the real ones, in
the same class; ``SAMPLE_DATA`` on the class says whether any are left. None of
these modules loads pandapower when imported (the adapter imports it inside
functions).
"""

from dataclasses import dataclass, fields
from pathlib import Path

from src_thesis.env import load_env

load_env()  # MARLEM_HOME and the other settings from .env, for every caller

from src_thesis.application.config_service import ConfigService  # noqa: E402
from src_thesis.application.experiment_service import ExperimentService  # noqa: E402
from src_thesis.application.grid_catalog_service import (  # noqa: E402
    GridCatalogService,
)
from src_thesis.application.profile_service import ProfileService  # noqa: E402
from src_thesis.application.result_service import ResultService  # noqa: E402
from src_thesis.application.validation_service import (  # noqa: E402
    ValidationService,
)
from src_thesis.application.workspace import Workspace  # noqa: E402


@dataclass(frozen=True)
class Services:
    """The six services a caller uses.

    Attributes:
        config: Experiment files.
        grid: Network catalog.
        profiles: Profiles and participant mapping.
        validation: Preflight checks.
        experiments: Runs.
        results: Reading results.
    """

    config: ConfigService
    grid: GridCatalogService
    profiles: ProfileService
    validation: ValidationService
    experiments: ExperimentService
    results: ResultService

    def sample_data(self) -> list[str]:
        """Names of the services that still return sample data (for the Studio)."""
        return [
            f.name for f in fields(self) if getattr(self, f.name).SAMPLE_DATA is True
        ]


def build_services(home: Path | None = None) -> Services:
    """Build all services.

    Args:
        home: Workspace folder; default outside OneDrive (``workspace.py``).
    """
    workspace = Workspace(home) if home else Workspace.default()
    return Services(
        config=ConfigService(workspace),
        grid=GridCatalogService(cache=workspace.network_cache),
        profiles=ProfileService(),
        validation=ValidationService(),
        experiments=ExperimentService(),
        results=ResultService(),
    )
