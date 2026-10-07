"""MarketService: the market built from the scenario, stepped by the Step page.

Holds one ``MarketManager``. The Studio asks it to build the market from the
current scenario and then calls the manager's own methods to step it; the records
the manager returns are plain data.
"""

from __future__ import annotations

from copy import deepcopy

from config.scenario import Scenario
from market.manager import MarketManager


# --------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------
class MarketService:
    """The market being stepped."""

    def __init__(self) -> None:
        self.manager: MarketManager | None = None

    def build(self, scenario: Scenario) -> MarketManager:
        """A fresh market from a copy of ``scenario`` (later edits to the scenario
        do not change a market being played), reset to step 0."""
        manager = MarketManager(deepcopy(scenario))
        manager.reset()
        self.manager = manager
        return manager
