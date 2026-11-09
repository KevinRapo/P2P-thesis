# Experiments

> The experiments run with this tool and what they showed. Each experiment is a
> file in [config/experiments/](../../config/experiments/); how to run one is in
> [Starting and following runs](../using/running/runs.md).

**The thesis's results** come from two experiments on one shared setup:
[Thesis experiments](thesis.md).

| Experiment | Question |
|---|---|
| `thesis_grid_methods` | What changes when the fees see the grid through the AC power flow instead of [P1]'s graph model? The main result |
| `thesis_reward_obs` | Do our reward and observation serve the participants better than the original's? |

**Exploratory runs** came before them, to find settings that learn:

| Experiment | Question | Page |
|---|---|---|
| `market_s3`, `market_s3_ctce`, `market_s4_*`, `scale_*` | Do the paradigms learn the market reliably over seeds, and with more agents? | [Market runs](market-s3.md) |
| `grid_methods` | The grid methods set up first, on `validate_market` (5 participants) | [Grid methods](../methodology/market/grid-methods.md) |
