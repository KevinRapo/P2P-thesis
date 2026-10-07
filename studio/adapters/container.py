"""The services every caller uses, built in one place.

    grid_catalog_service  GridCatalogService   networks via pandapower
    profile_service       ProfileService       SimBench profiles
    scenario_service      ScenarioService      the scenario: saved, participants placed
    market_service        MarketService        the market being stepped

None of these modules loads pandapower when imported (the adapter imports it
inside functions).
"""

from dataclasses import dataclass
from pathlib import Path

from studio.adapters.workspace import Workspace
from studio.adapters.grid_catalog_service import GridCatalogService
from studio.adapters.market_service import MarketService
from studio.adapters.profile_service import ProfileService
from studio.adapters.scenario_service import ScenarioService


@dataclass(frozen=True)
class Services:
    """The services a caller uses.

    Attributes:
        grid: Network catalog.
        profiles: SimBench profiles of networks and the catalogue.
        scenario: The scenario being edited.
        market: The market built from it, stepped by the Step page.
    """

    grid: GridCatalogService
    profiles: ProfileService
    scenario: ScenarioService
    market: MarketService


def build_services(home: Path | None = None) -> Services:
    """Build all services.

    Args:
        home: Workspace folder; default outside OneDrive (``studio/adapters/workspace.py``).
    """
    workspace = Workspace(home) if home else Workspace.default()
    return Services(
        grid=GridCatalogService(cache=workspace.network_cache),
        profiles=ProfileService(),
        scenario=ScenarioService(workspace.scenario_file),
        market=MarketService(),
    )
