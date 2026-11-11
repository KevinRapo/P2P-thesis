# First steps: from a network to a trained policy

> One pass through the workflow, in the order the tool is built:
> 1. look at a network;
> 2. build a scenario on it;
> 3. play the market by hand;
> 4. train;
> 5. read the results.
>
> Each step names the Studio page to use and the page that explains it. It assumes
> the [setup](setup.md) is done and the Studio is running.

## 1. Look at a network: Inspect

Every market runs on a [SimBench](../using/data/simbench.md) low-voltage network. These
are German benchmark grids with real line data and a year of load and PV profiles.

Open **Build → Inspect** and pick a network, for example `1-LV-rural3--2-sw`. It
shows:
- its topology and size;
- its loads and generators;
- their profiles over the year, one element at a time, per profile, or summed over
  the whole network;
- SimBench's study cases.

The [network catalogue](../using/data/networks.md) compares all of them.

## 2. Build a scenario: Scenario

A **scenario** fixes four things:
- the network and the day;
- which elements belong to market **participants**; the rest is **background**,
  which loads the grid but does not trade;
- the market's settings: pricing, the DSO's fees, the tariffs.

Open **Build → Scenario**. Then either load one from
[config/scenarios/](../../config/scenarios/), or place participants on a network
and save a new one.

| Scenario | Use |
|---|---|
| `validate_market.json` | Five participants on `rural1--0`. Small; the tests and the market notebooks use it |
| `lv_rural3_p13.json` | Thirteen participants on `rural3--2`. The current experiments use it |

Every setting is explained in the [config reference](../using/running/config.md).

## 3. Play the market by hand: Validate → Market

On the **Step** tab, the scenario's market plays one hour at a time, each stage
shown on its own:
1. the orders;
2. the three clearing stages: preferred partners, the double auction, the DSO;
3. settlement;
4. the power flow;
5. the DSO's fees.

No learning is involved: the participants bid by a fixed rule.

The **Probes** tab plays scripted cases whose outcome is known in advance. This is
the place to understand the market before trusting any training result.
[The market step](../methodology/market/step.md) explains each stage with its
equation and the code behind it.

## 4. Train: an experiment

An **experiment** is a JSON file in
[config/experiments/](../../config/experiments/). It combines:
- a scenario;
- training and test days;
- the paradigms (CTCE, CTDE, DTDE);
- seeds;
- a budget of environment steps;
- PPO settings.

Each combination is one **run**.

The smallest experiment checks that everything works end to end. These commands
start its test version on this PC and show its progress:

```
python -m core.runner check config/experiments/smoke.json
python -m core.runner start config/experiments/smoke.json --profile test
python -m core.runner status smoke--test
```

The same experiments can be started from **Build → Experiments** and
**Experiments → Runs** in the Studio.

To run on the TalTech cluster, add `--target taltech` and follow the
[HPC setup](hpc-setup.md). The commands are explained in
[Starting and following runs](../using/running/runs.md).

Each run trains, then plays the test days with the trained policy and with fixed
**baselines**. It writes everything to `runs/<experiment>/<run>/`, as described in
[What a run saves](../methodology/evaluation/files.md).

## 5. Read the results: Results

Open **Experiments → Results** and tick the runs. It has four tabs:

| Tab | Answers |
|---|---|
| Learning | Did training converge? |
| Validation | How good is the trained policy compared with the baselines and the best possible ([metrics](../methodology/evaluation/metrics.md))? |
| Market | What did the market do? |
| Grid | What did the grid do? |

The [notebook](../../notebooks/runner/results.ipynb) reads the same results in
Python.

## Where to go next

| You want to… | Read |
|---|---|
| Understand what the model computes | [Methodology](../methodology/index.md), starting at [the market step](../methodology/market/step.md) |
| Know what the original MARLEM states, and what was wrong with it | [Original MARLEM](../original/methodology.md) and the [issue register](../original/issues/register.md) |
| Find or change code | [Architecture](../methodology/architecture/index.md) and [the full cycle](../methodology/full-cycle.md) |
| Know how the tool was checked | [Validation](../methodology/validation/index.md) |
| Run many experiments on the cluster | [HPC](../using/running/hpc/index.md) |
| Look up a term | [Glossary](glossary.md) |
