"""MarketService: the market built from the scenario, stepped by the Step page.

The only place that builds and holds the ``MarketManager``. The Studio asks it to
build the market from the current scenario and to step it; pages read the manager's
state (history, participants, pending step) to display it but never construct or
drive it themselves. The records the manager returns are plain data.
"""

from __future__ import annotations

from core.config.scenario import Scenario
from core.market.manager import MarketManager


# --------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------
class MarketService:
    """The market being stepped."""

    def __init__(self) -> None:
        self.manager: MarketManager | None = None

    def build(self, scenario: Scenario) -> MarketManager:
        """A fresh market from ``scenario`` (the manager copies it), reset to step 0."""
        manager = MarketManager(scenario)
        manager.reset()
        self.manager = manager
        return manager

    def next_part(self) -> None:
        """The next part of the step: collect the orders when no step is running,
        else the next clearing stage, or settlement and the power flow."""
        m = self._built()
        if m.pending is None:
            m.start_step()
        else:
            m.advance()

    def step(self) -> None:
        """Finish the step being played, or play one whole step."""
        self._built().step()

    def run_to_end(self) -> None:
        """Play the rest of the day."""
        self._built().run_to_end()

    def _built(self) -> MarketManager:
        if self.manager is None:
            raise RuntimeError("The market is not built yet")
        return self.manager
