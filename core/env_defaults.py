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
OBSERVATION_NAMES = ("paper", "pruned", "minimal", "minimal_market", "minimal_grid", "pruned_grid")
SCALE_KEYS = ("energy_scale", "reward_scale", "tariff_range")
ENV_CONFIG_KEYS = tuple(MARKET_ENV_CONFIG) + ("scenario", "days", "seed")
