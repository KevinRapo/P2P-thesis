"""The services every caller uses, built in one place.

Callers (Studio, CLI, notebooks) obtain every service through ``build_services``.
Each service is one class in its own module:

    config_service        ConfigService        experiment files (built)
    grid_catalog_service  GridCatalogService   networks via pandapower (built)
    profile_service       ProfileService       SimBench profiles (built)
    participant_service   ParticipantService   placement, previews (built)
    tariff_service        TariffService        DSO tariff CSVs (built)
    validation_service    ValidationService    file checks, dry run, scenarios (built)
    experiment_service    ExperimentService    runs, worker pool (built)
    result_service        ResultService        simulation runs built; curves, matrix, compare are samples

A service is built by replacing its sample method bodies with the real ones, in
the same class; ``SAMPLE_DATA`` on the class says whether any are left. None of
these modules loads pandapower when imported (the adapter imports it inside
functions).
"""

from dataclasses import dataclass, fields
from pathlib import Path

from src_thesis.platform.env import load_env

load_env()  # MARLEM_HOME and the other settings from .env, for every caller

from src_thesis.platform.services.config_service import ConfigService  # noqa: E402
from src_thesis.platform.services.experiment_service import (
    ExperimentService,
)  # noqa: E402
from src_thesis.platform.services.grid_catalog_service import (  # noqa: E402
    GridCatalogService,
)
from src_thesis.platform.services.participant_service import (  # noqa: E402
    ParticipantService,
)
from src_thesis.platform.services.profile_service import ProfileService  # noqa: E402
from src_thesis.platform.services.result_service import ResultService  # noqa: E402
from src_thesis.platform.services.tariff_service import TariffService  # noqa: E402
from src_thesis.platform.services.validation_service import (  # noqa: E402
    ValidationService,
)
from src_thesis.platform.services.workspace import Workspace  # noqa: E402


@dataclass(frozen=True)
class Services:
    """The services a caller uses.

    Attributes:
        config: Experiment files.
        grid: Network catalog.
        profiles: SimBench profiles of networks and the catalogue.
        participants: Placing and previewing participants.
        tariffs: DSO tariff CSVs.
        validation: Preflight checks.
        experiments: Runs.
        results: Reading results.
    """

    config: ConfigService
    grid: GridCatalogService
    profiles: ProfileService
    participants: ParticipantService
    tariffs: TariffService
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
        participants=ParticipantService(),
        tariffs=TariffService(),
        validation=ValidationService(),
        experiments=ExperimentService(workspace),
        results=ResultService(workspace),
    )
