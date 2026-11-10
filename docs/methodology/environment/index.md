# The environment: the market as an RL problem

> `MarketEnv` is the middle loop of [the full cycle](../full-cycle.md): it turns the
> agents' actions into orders, lets the market play one step
> ([The market step](../market/step.md)) and turns the step's record into rewards and
> observations.

## The market as an environment

The full definition is in the module docstring of
[market_env.py](../../../core/env/market_env.py). In short:

- **Agents:** one per scenario participant.
- **Episode:** one market day by default, drawn at each reset from the training
  days, or a window of `episode_days` days. The window's end terminates the episode
  unless `truncate_episode` is set.
- **Action and observation:** [Action](action.md) and
  [Observation](observation.md).
- **Reward** ([Reward](reward.md)): the agent's net bill for the step, scaled:
  `(profit + p_FiT · deferred_supply − p_utility · deferred_demand) / reward_scale`.
  What no trade covers is settled at retail (MP-1e): untraded imports at the utility
  price, untraded exports at the feed-in tariff, without grid fees.
- **Baselines:** `zero_policy` (never trade) and `net_position_policy` (the
  market's own bidding rule: offer the surplus, ask for the deficit, battery first).

Choices made here that the papers leave open, with the reason:

| Choice | Decision | Why |
|---|---|---|
| Objective | individual bill per agent | self-interested prosumers; CTCE keeps the welfare objective as the planner benchmark |
| Reward | net bill, not the paper's five-part weighted reward | the economic outcome itself; no hand-tuned weights; the paper's reward has three inconsistent versions ([papers.md](../../original/issues/papers.md)) |
| Action | the quantity as a share of the feasible bound, the price in [FiT, utility] | no infeasible or rejected orders (E-04, E-05); prices outside the tariffs are dominated |
| Scaling | fixed scales in the environment | the same in training and evaluation; returns of order 1-10 |
| Day end | termination by default; `truncate_episode` and `terminal_value` as options | a market day settles and the hour is observed; the alternatives are an experiment (RP-1f) |
| Days | drawn from a list per episode | train on some days, evaluate on held-out periods (L-17) |

## The environment step

[`MarketEnv.step`](../../../core/env/market_env.py#L459-L544): the agents' actions in,
observations and rewards out, one market step in the middle.

The step in four parts, each on the page that holds it:

- **E1. Decode** the action into an order: [Action](action.md#e1-decode).
- **Then the market step**: phases 1 to 8 ([The market step](../market/step.md)), with these intents as phase 2a.
- **E2. Reward** from the market's outcome: [Reward](reward.md#e2-reward).
- **E3. Observation** for the next step: [Observation](observation.md#where-it-is-made-and-what-is-not-seen).
- **E4. Episode end**, below.

**E4. Episode end.** After the day's last step the episode is **terminated**
(RP-1f): the return ends at midnight and nothing is bootstrapped into the next day,
because each day starts fresh (batteries at their initial charge, reputations at
0.5). Energy left in a battery at midnight is therefore worth nothing to the agents
(MP-1c). Environment settings change this for an experiment: `episode_days` plays
consecutive days with the batteries and reputations carried over midnight,
`truncate_episode` bootstraps the return from the next day's start, and
`terminal_value` pays for the stored energy; a test period is played without a reset
([`day_end.json`](../../../config/experiments/day_end.json) compares them).

| | |
|---|---|
| **Reads** | the actions; the `StepRecord` of the market step |
| **Computes** | intents; rewards; next observations; the step's metrics (`infos`) |
| **Writes** | `last_record` |
| **Code** | above; metrics: [`_market_infos`](../../../core/env/market_env.py) |
| **Paper** | [P1] §3.9 phases 5 (reward) and 7 (observation); eq. 2 (the action) |
| **Decisions** | the reward is the net bill, not [P2]'s composite reward (E-13 to E-22); observations normalised (E-06); the true future in the forecasts by default, `forecast_error` as an option (E-05); the day terminated (RP-1f); *Open: RP-1a to RP-1e* ([plans](../../temp/index.md)) |
