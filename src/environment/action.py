"""
Action space definition for the Local Energy Market environment.
"""

from typing import List, Optional

from gymnasium.spaces import Box, Dict
from numpy import array, float32, ndarray

from ..agent.der import DERAgent
from ..market.dso import DSOAgent
from ..market.matching import MarketConfig


class ActionHandler:
    """Handler class for managing action space."""

    def __init__(self,
                 agents: List[DERAgent],
                 dso: DSOAgent,
                 market_config: MarketConfig,
                 time_step_hours: float = 1.0) -> None:
        """Initialize action handler.

        Args:
            agents: List of DER agents in the market
            market_config: Market configuration parameters
        """
        self._agents = agents
        self._dso = dso
        self.time_step_hours = time_step_hours

        # Check initialization
        self._check_init()

        # The policy controls only continuous quantities.  A positive signed
        # quantity requests an import and a negative quantity offers an export.
        # Matching is deterministic price-time priority; partner choice is not
        # part of this baseline action space.
        self.action_space = Dict({agent.id: Box(low=array([market_config.min_price,  # bid_price
                                                           -min(market_config.max_quantity, agent.capacity * time_step_hours)], dtype=float32),
                                                high=array([market_config.max_price,  # bid_price
                                                            min(market_config.max_quantity, agent.capacity * time_step_hours)], dtype=float32),
                                                dtype=float32)
                                  for agent in agents})

    def _check_init(self) -> None:
        """Check if the action handler is initialized correctly."""
        if self._agents is None:
            raise ValueError(f"Agents must be provided in the config. Current value: <agents = {self._agents}>.")

        if self._dso is None:
            raise ValueError(f"DSO agent must be provided in the config. Current value: <dso = {self._dso}>.")

    def is_valid_action(self,
                        agent_id: str,
                        action: ndarray) -> bool:
        """Check if the action is within the action space.

        Args:
            agent_id: ID of the agent making the action
            action: Action to check

        Returns:
            True if the action is within the action space, False otherwise
        """
        return self.action_space[agent_id].contains(action)

    def get_partner_id(self, index: int) -> Optional[str]:
        """Get the partner ID from the action.

        Index mapping:
        - 0 to len(agents)-1: DER agent IDs
        - len(agents): DSO agent ID
        - len(agents)+1: No preference (None)

        Args:
            index: Index of the partner given in the action

        Returns:
            Partner ID extracted from the action, or None for no preference
        """
        if index < len(self._agents):
            return self._agents[index].id

        elif index == len(self._agents):
            return self._dso.id

        else:
            return None
