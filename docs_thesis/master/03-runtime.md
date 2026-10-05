# 3. Constructing the runtime

[Previous: participants](02-participants.md) · [Master overview](README.md)

## Why this stage exists

Saved records must become live objects: participant agents, battery state, profile
providers, market configuration, DSO and grid model. The factory is intended to
make this conversion consistent across workers, notebooks and RLlib runners.

## What goes in and comes out

`build_env_config(resolved, cell, episode_seed)` currently returns a plain dictionary:

```python
{
    "marlem_resolved_file": resolved.to_data(),
    "cell": cell.model_dump(mode="json"),
    "episode_seed": episode_seed,
}
```

The intended next conversion is `build_env(env_config) -> LocalEnergyMarket`.
**It currently raises `NotImplementedError`.** Our example stops at this boundary;
there is no verified configured-SimBench execution to follow beyond it yet.

The existing environment instead expects a different dictionary with entries
such as `max_steps`, `market_config`, `agents`, and optional grid/DSO/profile
objects. Passing the serialized dictionary above straight to its constructor
does not bridge the formats.

## Where it happens

| Function / class | Responsibility and current behaviour |
|---|---|
| [build_env_config](../../src_thesis/experiments/factory/environment.py) | Serializes configuration and one cell |
| [build_env / build_grid](../../src_thesis/experiments/factory/environment.py) | Intended construction; both raise `NotImplementedError` |
| [LocalEnergyMarket.__init__](../../src_thesis/environment/lem.py) | Existing constructor: obtains agents and helpers, assigns graph locations, constructs matcher and observation/action/reward handlers |
| [LocalEnergyMarket.reset](../../src_thesis/environment/lem.py) | Resets counters, profiles, agents, market and grid, then returns initial observations |

## Who calls it

The factory's docstrings name workers, dry runs, notebooks and RLlib runners as
intended callers. The Studio dry run does not currently call it.

The existing [`RLTrainer`](../../src_thesis/marl/train.py) accepts an environment
class and config, and supplies an environment choice through its RLlib setup.
Its default class is obtained through `market_env_cls`. Grouped configurations
use `GroupedLEM`. The concrete existing environment's constructor/reset path can
therefore be studied separately from the unfinished experiment factory.

## Current status

**Factory: stub. Existing environment: implemented behaviour with unresolved
methodological issues.** Its runtime still depends on the earlier graph-based
grid. The SimBench catalogue/preview adapter does not establish a completed
step-time SimBench integration.

One consequential detail: `reset` asks `der_profile_handler.reset` for each
agent's generation and demand and passes them into `agent.reset`. Profiles given
earlier to an agent can be overwritten. This is tracked as I-05 in the
[issue register](../thesis/validation/issues.md). Naming a profile in the draft
is not yet proof that it drives the existing environment's episodes.

**Next:** [4. One market timestep](04-timestep.md). From here we explain the
existing environment implementation, rather than pretending the factory gap is closed.
