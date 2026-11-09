# Overview

> The model as implemented, in three layers. What the papers state is in
> [Original MARLEM](../original/methodology.md); why the RL layer departs from it is in
> [The RL layer](learning/examples/rl-layer.md).

## The model in three layers

**The market.** $N$ participants on a SimBench low-voltage network, each with a
load, PV and optionally a battery. Every hour, each places at most one order: a
side, a quantity, a price and a preferred partner. The orders clear in three
stages: preferred partners, then a double auction, then the DSO. What no trade
covers is settled at the DSO's two tariffs. An AC power flow, or the paper's graph
model, gives the line loading and voltage drop from which the DSO's fees are
computed, and the reputations are updated.
→ [Market step](market/step.md)

**The environment.** `MarketEnv` makes the market a multi-agent RL problem: one
agent per participant, one episode one day of 24 steps. The action is [P1]'s four
parts, the reward the agent's net bill for the step, the observation the paper's 42
signals plus the peers' reputations.
→ [Environment](environment/index.md)

**The learning layer.** RLlib's PPO in three paradigms: one policy for the whole
group (CTCE), MAPPO with a critic per agent that sees every agent (CTDE), and
independent learners (DTDE).
→ [Learning layer](learning/index.md)

[The full cycle](full-cycle.md) shows how the three nest, in one diagram.

## What is kept, changed and added

| | MARLEM ([P1], [P2]) | This implementation |
|---|---|---|
| Market mechanism | orders, three-stage clearing, DSO fees, reputation | kept; the release's defects corrected ([issue register](../original/issues/register.md)) |
| Grid | graph model on IEEE feeders or generated topologies ([methodology §6](../original/methodology.md#6-grid-p1-35)) | AC power flow on SimBench networks; the graph model kept as the alternative ([Grid methods](market/grid-methods.md)) |
| Prices | synthetic step functions, higher at peak hours, smoothed ([methodology §5.4](../original/methodology.md#54-profiles-p1-344)) | the German 2024 dynamic tariff, or a fixed time-of-use day ([Market prices](../using/data/prices.md)) |
| Action | four parts ([P1] eq. 2), decoded from one continuous vector | the same four parts, side and partner categorical, quantity and price continuous ([Action](environment/action.md)) |
| Reward | [P2]'s weighted composite reward | the net bill ([Reward](environment/reward.md)) |
| Observation | 42 signals, unscaled | the same signals, with fixed scales ([Observation](environment/observation.md)) |
| Learning | PPO, APPO and SAC, population-based training | PPO with fixed settings per run, judged against baselines on held-out days |

## Not in scope

- Forecasts in the observation: the agents see the true values.
- Recurrent or autoregressive policies. The policy is **factorised**: each action
  part is sampled independently given the observation, so the partner is not
  chosen conditionally on the side.
- The original's trade ledger, which changes no market result.
