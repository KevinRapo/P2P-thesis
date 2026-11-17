"""Market environment settings shared with the runner, without loading RLlib.

These sit outside ``core/env/`` because that package imports ``MarketEnv`` and Ray.
``None`` means computed from the training days or the environment's default;
``False`` switches an option off. The experiment supplies scenario, days and seed.
"""

MARKET_ENV_CONFIG = {
    "reward": "bill",
    "grid_capacity_kwh": None,
    "observation": "paper",
    "energy_scale": None,
    "reward_scale": None,
    "tariff_range": None,
    "forecast_error": 0.0,
    "episode_days": None,
    "truncate_episode": False,
    "random_start_soc": False,
    "terminal_value": False,
    "stored_kwh_value": None,
}
# Kept in step with core.env.reward.REWARDS (a test compares them).
REWARD_NAMES = ("bill", "salazar")
# Kept in step with core.env.market_env.OBSERVATIONS (a test compares them).
OBSERVATION_NAMES = (
    "paper",
    "agent",
    "agent_market",
    "pruned",
    "minimal",
    "minimal_market",
    "minimal_grid",
    "pruned_grid",
)
# What a run resolves on its training days and every later environment reuses
# (validation, the held-out days); grid_capacity_kwh only with the salazar reward (RP-1g).
SCALE_KEYS = ("energy_scale", "reward_scale", "tariff_range", "grid_capacity_kwh")
ENV_CONFIG_KEYS = tuple(MARKET_ENV_CONFIG) + ("scenario", "days", "seed")
