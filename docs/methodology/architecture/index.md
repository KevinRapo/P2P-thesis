# Architecture

> How the code is organised, in three levels: this page (the folders and the rules
> between them), one page per package (its modules and how they connect), and the
> [API Reference](../../api/index.md) (one page per module: its classes and
> functions, from the docstrings).

## The folders

```text
marlem-v2/
├─ core/                           the functionality: everything a notebook can call
│  ├─ config/                      the scenario: network, participants, market rules
│  │  ├─ scenario.py
│  │  └─ …
│  ├─ grid/                        the SimBench network and its power flow
│  │  ├─ powerflow.py
│  │  └─ …
│  ├─ market/                      orders, matching, pricing, DSO, reputation
│  │  ├─ lem.py                    LocalEnergyMarket: one market step
│  │  ├─ agent/                    the participants: DER, battery
│  │  └─ …
│  ├─ env/                         the market as an RL environment
│  │  ├─ market_env.py
│  │  └─ …
│  ├─ rl/                          PPO in three paradigms on RLlib
│  │  ├─ train.py
│  │  ├─ envs/                     the probe environments
│  │  ├─ scripts/                  the probe scripts
│  │  └─ …
│  ├─ runner/                      experiments: start, watch, stop, sync
│  │  ├─ spec.py
│  │  └─ …
│  ├─ settings.py                  this machine's settings (.env)
│  └─ …                            files.py, env_defaults.py, rl_defaults.py
├─ studio/                         the NiceGUI interface
│  ├─ adapters/                    thin layer over core/
│  │  ├─ run_service.py
│  │  └─ …
│  ├─ components/                  shared building blocks: charts, tables
│  ├─ pages/                       one file per page; market/ and results/ have tabs
│  └─ …
├─ config/                         data, not code
│  ├─ data/                        market price data
│  ├─ experiments/                 experiment specs: which runs to train (JSON)
│  └─ scenarios/                   saved scenarios (JSON)
├─ notebooks/                      market/, rl/, runner/; they call core/ only
├─ tests/                          market/, rl/, runner/, studio/
├─ hpc/                            where experiments run (targets.toml), the cluster jobs
├─ docs/                           this documentation (Markdown)
├─ docs_site/                      builds the website from docs/
├─ runs/                           training runs and results (not in git)
└─ run_studio.py, mkdocs.yml, …    entry points, the docs site's settings
```

A package shows one landmark module; `…` stands for the others, listed one line each
on the package's page. The same as a diagram:

```mermaid
%%{init: {"flowchart": {"rankSpacing": 10, "nodeSpacing": 24, "padding": 8, "subGraphTitleMargin": {"top": 4, "bottom": 6}}}}%%
flowchart TB
  subgraph other["top level"]
    direction TB
    nb["notebooks/"]:::code ~~~ tests["tests/"]:::code ~~~ hpc["hpc/"]:::data ~~~ runs["runs/ (not in git)"]:::data
  end

  subgraph studio["studio/"]
    direction TB
    s1["pages/ · components/"]:::code ~~~ s2["adapters/"]:::code
  end

  subgraph cfg["config/"]
    direction TB
    f1["data/"]:::data ~~~ f2["experiments/"]:::data ~~~ f3["scenarios/"]:::data
  end

  subgraph core["core/"]
    direction TB
    c0["shared helpers"]:::code ~~~ c1["config/"]:::code ~~~ c2["grid/"]:::code ~~~ c3["market/"]:::code
    c3 ~~~ c4["env/"]:::code ~~~ c5["rl/"]:::code ~~~ c6["runner/"]:::code
  end

  click c0 href "#shared-helpers" _self
  click c1 href "packages/config/" _self
  click c2 href "packages/grid/" _self
  click c3 href "packages/market/" _self
  click c4 href "packages/env/" _self
  click c5 href "packages/rl/" _self
  click c6 href "packages/runner/" _self
  click f1 href "around/#config-settings-and-data" _self
  click f2 href "around/#config-settings-and-data" _self
  click f3 href "around/#config-settings-and-data" _self
  click s1 href "packages/studio/" _self
  click s2 href "packages/studio/" _self
  click nb href "around/#notebooks" _self
  click tests href "around/#tests" _self
  click hpc href "around/#everything-else" _self
  click runs href "around/#everything-else" _self

  classDef code fill:#dcfce7,stroke:#15803d,color:#111
  classDef data fill:#dbeafe,stroke:#1d4ed8,color:#111
```

Green holds code, blue holds data and settings. Click a folder to open its page.

| Package | What it is | Page |
|---|---|---|
| `core/config/` | The scenario: everything set before the market runs, as plain data | [Config](packages/config.md) |
| `core/grid/` | The SimBench network: loading, topology, profiles, the power flow, the graph model | [Grid](packages/grid.md) |
| `core/market/` | The MARLEM market: participants, DSO, clearing, fees, reputation, signals | [Market](packages/market.md) |
| `core/env/` | The market as a multi-agent RL environment: actions, observations, rewards | [Environment](packages/env.md) |
| `core/rl/` | The learning layer: PPO in three paradigms on RLlib | [RL](packages/rl.md) |
| `core/runner/` | Experiments: starting, watching and reading runs, here or on a cluster | [Runner](packages/runner.md) |
| `studio/` | The NiceGUI interface | [Studio](packages/studio.md) |
| `config/`, `notebooks/`, `tests/`, the rest | Data and settings, notebooks, tests, cluster helpers, docs | [Around the code](around.md) |

## The layers

An arrow means "imports"; only the main imports are drawn.

```mermaid
%%{init: {"flowchart": {"rankSpacing": 34, "nodeSpacing": 18, "padding": 8}}}%%
flowchart LR
  ui["studio/pages/<br/>components/"]:::code --> ad["studio/adapters/"]:::code
  nb["notebooks/"]:::code --> runner
  nb --> rl
  nb --> market
  ad --> runner["core/runner/"]:::code
  ad --> market["core/market/"]:::code
  runner --> env["core/env/"]:::code
  runner --> rl["core/rl/"]:::code
  env --> market
  market --> base["core/config/ ↔<br/>core/grid/"]:::code

  classDef code fill:#dcfce7,stroke:#15803d,color:#111
  classDef data fill:#dbeafe,stroke:#1d4ed8,color:#111
```

Four rules keep the layers apart:

- **`core/` never imports `studio/` or `notebooks/`.** Anything that looks wrong in
  the Studio can be reproduced in a notebook, which tells a core problem from a UI
  one.
- **`core/rl/` imports no market module.** The environment arrives as a class, so
  the RL probes test the learner alone.
- **`core/runner/` is the one place that knows both** the environment and the
  learner, and it loads them only inside a training job.
- **`core/grid/` is the only place that imports pandapower and SimBench.** It hands
  out plain records, never pandapower objects.

`core/config/` and `core/grid/` import each other: placing participants needs the
network, and the power flow reads the grid settings.

## Shared helpers

Four modules directly in `core/`, which any layer may use. Each is light on purpose:
importing them loads neither Ray nor the market
([API](../../api/helpers/index.md)).

| Module | What it is |
|---|---|
| [`settings`](../../api/helpers/settings.md) | This machine's settings (cluster account, SSH host, folders), from the environment or `.env` |
| [`files`](../../api/helpers/files.md) | Atomic file and JSON writes, shared by training and the runner |
| [`env_defaults`](../../api/helpers/env_defaults.md) | The environment's settings and their defaults, for the runner without loading RLlib |
| [`rl_defaults`](../../api/helpers/rl_defaults.md) | PPO's and the network's default settings, so an experiment can be written out in full without loading Ray |
