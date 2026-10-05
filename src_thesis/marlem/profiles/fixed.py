"""Profile handler that returns the profiles it was given.

The original environment replaces every agent's profile at ``reset`` with random
or CSV ones (I-05). This handler hands each agent back its own, in agent order,
so the profiles an experiment file describes are the ones the market runs on.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from src_thesis.marlem.profiles.der import DERProfileHandler


class FixedProfileHandler(DERProfileHandler):
    """Hands out fixed (generation, demand) pairs, one per ``reset`` call.

    ``LocalEnergyMarket.reset`` calls ``reset`` once per agent in agent order, so
    the pairs must be given in that order; ``rewind`` starts again at the first.

    Args:
        profiles: One (generation, demand) pair per agent.
        min_quantity: Market minimum quantity.
        max_quantity: Market maximum quantity.
    """

    def __init__(
        self,
        profiles: Sequence[Tuple[Sequence[float], Sequence[float]]],
        min_quantity: float,
        max_quantity: float,
    ) -> None:
        super().__init__(float(min_quantity), float(max_quantity))
        self._profiles = [(list(g), list(d)) for g, d in profiles]
        self._next = 0

    def rewind(self) -> None:
        """The next ``reset`` call belongs to the first agent."""
        self._next = 0

    def reset(self, capacity: float, max_steps: int) -> Tuple[List[float], List[float]]:
        """The next agent's own profiles (``capacity`` and ``max_steps`` unused)."""
        generation, demand = self._profiles[self._next % len(self._profiles)]
        self._next += 1
        return list(generation), list(demand)
