"""
Local Energy Market (LEM) environment implementation using Gymnasium.

This environment implements a decentralized marketplace where agents can submit buy/sell
offers for energy trading. The environment handles:
- Non-stationary market dynamics
- Continuous action spaces for bid/ask prices and quantities
- Partial observability of market state
- Decentralized market clearing
"""

from copy import deepcopy
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Union

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv
from ray.rllib.utils.typing import MultiAgentDict

from ..agent.der import DERAgent
from ..coordination.implicit_cooperation import ImplicitCooperation
from ..grid.base import GridTopology
from ..grid.network import GridNetwork
from ..market.dso import DSOAgent
from ..market.matching import MarketConfig, OrderMatcher
from ..market.order import Order
from ..market.reputation import ReputationHandler
from ..profile.der import DERProfileHandler
from ..profile.dso import DSOProfileHandler
from .action import ActionHandler
from .observation import ObservationHandler
from .reward import RewardHandler


# region Local energy market environment
class LocalEnergyMarket(MultiAgentEnv):
    """
    Local Energy Market environment implementing the MultiAgentEnv interface.

    This environment implements a decentralized marketplace where agents can trade
    energy through buy/sell offers, following a Dec-POMDP framework. The agents have
    partial observability of the market state and make decisions based on their own
    local observations.
    """

    metadata = {"render_modes": ["human"], "render_fps": 1}

    # region Construction and validation
    def __init__(self, env_config: Dict[str, Any]) -> None:
        """Initialize the environment.

        Args:
            config: RLlib env_config dict.
        """
        super().__init__()
        env_config = deepcopy(env_config)

        # Validate before constructing dependent components.
        self._check_env_config(env_config)

        # Read immutable scenario settings.
        self.max_steps: int = env_config["max_steps"]
        self.market_config: MarketConfig = env_config["market_config"]
        self.grid_network: GridNetwork = env_config.get("grid_network", None)
        self.dso: DSOAgent = env_config.get("dso", None)
        self.der_profile_handler: DERProfileHandler = env_config.get(
            "der_profile_handler", None
        )
        self.dso_profile_handler: DSOProfileHandler = env_config.get(
            "dso_profile_handler", None
        )
        self.enable_reset_dso_profiles: bool = env_config.get(
            "enable_reset_dso_profiles", False
        )
        self.enable_asynchronous_order: bool = env_config.get(
            "enable_asynchronous_order", True
        )
        self.max_error: float = env_config.get("max_error", 0.3)
        if not np.isfinite(self.max_error) or self.max_error < 0 or self.max_error > 1:
            raise ValueError("max_error must be a finite fraction in [0, 1].")
        self.num_anchor: int = env_config.get("num_anchor", 4)
        self.seed: Optional[int] = env_config.get("seed", None)

        self.time_step_hours = float(env_config.get("time_step_hours", 1.0))
        if not np.isfinite(self.time_step_hours) or self.time_step_hours <= 0:
            raise ValueError("time_step_hours must be finite and positive.")
        self._rng = np.random.default_rng(self.seed)
        self._reset_count = 0
        # Preserve configured order for stable multi-agent spaces.
        _config_agents = env_config["agents"]
        self._agents: Dict[str, DERAgent] = {
            agent.id: agent for agent in _config_agents
        }
        self.agents_id: List[str] = [*self._agents.keys()]
        self.agent_order = tuple(self.agents_id)
        self.agents = list(self.agent_order)
        self.possible_agents = list(self.agent_order)
        self._agent_ids = set(self.agent_order)

        # Apply defaults and propagate shared physical settings.
        self._set_default_values()
        self.grid_network.time_step_hours = self.time_step_hours
        self.dso.grid_network = self.grid_network
        self.dso.market_price_bounds = (
            self.market_config.min_price,
            self.market_config.max_price,
        )
        if self.dso.node_id not in self.grid_network.graph:
            self.dso.node_id = next(iter(self.grid_network.graph))
        for agent in _config_agents:
            agent.time_step_hours = self.time_step_hours
            if agent.battery:
                agent.battery.time_step_hours = self.time_step_hours
            if not agent.generation_profile and not agent.demand_profile:
                agent.generation_profile, agent.demand_profile = (
                    self.der_profile_handler.reset(agent.capacity, self.max_steps)
                )
            if env_config.get("profile_values_are_power", False):
                agent.generation_profile = [
                    v * self.time_step_hours for v in agent.generation_profile
                ]
                agent.demand_profile = [
                    v * self.time_step_hours for v in agent.demand_profile
                ]
        self._configured_profiles = {
            a.id: (list(a.generation_profile), list(a.demand_profile))
            for a in _config_agents
        }
        self._initial_tariffs = (
            list(self.dso.feed_in_tariff),
            list(self.dso.utility_price),
        )

        # Validate the fully assembled component graph.
        self._check_init()

        # Assign agents to their configured or seeded grid nodes.
        self.grid_network.assign_agents_to_graph(_config_agents)

        # Initialize Gymnasium/RLlib state containers.
        self.render_mode: Optional[str] = None
        self.rewards: MultiAgentDict = {id: [] for id in self.agents_id}

        # Initialize episode state.
        self.current_step: int = 0
        self.time_of_day: float = 0.0

        # Build market and learning-support components.
        self.market = OrderMatcher(
            len(self.agents_id), self.market_config, self.grid_network, self.dso
        )

        self.reputation_handler = ReputationHandler()

        self.implicit_cooperation = ImplicitCooperation(self.grid_network.capacity)

        self.observation_handler = ObservationHandler(
            self.max_steps,
            _config_agents,
            self.dso,
            self.market_config,
            self.grid_network,
            forecast_error=self.max_error,
        )
        self.observation_spaces: spaces.Dict[str, spaces.Box] = (
            self.observation_handler.observation_space
        )

        self.action_handler = ActionHandler(
            _config_agents, self.dso, self.market_config
        )
        self.action_spaces: spaces.Dict[str, spaces.Box] = (
            self.action_handler.action_space
        )

        self.reward_handler = RewardHandler(self.dso, self.grid_network)

    @staticmethod
    def _check_env_config(env_config: Dict[str, Any]) -> None:
        """Check environment configuration.

        Args:
            env_config: Environment configuration dictionary.

        Raises:
            ValueError: If required attributes are not provided in the <env_config> dictionary.
            ValueError: If agents is not a list of DERAgent objects.
            ValueError: If max_steps is not an integer.
            ValueError: If market_config is not a MarketConfig object.
            ValueError: If grid_network is not a GridNetwork object.
            ValueError: If dso is not a DSOAgent object.
            ValueError: If der_profile_handler is not a DERProfileHandler object.
            ValueError: If dso_profile_handler is not a DSOProfileHandler object.
        """
        # Check required attributes
        for key in ["max_steps", "market_config", "agents"]:
            if key not in env_config.keys():
                raise ValueError(
                    f"The <env_config> is missing the required key: <key = {key}>."
                )

        # Check agents configuration
        if env_config.get("agents") is None:
            raise ValueError("Agents must be provided in the config.")

        # Validate agents
        if (
            not isinstance(env_config.get("agents"), list)
            or len(env_config.get("agents")) == 0
        ):
            raise ValueError(
                f"The <agents> must be a non-empty list, got <agents = {env_config.get('agents')}>."
            )

        # Check for duplicate agent IDs
        if len(env_config.get("agents")) != len(
            set(agent.id for agent in env_config.get("agents"))
        ):
            raise ValueError("Duplicate agent IDs found in agents config.")

        # Check max_steps
        if (
            not isinstance(env_config.get("max_steps"), int)
            or env_config.get("max_steps") <= 0
        ):
            raise ValueError(
                f"The <max_steps> must be a positive integer, got <max_steps = {env_config.get('max_steps')}>."
            )

        # Check market_config
        if not isinstance(env_config.get("market_config"), MarketConfig):
            raise ValueError(
                f"The attribute <market_config> must be a MarketConfig object. Got <market_config = {env_config.get('market_config')}>."
            )

        # Check grid_network
        if (env_config.get("grid_network") is not None) and (
            not isinstance(env_config.get("grid_network"), GridNetwork)
        ):
            raise ValueError(
                f"The attribute <grid_network> must be a GridNetwork object or None. Got <grid_network = {env_config.get('grid_network')}>."
            )

        # Check dso
        if (env_config.get("dso") is not None) and (
            not isinstance(env_config.get("dso"), DSOAgent)
        ):
            raise ValueError(
                f"The attribute <dso> must be a DSOAgent object or None. Got <dso = {env_config.get('dso')}>."
            )

        # Check der_profile_handler
        if (env_config.get("der_profile_handler") is not None) and (
            not isinstance(env_config.get("der_profile_handler"), DERProfileHandler)
        ):
            raise ValueError(
                f"The attribute <der_profile_handler> must be a DERProfileHandler object or None. Got <der_profile_handler = {env_config.get('der_profile_handler')}>."
            )

        # Check dso_profile_handler
        if (env_config.get("dso_profile_handler") is not None) and (
            not isinstance(env_config.get("dso_profile_handler"), DSOProfileHandler)
        ):
            raise ValueError(
                f"The attribute <dso_profile_handler> must be a DSOProfileHandler object or None. Got <dso_profile_handler = {env_config.get('dso_profile_handler')}>."
            )

    def _set_default_values(self) -> None:
        """Check environment configuration and set default values if not provided."""
        # Set default values if not provided
        if self.grid_network is None:
            self.grid_network = GridNetwork(
                GridTopology.IEEE34,
                len(self.agents),
                self.market_config.max_quantity * len(self.agents),
                seed=self.seed,
            )

        # Set DER profile handler
        if self.der_profile_handler is None:
            self.der_profile_handler = DERProfileHandler(
                self.market_config.min_quantity,
                self.market_config.max_quantity,
                seed=self.seed,
            )

        # Set DSO profile handler
        if self.dso_profile_handler is None:
            self.dso_profile_handler = DSOProfileHandler(
                self.market_config.min_price,
                self.market_config.max_price,
                seed=self.seed,
            )

        # Set DSO agent
        if self.dso is None:
            feed_in_tariff, utility_price = self.dso_profile_handler.get_price_profiles(
                self.max_steps
            )
            self.dso = DSOAgent("DSO", feed_in_tariff, utility_price, self.grid_network)

    def _check_init(self):
        """Validate physical profiles independently of the market order-size cap."""
        for agent in self._agents.values():
            for name in ("generation_profile", "demand_profile"):
                values = getattr(agent, name)
                if (
                    len(values) != self.max_steps
                    or not np.isfinite(values).all()
                    or min(values) < 0
                ):
                    raise ValueError(
                        f"{agent.id} {name} must contain max_steps finite non-negative energies."
                    )
            if not np.isfinite(agent.capacity) or agent.capacity < 0:
                raise ValueError(
                    "DER generation capacity must be finite and non-negative."
                )
        if self.dso.id in self._agents:
            raise ValueError("DSO and household IDs must be distinct.")
        for values in (self.dso.feed_in_tariff, self.dso.utility_price):
            if len(values) != self.max_steps or not np.isfinite(values).all():
                raise ValueError("Tariffs must contain max_steps finite values.")
            if (
                min(values) < self.market_config.min_price
                or max(values) > self.market_config.max_price
            ):
                raise ValueError("Tariffs must lie within market price bounds.")
        self.dso._check_init()

    # endregion

    # region Episode lifecycle
    def reset(self, *, seed=None, options=None):
        """Restore state using reproducible, independent episode random streams.

        ``reset(seed=x)`` is an exact replay of episode seed ``x``.  Repeated
        ``reset()`` calls advance a local seeded stream, so evaluation episodes
        are distinct rather than silently replaying seed 42 forever.
        """
        super().reset(seed=seed, options=options)
        if seed is not None:
            selected_seed = int(seed)
            self._rng = np.random.default_rng(selected_seed)
            self._reset_count = 0
        else:
            selected_seed = int(self._rng.integers(0, 2**31 - 1))
            self._reset_count += 1
        self.episode_seed = selected_seed
        episode_rng = np.random.default_rng(selected_seed)
        self.current_step = 0
        self.time_of_day = 0.0
        self.agents = list(self.agent_order)
        for agent_index, agent in enumerate(self._agents.values()):
            generation, demand = self._configured_profiles[agent.id]
            agent_seed = int(episode_rng.integers(0, 2**31 - 1))
            agent.reset(
                float(episode_rng.uniform(0.0, 1.0)),
                list(generation),
                list(demand),
                agent_seed,
            )
            # Perturb observations only; settlement keeps physical profiles.
            forecast_rng = np.random.default_rng(
                int(episode_rng.integers(0, 2**31 - 1))
            )
            if self.max_error > 0:
                generation_forecast = np.asarray(generation, dtype=float) * (
                    1.0
                    + forecast_rng.uniform(
                        -self.max_error, self.max_error, len(generation)
                    )
                )
                demand_forecast = np.asarray(demand, dtype=float) * (
                    1.0
                    + forecast_rng.uniform(-self.max_error, self.max_error, len(demand))
                )
            else:
                generation_forecast, demand_forecast = generation, demand
            agent.set_forecasts(generation_forecast.tolist(), demand_forecast.tolist())
        self.market.reset(selected_seed)
        self.grid_network.begin_period()
        if self.enable_reset_dso_profiles:
            self.dso_profile_handler._rng = np.random.default_rng(
                int(self._rng.integers(0, 2**31 - 1))
            )
            self.dso.feed_in_tariff, self.dso.utility_price = (
                self.dso_profile_handler.reset(self.max_steps)
            )
        else:
            self.dso.feed_in_tariff, self.dso.utility_price = map(
                list, self._initial_tariffs
            )
        self._check_init()
        self.rewards = {id: [] for id in self.agent_order}
        self.info = {}
        return self.observation_handler.reset_observation_space(), {
            id: {} for id in self.agent_order
        }

    def step(self, action_dict):
        """Execute exactly one physical market period, then publish its outcomes."""
        if self.current_step >= self.max_steps:
            raise RuntimeError("Episode is complete; call reset before stepping again.")
        if set(action_dict) != set(self.agent_order):
            raise ValueError("One action per active agent is required.")
        orders = {}
        raw_actions = {
            id: np.asarray(action_dict[id]).copy() for id in self.agent_order
        }
        for id in self.agent_order:
            agent = self._agents[id]
            action = agent.adjust_action_for_battery(
                self.current_step, raw_actions[id], self.market_config
            )
            if not self.action_handler.is_valid_action(id, action):
                raise ValueError(f"Invalid action for {id}: {action}")
            price, quantity, direction, partner = action
            preferred = (
                self.action_handler.get_partner_id(partner)
                if self.market_config.enable_partner_preference
                else None
            )
            if preferred == id:
                preferred = None
            time = self.time_of_day + (
                self._rng.uniform(0.0, 1.0 / self.max_steps)
                if self.enable_asynchronous_order
                else 0.0
            )
            orders[id] = Order(
                f"{id}_{self.current_step}",
                id,
                float(price),
                float(quantity),
                bool(direction > 0.5),
                time,
                agent.location,
                preferred,
            )
        baseline = sum(
            a.get_generation(self.current_step) - a.get_demand(self.current_step)
            for a in self._agents.values()
        )
        matching = self.market.match_orders(
            self.current_step,
            list(orders.values()),
            {id: a.reputation for id, a in self._agents.items()},
            baseline,
        )
        for id, agent in self._agents.items():
            bought = sum(
                t.delivered_quantity for t in matching.trades if t.buyer_id == id
            )
            sold = sum(t.quantity for t in matching.trades if t.seller_id == id)
            record = agent.settle_energy(self.current_step, bought, sold)
            matching.physical_settlements[id] = record
            agent.profit = self.market.get_agent_cash_position(id)
            agent.balance = self.market.get_agent_position(id)
        # Residual balance is remaining curtailment minus unmet demand after storage.
        self.dso.balance = sum(
            r.curtailed_generation - r.unserved_demand
            for r in matching.physical_settlements.values()
        )
        matching.grid_balance = self.dso.balance
        kpis = self.implicit_cooperation.get_kpis(
            self.current_step,
            self.dso.id,
            list(self._agents.values()),
            list(orders.values()),
            matching.trades,
            self.dso.congestion_level,
            self.market.matching_history,
        )
        matching.kpis = dict(kpis)
        terminal = self.current_step == self.max_steps - 1
        rewards = {
            id: self.reward_handler.calculate_reward(
                a,
                orders[id],
                matching,
                kpis,
                self.market_config.min_price,
                self.market_config.max_price,
                is_terminal=terminal,
            )
            for id, a in self._agents.items()
        }
        for id, agent in self._agents.items():
            self.rewards[id].append(rewards[id])
            agent.reputation = self.reputation_handler.update_reputation(
                agent, matching, self.time_of_day, self.dso.id
            )
        self.current_step += 1
        self.time_of_day = self.current_step / self.max_steps
        self.info = dict(
            episode_seed=self.episode_seed,
            current_step=self.current_step,
            time_of_day=self.time_of_day,
            orders=list(orders.values()),
            trades=matching.trades,
            grid_balance=self.dso.balance,
            market_price=matching.clearing_price,
            market_volume=matching.clearing_volume,
            matching_history=self.market.matching_history,
            dso_stats=dict(self.market.dso_stats),
            kpis=dict(kpis),
            dso_intervention=dict(self.dso.intervention_history[-1]),
            physical_settlements={
                id: asdict(r) for id, r in matching.physical_settlements.items()
            },
            raw_actions={id: a.tolist() for id, a in raw_actions.items()},
            cash_ledger=dict(self.market.cash_ledger),
        )
        observations = self.observation_handler.update_observation_space(
            min(self.current_step, self.max_steps - 1),
            self.time_of_day,
            list(orders.values()),
            self.market.matching_history,
            self.implicit_cooperation,
        )
        terminateds = {id: terminal for id in self.agent_order}
        terminateds["__all__"] = terminal
        truncateds = {id: False for id in self.agent_order}
        truncateds["__all__"] = False
        return (
            observations,
            rewards,
            terminateds,
            truncateds,
            {id: self.info for id in self.agent_order},
        )

    # endregion

    # region Rendering and compatibility helpers
    def render(self) -> Optional[Union[np.ndarray, str]]:
        """Render the environment.

        Returns:
            Rendered frame as numpy array (rgb_array mode) or None
        """
        if self.render_mode is None:
            return None

        # Implement visualization (to be added)
        return None

    def close(self) -> None:
        """Clean up environment resources."""
        pass

    def seed(self, seed: Optional[int] = None) -> None:
        """Set random seed for reproducibility.

        Args:
            seed: Random seed value
        """
        if seed is not None:
            self.seed = int(seed)
            self._rng = np.random.default_rng(self.seed)
            self._reset_count = 0

    # endregion


# endregion
