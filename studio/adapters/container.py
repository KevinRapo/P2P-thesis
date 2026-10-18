"""The services every caller uses, built in one place.

    grid_catalog_service  GridCatalogService   networks via pandapower
    profile_service       ProfileService       SimBench profiles
    scenario_service      ScenarioService      the scenario: saved, participants placed
    market_service        MarketService        the market being stepped
    run_service           RunService           the experiments of this PC and a cluster
    results_service       ResultsService       finished runs, to compare

None of these modules loads pandapower when imported (the adapter imports it
inside functions).
"""

from dataclasses import dataclass
from pathlib import Path

from studio.adapters.workspace import Workspace
from studio.adapters.grid_catalog_service import GridCatalogService
from studio.adapters.market_service import MarketService
from studio.adapters.profile_service import ProfileService
from studio.adapters.results_service import ResultsService
from studio.adapters.run_service import RunService
from studio.adapters.scenario_service import ScenarioService

# The scenario files the Studio offers to open: the repository's scenarios/ folder.
SCENARIO_LIBRARY = Path(__file__).resolve().parents[2] / "scenarios"


@dataclass(frozen=True)
class Services:
    """The services a caller uses.

    Attributes:
        grid: Network catalog.
        profiles: SimBench profiles of networks and the catalogue.
        scenario: The scenario being edited.
        market: The market built from it, stepped by the Step page.
        runs: The training experiments on this PC and on a cluster, and starting
            them (the Runs page).
        results: The finished runs, to compare (the Results page).
    """

    grid: GridCatalogService
    profiles: ProfileService
    scenario: ScenarioService
    market: MarketService
    runs: RunService
    results: ResultsService


def build_services(home: Path | None = None) -> Services:
    """Build all services.

    Args:
        home: Workspace folder; default outside OneDrive (``studio/adapters/workspace.py``).
    """
    workspace = Workspace(home) if home else Workspace.default()
    return Services(
        grid=GridCatalogService(cache=workspace.network_cache),
        profiles=ProfileService(),
        scenario=ScenarioService(workspace.scenario_file, SCENARIO_LIBRARY),
        market=MarketService(),
        runs=RunService(),
        results=ResultsService(),
    )
