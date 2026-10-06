"""One power flow per market step on a SimBench network."""

from __future__ import annotations

from typing import Sequence

from config.scenario import GridSetup
from grid.contract import GridAssessment, ParticipantInjection


class SimBenchGrid:
    """A working copy of the network, stepped with the market.

    The network's own elements follow their profiles (``GridSetup.background``),
    except the ones the participants own: those are replaced by the participants'
    injections.

    Args:
        setup: The network and its power-flow settings.
        owned: Element IDs each participant owns.
    """

    def __init__(self, setup: GridSetup, owned: dict[str, list[str]]) -> None:
        self.setup = setup
        self.owned = owned

    def reset(self) -> None:
        """Load a fresh copy of the network for the configured day."""
        raise NotImplementedError

    def assess(
        self, step: int, injections: Sequence[ParticipantInjection]
    ) -> GridAssessment:
        """Run the power flow for ``step`` with the participants' injections."""
        raise NotImplementedError

    def electrical_distance(self, bus_a: str, bus_b: str) -> float:
        """Line length in km between two buses."""
        raise NotImplementedError
