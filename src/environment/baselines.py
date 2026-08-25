"""Small, deterministic/non-learning action baselines for experiment comparison."""

from typing import Callable, Dict, Optional

import numpy as np

from .lem import LocalEnergyMarket


def _feasible_quantity(environment: LocalEnergyMarket, agent_id: str) -> tuple[bool, float]:
    """Return the physical import/export direction and kWh quantity for this step."""
    agent = environment._agents[agent_id]
    generation = agent.get_generation(environment.current_step)
    demand = agent.get_demand(environment.current_step)
    is_buy = demand > generation
    quantity = min(abs(demand - generation), environment.market_config.max_quantity)
    return is_buy, quantity


def random_valid_actions(environment: LocalEnergyMarket,
                         seed: Optional[int] = None) -> Dict[str, np.ndarray]:
    """Sample valid prices and physically feasible signed quantities.

    Without an explicit seed, consume the environment's reset-seeded generator
    so declared episode seeds reproduce this baseline exactly.
    """
    rng = np.random.default_rng(seed) if seed is not None else environment._rng
    actions = {}
    for agent_id in environment.agent_order:
        is_buy, maximum = _feasible_quantity(environment, agent_id)
        quantity = rng.uniform(0.0, maximum) if maximum else 0.0
        price = rng.uniform(environment.market_config.min_price, environment.market_config.max_price)
        actions[agent_id] = np.array([price, quantity if is_buy else -quantity], dtype=np.float32)
    return actions


def dso_fallback_actions(environment: LocalEnergyMarket) -> Dict[str, np.ndarray]:
    """Submit deliberately non-crossing quotes so residuals settle through the DSO."""
    actions = {}
    for agent_id in environment.agent_order:
        is_buy, quantity = _feasible_quantity(environment, agent_id)
        price = environment.market_config.min_price if is_buy else environment.market_config.max_price
        actions[agent_id] = np.array([price, quantity if is_buy else -quantity], dtype=np.float32)
    return actions


def full_information_greedy_actions(environment: LocalEnergyMarket) -> Dict[str, np.ndarray]:
    """Use current global supply/demand to submit immediately crossing feasible orders.

    This is a transparent perfect-current-state reference, not an optimization
    proof or an economic-optimum claim.
    """
    actions = {}
    for agent_id in environment.agent_order:
        is_buy, quantity = _feasible_quantity(environment, agent_id)
        price = environment.market_config.max_price if is_buy else environment.market_config.min_price
        actions[agent_id] = np.array([price, quantity if is_buy else -quantity], dtype=np.float32)
    return actions


def run_baseline_episode(environment: LocalEnergyMarket,
                         policy: Callable[[LocalEnergyMarket], Dict[str, np.ndarray]],
                         seed: Optional[int] = None) -> Dict[str, float]:
    """Run one baseline episode and return a raw-record-compatible summary."""
    environment.reset(seed=seed)
    total_reward = 0.0
    steps = 0
    done = False
    while not done:
        _, rewards, terminated, truncated, _ = environment.step(policy(environment))
        total_reward += float(sum(rewards.values()))
        steps += 1
        done = terminated["__all__"] or truncated["__all__"]
    return {"seed": seed, "steps": steps, "episode_return": total_reward,
            "total_reward": total_reward,
            "mean_agent_reward": total_reward / len(environment.agent_order)}
