# core/env/: the market as an RL environment

`MarketEnv` is an RLlib `MultiAgentEnv` over `LocalEnergyMarket`: one agent per
participant, one episode per market day (or window of days). It only translates
actions into orders and the step's record into observations and rewards; the market
rules stay in `core/market/`. The design: [Environment](../../environment/index.md).

| Module | What it is |
|---|---|
| [`market_env`](../../../api/env/market_env.md) | `MarketEnv`: the mixed action decoded into an order, the observation, episodes over days, the baselines `zero_policy` and `net_position_policy` |
| [`reward`](../../../api/env/reward.md) | The rewards, chosen by `env_config["reward"]`: `NetBillReward` (the default) and `SalazarReward` (the original code's) |

Its settings and their defaults are in [`env_defaults`](../index.md#shared-helpers),
outside the package, so the runner can read them without loading RLlib.
