"""
Distributed Energy Resource (DER) agent implementation.

This module implements agents representing distributed energy resources (DERs) in the
Local Energy Market. Agents can have generation and demand profiles, battery storage,
and the ability to participate in market trading with demand response capabilities.
"""

from typing import TYPE_CHECKING, List, Optional

import numpy as np
from networkx import Graph

from ..grid.base import Location
from .battery import Battery
from .settlement import EnergySettlement

if TYPE_CHECKING:
    from ..market.matching import MarketConfig


class DERAgent:
    """Agent representing a Distributed Energy Resource in the Local Energy Market."""

    def __init__(self,
                 id: str,
                 capacity: float,
                 battery: Optional[Battery] = None,
                 node_id: Optional[str] = None,
                 generation_profile: Optional[List[float]] = None,
                 demand_profile: Optional[List[float]] = None) -> None:
        """Initialize the DER agent.

        Args:
            id: Unique identifier for the agent
            capacity: Maximum capacity of the DER (W)
            battery: Optional battery object
            node_id: Optional node ID in the grid network
            generation_profile: Optional time series (list/array) of generation values per timestep
            demand_profile: Optional time series (list/array) of demand values per timestep
        """
        self.id = id
        self.capacity = capacity
        self.battery = battery
        self.node_id = node_id
        self.generation_profile = list(generation_profile or [])
        self.demand_profile = list(demand_profile or [])

        # Demand response tracking
        self.cumulative_demand_satisfied: float = 0.0
        self.cumulative_demand_deferred: float = 0.0
        self.total_demand_required: float = sum(self.demand_profile)
        self.cumulative_supply_satisfied: float = 0.0
        self.cumulative_supply_deferred: float = 0.0
        self.total_supply_required: float = sum(self.generation_profile)

        # Grid attributes
        self.location: Optional[Location] = None

        # Attributes from the environment
        self.balance: float = 0.0
        self.profit: float = 0.0
        self.reputation: float = 0.5

        # Market state tracking
        self.price_history: List[float] = []

        # Mechanism factors
        self._rng = np.random.default_rng()
        self.settlements = []
        self.time_step_hours = 1.0
        self._reputation_factor: float = 0.5
        self._cooperation_factor: float = 0.3

        # Check initialization
        self._check_init()

    def reset(self,
              reputation: float,
              generation_profile: List[float],
              demand_profile: List[float],
              seed: Optional[int] = None) -> None:
        """Reset the DER agent state.

        Args:
            reputation: Reputation score
            generation_profile: Generation profile
            demand_profile: Demand profile
            seed: Random seed for reproducibility
        """
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        # Reset agent attributes
        self.settlements = []
        self.reputation = reputation
        self.generation_profile = list(generation_profile or [])
        self.demand_profile = list(demand_profile or [])

        # Reset battery
        if self.battery:
            self.battery.reset(seed)

        # Reset demand response tracking
        self.cumulative_demand_satisfied = 0.0
        self.cumulative_demand_deferred = 0.0
        self.total_demand_required = sum(self.demand_profile)
        self.cumulative_supply_satisfied = 0.0
        self.cumulative_supply_deferred = 0.0
        self.total_supply_required = sum(self.generation_profile)

        # Reset attributes from the environment
        self.balance = np.random.uniform(-self.capacity, self.capacity)
        self.profit = 0.0

        # Reset market state tracking
        self.price_history = []

    def _check_init(self) -> None:
        """ Validate DERAgent parameters.

        Raises:
            ValueError: If id is not a string
            ValueError: If generation_profile or demand_profile have different lengths
        """

        if not isinstance(self.id, str):
            raise ValueError(f"id must be a string, got {type(self.id)}")

        if not (len(self.generation_profile) == len(self.demand_profile)):
            raise ValueError(f"Length mismatch: generation_profile ({len(self.generation_profile)}), demand_profile ({len(self.demand_profile)})")

    def update_location(self, location: Location) -> None:
        """Update the agent's location.

        Args:
            location: New location of the agent
        """
        self.location = location

    def select_preferred_partner(self,
                                 candidates: List['DERAgent'],
                                 graph: Graph,
                                 randomize: bool = True) -> str:
        """Select a preferred trading partner based on the agent"s strategy and observations.

        This method implements different strategies for partner selection.
        The selected partner ID will be included in the agent"s market orders.

        Args:
            candidates: List of known agents
            graph: Optional graph for distance calculation
            randomize: Whether to randomize the selection of a partner

        Returns:
            ID of the preferred trading partner
        """
        # Exclude self from candidates
        candidates = [agent for agent in candidates if agent.id != self.id]

        # Sort candidates by reputation and distance
        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x.reputation, self.location.distance_to(x.location, graph)))

        return self._rng.choice(candidates[:max(1, len(candidates) // 2 + 1)]).id if randomize else candidates[0].id

    def adjust_action_for_battery(self, step, action, market_config):
        """Project the original four continuous controls onto physical feasibility.

        Direction uses the same >0.5 threshold as order creation. Partner selection
        is decoded once by ActionHandler. Buying may charge storage; selling may
        discharge it, after reserving sufficient energy for current household demand.
        """
        action = np.asarray(action, dtype=np.float32)
        if action.shape != (4,) or not np.isfinite(action).all():
            raise ValueError('Action must contain four finite controls.')
        price, requested, direction, partner = action
        charge, discharge = self.battery.estimate_available_energy() if self.battery else (0., 0.)
        net = self.get_generation(step) - self.get_demand(step)
        available = max(0., -net + charge) if direction > .5 else max(0., net + discharge)
        # DER capacity scales generation profiles; it is not a household import
        # connection rating (pure consumers legitimately have zero DER capacity).
        quantity = min(max(0., float(requested)), available, market_config.max_quantity)
        if quantity < market_config.min_quantity:
            quantity = 0.
        return np.array([np.clip(price, market_config.min_price, market_config.max_price),
                         quantity, np.clip(direction, 0., 1.), partner], dtype=np.float32)

    def update_energy_tracking(self, step, energy_bought=0., energy_sold=0.):
        """Compatibility entry point; physical settlement is idempotent per period."""
        return self.settle_energy(step, energy_bought, energy_sold)

    def update_battery_from_trades(self, step, energy_bought=0., energy_sold=0.):
        """Compatibility entry point; physical settlement is idempotent per period."""
        return self.settle_energy(step, energy_bought, energy_sold)

    def get_generation(self, step: int) -> float:
        """Get generation value for a specific step.

        Args:
            step: Time step

        Returns:
            Generation value at the specified step
        """
        try:
            return self.generation_profile[step]
        except IndexError:
            raise IndexError(f"Time step {step} is out of range for <generation_profile> with length {len(self.generation_profile)}.")

    def get_demand(self, step: int) -> float:
        """Get demand value for a specific step.

        Args:
            step: Time step

        Returns:
            Demand value at the specified step
        """
        try:
            return self.demand_profile[step]
        except IndexError:
            raise IndexError(f"Time step {step} is out of range for <demand_profile> with length {len(self.demand_profile)}.")

    def get_remaining_demand(self, step: int) -> float:
        """Get remaining demand from current step to end of episode.

        Args:
            step: Current time step

        Returns:
            Sum of remaining demand
        """
        try:
            return sum(self.demand_profile[step:])
        except IndexError:
            raise IndexError(f"Time step {step} is out of range for <demand_profile> with length {len(self.demand_profile)}.")

    def get_remaining_supply(self, step: int) -> float:
        """Get remaining supply from current step to end of episode.

        Args:
            step: Current time step

        Returns:
            Sum of remaining generation
        """
        try:
            return sum(self.generation_profile[step:])
        except IndexError:
            raise IndexError(f"Time step {step} is out of range for <generation_profile> with length {len(self.generation_profile)}.")

    def settle_energy(self, step, energy_bought=0., energy_sold=0.):
        """Dispatch storage once, then record all physical sinks and sources."""
        if self.settlements and self.settlements[-1].step == step:
            previous = self.settlements[-1]
            if not np.isclose(previous.imported, energy_bought) or not np.isclose(previous.exported, energy_sold):
                raise ValueError('Cannot settle a period twice with different trades.')
            return previous
        generation, demand = self.get_generation(step), self.get_demand(step)
        before = self.battery.energy_level if self.battery else 0.
        charge = discharge = loss = 0.
        balance = generation + energy_bought - energy_sold - demand
        if self.battery:
            if balance > 0:
                stored = self.battery.charge(balance)
                charge = stored / self.battery.charge_efficiency if self.battery.charge_efficiency else 0.
                loss = charge - stored
            elif balance < 0:
                discharge = self.battery.discharge(-balance)
                loss = before - self.battery.energy_level - discharge
            else:
                self.battery.idle()
        available = generation + energy_bought + discharge - energy_sold - charge
        if available < -1e-5:
            raise ValueError('Settled exports exceed physical availability.')
        served = min(demand, max(0., available))
        curtailed = max(0., available - demand)
        record = EnergySettlement(step, generation, demand, energy_bought, energy_sold,
                                  charge, discharge, loss, before,
                                  self.battery.energy_level if self.battery else 0.,
                                  served, demand-served, curtailed)
        if abs(record.balance_error) > 1e-5 or abs(record.storage_error) > 1e-5:
            raise ArithmeticError('Household energy settlement does not conserve energy.')
        self.settlements.append(record)
        self.cumulative_demand_satisfied += served
        self.cumulative_demand_deferred += demand-served
        self.cumulative_supply_satisfied += generation-curtailed
        self.cumulative_supply_deferred += curtailed
        return record
