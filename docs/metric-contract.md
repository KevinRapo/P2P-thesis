# Recorded metric contract

The following values are descriptive episode-step metrics, not reward terms or
claims of welfare, self-consumption, flexibility utilization, or coordination
convergence.

| Metric | Definition | Unit/range |
| --- | --- | --- |
| `settlement_turnover` | Sum of `trade.price * trade.quantity` | currency |
| `traded_energy` | Sum of source-side trade quantities | kWh |
| `bid_ask_spread` | Mean submitted buy price minus mean submitted sell price | currency/kWh |
| `settlement_price_volatility` | Within-step standard deviation of settlement prices | currency/kWh |
| `physical_supply_demand_imbalance` | `abs(sum(generation)-sum(demand)) / grid_capacity`, clipped to `[0,1]` | ratio |
| `grid_congestion` | Recorded grid congestion, clipped to `[0,1]` | ratio |
| `physical_balance_score` | `1 - physical_supply_demand_imbalance` | ratio |
| `local_trade_share` | P2P source-side energy divided by all traded energy | ratio |

Metrics are exposed as `info[agent_id]["kpis"]` after each environment step.

## Market analytics

`MarketMetrics` reports the same ledger-supported family at episode scope:
settlement turnover, traded energy, transaction count and mean size, mean
settlement price, transaction-price coefficient of variation, settlement-price
and volume trends, participant-volume HHI, P2P/DSO volume shares, per-agent
mean reward, and trade counts. It deliberately does not report welfare,
surplus, allocation efficiency, price discovery, liquidity, or price fairness.

`GridMetrics` reports recorded balance, congestion, clearing-volume and
transmission-loss series and their literal means/trends. `DSOMetrics` reports
DSO/P2P volumes, their shares, recorded tariff/settlement prices, price spread,
and net grid import. `CoordinationMetrics` is limited to the same observable
outcome summaries and mean recorded reward; it makes no claim about strategy,
information, battery, peak, waste, signal impact, or causal coordination.

## Experiment baselines

`src/environment/baselines.py` provides three non-learning references:
`random_valid_actions`, `dso_fallback_actions`, and
`full_information_greedy_actions`. The third sees current global physical state
and is a greedy matching reference only; it is not an optimizer or welfare
upper bound.

## Held-out evaluation

`ScenarioSplit` declares non-overlapping train, validation, and test scenario
IDs plus disjoint training, validation, and test seed lists. `RLTrainer` disables
evaluation by default; enabling it requires this declaration and independently
seeded train/validation environment configurations whose `scenario_id` values
belong to the declared split.

Each run manifest creates `episode_records.jsonl`, an append-only JSON-lines
stream for seed/episode-level metrics. `run_declared_episodes` evaluates only a
named declared split and appends one raw record per declared seed; use it for
the final test split after checkpoint selection. `run_declared_training` starts
one independent trainer per declared training seed. `EpisodeRecordStore.summarize` reports
count, mean, sample standard deviation, and a 95% normal-approximation interval
from those raw records. See [experiment-protocol.md](experiment-protocol.md)
for the required split and reporting sequence.
