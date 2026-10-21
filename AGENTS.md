# AGENTS.md: implementation guide for MARLEM v1

Where things are in this repository and the rules for changing them. What the
thesis is about, where the work stands and what comes next are in the workspace's
top-level `AGENTS.md`.

This file names folders and the few files that are landmarks, not every file:
[docs/structure.md](docs/structure.md) lists every folder and script with how far
it is built. Update structure.md whenever a file is added, moved, renamed or built;
update this file only when a folder, a landmark or a rule changes.

## Folders

```
core/        the MARLEM functionality: everything a notebook can call
  grid/        the SimBench network: catalogue, topology, profiles, power flow
  config/      the scenario: network, participants, market rules; save and load
  market/      orders, matching, pricing, DSO, agents, reputation; LocalEnergyMarket
  env/         MarketEnv: the market as an RLlib multi-agent environment
  rl/          the RL layer (paradigms on RLlib), with envs/ (test environments)
  runner/      experiments: start, watch, stop and sync training runs
  settings.py  this machine's settings (.env)
experiments/ experiment specs (JSON, tracked): which runs to train
scenarios/   saved scenarios (JSON, the Studio's format)
notebooks/   call core/ only: market/, rl/, runner/
tests/       market/, rl/, runner/
studio/      the NiceGUI Studio: pages/ and components/ on top of adapters/
docs/        the documentation (Markdown); docs_site/ builds the website from it
hpc/         targets.toml: where experiments run (local, TalTech)
scripts/     the Jupyter job on the cluster
runs/        training runs and results (git-ignored); the runner's one source of truth
```

### Landmarks

- **The market's API**: `LocalEnergyMarket` in `core/market/lem.py` (the one class
  that runs a market step and its power flow), `Scenario` in `core/config/`, the
  grid's records and `GridModel` protocol in `core/grid/contract.py`.
- **The power flow**: `core/grid/powerflow.py` (`SimBenchGrid`); `core/grid/` is the
  only place that imports pandapower or simbench.
- **The RL entry points**: `build_config` / `build_algo` (`core/rl/config.py`),
  `train(Run(...))` (`core/rl/train.py`), `evaluation` (`core/rl/policy.py`).
- **Experiments**: `python -m core.runner start / status / stop / sync / check`;
  the JSON spec's fields are in `core/runner/spec.py`, usage in
  [docs/v1.md §4](docs/v1.md) and [docs/hpc/](docs/hpc/).
- **Settings**: `core/settings.py` reads the environment, else `.env` (keys in
  `.env.example`), else a default. Never hard-code a machine or account value: add
  a key.

## Layer rules

```
core/  <-  notebooks/
core/  <-  studio/adapters/  <-  studio/pages/, studio/components/
```

- **`core/`** imports nothing from `studio/` or `notebooks/`. Every rule of the
  market or the network lives here, so a notebook can check it.
- **Inside `core/`**:
  - `grid`, `config`, `market` import nothing from `env`, `rl` or `runner`;
    `config` may import `grid`, never the reverse.
  - `rl` imports no market module: the environment arrives as a class, so the
    probes still test it alone.
  - `env` imports the market, never `rl`.
  - `runner` is the one place that knows both `env` and `rl`, and imports them
    only inside a job, so reading status stays fast. Neither imports the runner.
  - `settings.py` imports nothing from the project, so anything may use it.
- **`notebooks/`** import `core/` only. They find the repository root from wherever
  they run and write runs to `<root>/runs/`.
- **`studio/adapters/`** is a thin layer over `core/`: caching, background threads,
  the current scenario, the market being played between clicks, the experiments in
  `runs/`, workspace paths. No domain rules and no records that copy the core's.
  Test for any logic here: if a notebook would want it too, it belongs in `core/`.
- **`studio/pages/` and `studio/components/`** call the adapters. They may import
  the core's plain data records to display them, but never construct or drive a
  core engine class (`MarketService` holds the `LocalEnergyMarket` for the Studio).

When something looks wrong in the Studio, reproduce it in a notebook first. If the
notebook shows it, the problem is in `core/`; if not, it is in `studio/`.

## Code conventions

- **Pages and components.** A page is one file in `studio/pages/`; code only it
  uses stays there. A component goes in `studio/components/` only once a second
  place uses it, not before.
- **Sections.** A file that does more than one thing is split into sections with a
  banner whose title says what the section is for:

  ```python
  # --------------------------------------------------------------------------------------
  # Catalog: which networks exist and their names
  # --------------------------------------------------------------------------------------
  ```

  Inside a large class, a one-line marker groups methods:
  `    # --- Network cache ----------…`. Put new code in the section it belongs to.
- **Issue IDs.** A docstring that fixes or decides an issue names its ID from the
  [register](docs/validation/register.md).
- New Python files: Black style, 88-character lines.
- Never `git stash` in these worktrees.

## Keep the paper's grid functionality

The paper's graph grid model is to be added as a second grid method on the same
SimBench network (see the top-level `AGENTS.md`). Until it exists, do not delete
original-paper grid or market functionality, or anything it could use, only
because nothing calls it today (e.g. `electrical_distance`, the paths and zones of
`core/grid/powerflow.py`, the ledger, the reputation helpers,
`core/market/profile/`). When unsure, keep it and ask.

## RL layer

- RLlib's own PPO, APPO and SAC with RLlib's own modules: no custom losses,
  distributions or training loops. Only the environment (grouping, central state)
  and, for CTDE, what the actor reads differ between paradigms. Same network
  settings for every paradigm.
- Objectives: DTDE and CTDE learn from each agent's own reward; CTCE is one
  controller on the summed reward.
- An environment the trainer can use is a `MultiAgentEnv` built as
  `Env(env_config)`, with `agents_id`, `observation_spaces` and `action_spaces`
  (one `Box` per agent) and `"__all__"` in `terminateds` and `truncateds`.
  `MarketEnv` and the test environments in `core/rl/envs/` provide this.
- **Run the probes first after any change to `core/rl/` or its test environments**
  (`tests/rl/`, `notebooks/rl/probe_paradigms.ipynb`). The probes follow Andy
  Jones's guide (https://andyljones.com/posts/rl-debugging.html); each has an
  exact answer.
- The original RL code with its `FAULT`, `DECIDE` and `DEVIATION` annotations is
  on the `clean` branch, under `RL/core/rl/`.

## Running

- Start training experiments with `python -m core.runner`, not from a notebook
  cell, so they outlive the session.
- A seed repeats a run only with `PYTHONHASHSEED` fixed (the runner's jobs do
  this) and with algorithms built by `core.rl.config.build_algo`, not
  `config.build_algo()`, so the replay buffer follows the seed.
- RL notebooks put the repository root on `PYTHONPATH` before Ray starts, so
  worker processes can import `core.rl`.
- Several processes that each load torch (parallel runs, or environment runners
  set in a spec) can fail with "The paging file is too small" on this machine;
  Ray's start-up also fails sometimes under load (a run then shows `failed` or
  `lost`). Run fewer in parallel; `start` on the same experiment re-runs only
  those.
