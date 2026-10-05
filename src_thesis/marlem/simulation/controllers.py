"""Scripted controllers: the simplest policies, no learning.

They show how a market behaves under simple rules (and give RL something to be
compared with): nobody trades, everybody trades at random, everybody sells its
surplus and buys its deficit.
"""

from __future__ import annotations

import random
from typing import Mapping, Optional

from src_thesis.marlem.simulation.catalog import CONTROLLERS, names
from src_thesis.marlem.simulation.policy import AgentView, Intent, Policy


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class NoOrder:
    """Nobody places an order: the baseline where the market stays silent.

    With a market minimum order above zero a "no order" is not possible; every
    agent then offers the smallest allowed quantity at a price that only the DSO
    takes (sell at the maximum price, buy at the minimum price).
    """

    name = "no_order"

    def reset(self, seed: Optional[int]) -> None:
        """Nothing to reset."""

    def act(self, views: Mapping[str, AgentView]) -> dict[str, Intent]:
        """No order, or the smallest unmatchable one."""
        out = {}
        for agent_id, v in views.items():
            if v.min_quantity <= 0.0:
                out[agent_id] = Intent.nothing(v.midpoint)
            else:
                out[agent_id] = Intent(v.max_price, v.min_quantity, False)
        return out


class RandomOrders:
    """Zero-intelligence agents: random price, quantity and side ([P1] §4.2).

    Args:
        seed: Default seed when ``reset`` gets none.
    """

    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed
        self._rng = random.Random(seed)

    def reset(self, seed: Optional[int]) -> None:
        """Restart the random stream (a given seed gives the same orders)."""
        self._rng = random.Random(self._seed if seed is None else seed)

    def act(self, views: Mapping[str, AgentView]) -> dict[str, Intent]:
        """One random order per agent, in the order of the views."""
        out = {}
        for agent_id, v in views.items():
            out[agent_id] = Intent(
                price=self._rng.uniform(v.min_price, v.max_price),
                quantity_kwh=self._rng.uniform(v.min_quantity, v.max_quantity),
                is_buy=self._rng.random() < 0.5,
            )
        return out


class NetPosition:
    """Sell the surplus, buy the deficit, at a price between the DSO's two.

    The simplest sensible rule (02 §3.10 ``rule_based``): an agent with more
    generation than demand sells the difference, one with less buys it.

    Args:
        aggressiveness: 0 trades at the midpoint of the DSO's prices; 1 asks the
            DSO's own prices (sell at the feed-in tariff, buy at the utility
            price), which matches with anyone. Values between interpolate.
    """

    name = "net_position"

    def __init__(self, aggressiveness: float = 0.0) -> None:
        if not 0.0 <= aggressiveness <= 1.0:
            raise ValueError("aggressiveness must be between 0 and 1")
        self.aggressiveness = aggressiveness

    def reset(self, seed: Optional[int]) -> None:
        """Nothing to reset."""

    def act(self, views: Mapping[str, AgentView]) -> dict[str, Intent]:
        """Sell a surplus, buy a deficit, otherwise no order."""
        out = {}
        for agent_id, v in views.items():
            mid, a = v.midpoint, self.aggressiveness
            surplus = v.surplus_kwh
            if surplus > 0.0:
                price = _clip(mid - a * (mid - v.fit), v.min_price, v.max_price)
                out[agent_id] = Intent(price, min(surplus, v.max_quantity), False)
            elif surplus < 0.0:
                price = _clip(
                    mid + a * (v.utility_price - mid), v.min_price, v.max_price
                )
                out[agent_id] = Intent(price, min(-surplus, v.max_quantity), True)
            else:
                out[agent_id] = Intent.nothing(mid)
        return out


FACTORIES = {"no_order": NoOrder, "random": RandomOrders, "net_position": NetPosition}


def get_policy(name: str, **params: float) -> Policy:
    """Build a controller by name.

    Args:
        name: One of ``catalog.names()``.
        **params: Its parameters; unknown or out-of-range values are errors.

    Raises:
        ValueError: Unknown controller, unknown parameter or value out of range.
    """
    if name not in CONTROLLERS:
        raise ValueError(f"Unknown controller {name!r}; use one of {names()}")
    spec = CONTROLLERS[name]
    for key, value in params.items():
        if key not in spec.params:
            raise ValueError(f"{name} has no parameter {key!r}")
        p = spec.params[key]
        if not p.low <= value <= p.high:
            raise ValueError(f"{name}.{key} must be between {p.low} and {p.high}")
    return FACTORIES[name](**params)
