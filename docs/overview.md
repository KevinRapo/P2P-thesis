# Overview: PPO with the paper's mixed market action

> Branch `marlem-v2` (worktree `workspace/marlem-v2`): the market on SimBench
> networks with an AC power flow or the paper's graph model, RLlib's PPO in the
> three paradigms with the paper's four action components as genuine categorical
> and continuous parts, the runner, SLURM submission, synchronisation, results and
> the Studio. These pages are not published (see [About](about.md#publishing)).

## Scope

| Part | What this branch does |
|---|---|
| Algorithm | PPO only (RLlib's loss, modules and distributions) |
| Paradigms | CTCE, CTDE, DTDE |
| Market action | the four parts of [P1] eq. 2: side and partner categorical, quantity and price continuous |
| Partner β | learned, passed to the order as chosen |
| Observation | the paper's 42 signals and the peers' reputations (46 with five agents; [Observation](full-cycle/environment/observation.md)) |
| Scales | resolved on the training days, recorded, reused everywhere |
| Grid | one scenario setting selects the power flow or the graph model ([grid methods](experiments/grid-methods.md)) |

Not in scope: other algorithms, forecasts in the observation, recurrent policies,
a new grid-distance model, the original's blockchain-style trade ledger (it changes
no market result) and an autoregressive policy. The policy is **factorised** over
the action parts (one distribution per part, sampled independently given the
observation): the partner is not chosen conditionally on the sampled side or price.
Multi-node learners and other training backends are not needed and not added.

## The layers

The application is the market, the environment around it and the learning layer on
top, with the tooling to run and read them. Each part has one page that holds its
description.

- **The market.** The MARLEM market on a SimBench network: orders, three clearing
  stages, settlement, an AC power flow or the graph model, the DSO's fees and
  reputation. [The market step](full-cycle/market-step.md) follows it phase by phase,
  with the code, the equations and the decisions behind each phase.
- **The market as an environment.** `MarketEnv` turns the agents' actions into
  orders and the market's record into rewards and observations:
  [The environment](full-cycle/environment/index.md), with its
  [action](full-cycle/environment/action.md),
  [reward](full-cycle/environment/reward.md) and
  [observation](full-cycle/environment/observation.md).
- **The learning layer.** PPO in the three paradigms on that environment:
  [The learning layer](full-cycle/learning/index.md), with
  [one iteration step by step](full-cycle/learning/iteration.md),
  [worked examples](full-cycle/learning/examples.md) and the
  [probes](full-cycle/learning/probes.md) that check it.
- **Running it.** Scenario and experiment settings ([Config](config/reference.md)),
  what a run records ([The run contract](config/run-contract.md)), how to start runs
  and read their results ([Training experiments](hpc/experiments.md),
  [Results](config/results/index.md)) and where the code is
  ([Code structure](structure.md)).
- **What is left to do.** [Plans](plan/index.md): the market plan, the RL plan, the
  decision log and the [list of open items](plan/open.md).

[The full cycle](full-cycle/index.md) joins the three first layers in one diagram.
