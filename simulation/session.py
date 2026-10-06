"""Stepping a scenario by hand: market, then power flow, one step per click."""

from __future__ import annotations

from dataclasses import dataclass

from config.scenario import Scenario
from grid.contract import GridAssessment
from grid.powerflow import SimBenchGrid
from market.step import MarketStep, OrderIntent, StepOutcome


@dataclass(frozen=True)
class StepRecord:
    """One played step: what the market did and what the network did."""

    step: int
    market: StepOutcome
    grid: GridAssessment


class StepSession:
    """A scenario being stepped through in the Studio.

    Args:
        scenario: The configured market on its network.
    """

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.market: MarketStep | None = None
        self.grid: SimBenchGrid | None = None
        self.history: list[StepRecord] = []

    @property
    def current_step(self) -> int:
        """The next step to play."""
        return len(self.history)

    def reset(self) -> None:
        """Build the market and the grid and go back to step 0."""
        raise NotImplementedError

    def step(self, intents: dict[str, OrderIntent] | None = None) -> StepRecord:
        """Play the next step: orders, clearing, settlement, power flow."""
        raise NotImplementedError

    def run_to_end(self) -> list[StepRecord]:
        """Play every remaining step of the day."""
        raise NotImplementedError
