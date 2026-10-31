"""Market environment settings shared with the runner, without loading RLlib.

These sit outside ``core/env/`` because that package imports ``MarketEnv`` and Ray.
``None`` means computed from the training days or the environment's default;
``False`` switches an option off. The experiment supplies scenario, days and seed.
"""

MARKET_ENV_CONFIG = {
    "energy_scale": None,
    "reward_scale": None,
    "episode_days": None,
    "truncate_episode": False,
    "random_start_soc": False,
    "terminal_value": False,
    "stored_kwh_value": None,
}
SCALE_KEYS = ("energy_scale", "reward_scale")
ENV_CONFIG_KEYS = tuple(MARKET_ENV_CONFIG) + ("scenario", "days", "seed")
