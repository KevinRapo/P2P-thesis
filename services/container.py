"""The services every caller uses, built in one place.

    grid_catalog_service  GridCatalogService   networks via pandapower
    profile_service       ProfileService       SimBench profiles

None of these modules loads pandapower when imported (the adapter imports it
inside functions).
"""

from dataclasses import dataclass
from pathlib import Path

from services.grid_catalog_service import GridCatalogService
from services.profile_service import ProfileService
from services.workspace import Workspace


@dataclass(frozen=True)
class Services:
    """The services a caller uses.

    Attributes:
        grid: Network catalog.
        profiles: SimBench profiles of networks and the catalogue.
    """

    grid: GridCatalogService
    profiles: ProfileService


def build_services(home: Path | None = None) -> Services:
    """Build all services.

    Args:
        home: Workspace folder; default outside OneDrive (``workspace.py``).
    """
    workspace = Workspace(home) if home else Workspace.default()
    return Services(
        grid=GridCatalogService(cache=workspace.network_cache),
        profiles=ProfileService(),
    )
