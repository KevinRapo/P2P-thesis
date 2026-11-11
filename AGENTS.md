# AGENTS.md: implementation guide for MARLEM v2

Branch `marlem-studio` (checked out as `marlem-v2/`): the market, grid, Studio and runner, with RLlib's PPO and the
paper's mixed market action (continuous price and quantity, categorical side and
partner). What it does and why is in the [overview](docs/methodology/index.md). On the cluster this
branch is its own checkout, `~/marlem-v2`, with its own `runs/`.

Where things are in this repository and the rules for changing them. What the
thesis is about, where the work stands and what comes next are in the workspace's
top-level `AGENTS.md`.

This file names folders and the few files that are landmarks, not every file:
The [Architecture](docs/methodology/architecture/index.md) section has one page per package,
one line per module (the details are in the module's docstring, shown in the API
Reference). Update the package's page whenever a module is added, moved, renamed or
removed; update this file only when a folder, a landmark or a rule changes.

## Folders

```
core/        the MARLEM functionality: everything a notebook can call
  grid/        the SimBench network: catalogue, topology, profiles, power flow
  config/      the scenario: network, participants, market rules; save and load
  market/      orders, matching, pricing, DSO, agents, reputation; LocalEnergyMarket
  env/         MarketEnv: the market as an RLlib multi-agent environment
  rl/          the RL layer (paradigms on RLlib), with envs/ (the probe
               environments) and scripts/ (the probe check)
  runner/      experiments: start, watch, stop and sync training runs
  settings.py  this machine's settings (.env)
config/      experiments/: experiment specs (JSON, tracked), which runs to train;
             scenarios/: saved scenarios (JSON, the Studio's format)
notebooks/   call core/ only: market/, rl/, runner/
tests/       market/, rl/, runner/
studio/      the NiceGUI Studio: pages/ and components/ on top of adapters/
docs/        the documentation (Markdown); docs_site/ builds the website from it
hpc/         targets.toml: where experiments run (local, TalTech); the Jupyter job
             on the cluster (hpc.ps1 / hpc.cmd, jupyter.slurm)
runs/        training runs and results (git-ignored); the runner's one source of truth
```

### Landmarks

- **The market's API**: `LocalEnergyMarket` in `core/market/lem.py` (the one class
  that runs a market step and its power flow), `Scenario` in `core/config/`, the
  grid's records in `core/grid/contract.py`.
- **The observation signals**: `core/market/signals.py`, the paper's 42 signals
  (KPIs, market and agent signals), each a plain function; `MarketEnv` scales them
  into the observation.
- **The power flow**: `core/grid/powerflow.py` (`SimBenchGrid`); `core/grid/` is the
  only place that imports pandapower or simbench.
- **The RL entry points**: `build_config` / `build_algo` (`core/rl/config.py`),
  `train(Run(...))` (`core/rl/train.py`), `evaluation` (`core/rl/policy.py`).
- **Experiments**: `python -m core.runner start / status / stop / sync / check`;
  the JSON spec's fields are in `core/runner/spec.py`, usage in
  [docs/using/running/runs.md](docs/using/running/runs.md) and [docs/using/running/hpc/](docs/using/running/hpc/index.md).
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

- **One name per layer.** When a call passes through layers that each do their
  own part, each layer names its part, so a search lands on one of them:
  - a page's event handler is `on_<what>` (`on_sync`, `on_stop_run`);
  - a Studio service names what it does to what (`RunService.start_experiment`,
    `check_target`, `experiments`);
  - an interface keeps the plain verb its implementations share (`Target.start`,
    `Target.sync`), and its place-specific step has its own (`Target._launch`);
  - a back end names its action (`launch.start_worker`, `slurm.submit`,
    `slurm.cancel`).
  A service that only hands a call on unchanged (`ResultsService.learning_curves`
  -> `results.learning_curves`) keeps the core's name, and an interface's
  implementations share theirs (`reset`, `step`, `assess`): there the same name
  means the same thing.
- **Pages and components.** A page is one file in `studio/pages/`; code only it
  uses stays there. A page whose tabs each need a file gets a folder of its own
  (`studio/pages/market/`: `page.py` with the frame and the tab bar, one file per
  tab, `__init__.py` exporting `page`). A component goes in `studio/components/`
  only once a second place uses it, not before.
- **What a page remembers.** A page is built anew on every visit. A choice that
  decides what a page shows goes through `remember` (`studio/components/memory.py`),
  before its handlers are connected; the scenario, the experiment and the market stay
  in the services.
- **Charts.** A chart on a page is a small subclass of `SeriesChart`,
  `NetworkChart` or `Chart` (`studio/components/charts.py`) whose `draw()` says
  what to draw from its options; `show()` places it and a control that changes it
  comes from the chart (`chart.switch`, `chart.select`, `chart.slider`), so a page
  writes no redraw code. Colours with a meaning are in `studio/theme.py`. The
  Components page shows every building block with its code.
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
  [register](docs/original/issues/register.md); one that implements a plan decision
  names its `MP-` or `RP-` ID from [open items](docs/temp/open.md), the one list of
  every question, open or decided. The order of the work and how a question is
  taken: [docs/temp/index.md](docs/temp/index.md).
- **Markers.** Four comment markers, listed in the workspace's `.vscode/settings.json`
  (Todo Tree): `FAULT` (still broken), `BUG` (a bug to fix), `DEVIATION` (our own choice,
  differing from the paper or the original) and `OPEN` (not decided). An open question is `# OPEN <ID>: question`, with the choice
  used for now; the ID (a register ID such as `E-10`, or an `MP-`/`RP-` ID such as `MP-6a`) must
  be in [docs/temp/open.md](docs/temp/open.md), which
  `tests/test_open_markers.py` checks. `# ! note` is a quick reminder without an ID,
  triaged into that list at the end of a session. When decided, an `OPEN` becomes
  `# DEVIATION <ID>` if it departs from the paper, else it is removed and the docstring
  names the ID. Nothing else is marked.
- New Python files: Black style, 88-character lines.
- **Blank lines inside functions.** Separate a function's logical steps with one blank
  line: before and after an `if`, `for`, `while`, `with`, `try` or `match` block that
  has statements around it, and before a final `return` that follows several
  statements. Not after the docstring, and not inside bodies of three statements or
  fewer. Black keeps these lines but does not add them.
- Never `git stash` in these worktrees.

## Keep the paper's grid functionality

The paper's graph grid model was built as a second grid method and removed on
11 Nov 2026 (reasons in the decision log, `docs/temp/decisions.md`; the last version
with it is the tag `v2-graph-model`): the power flow is the only grid the market
reads. Do not delete other
original-paper grid or market functionality, or anything it could use, only
because nothing calls it today (e.g. `electrical_distance`, the paths and zones of
`core/grid/powerflow.py`, the reputation helpers). The original's profile
generators (`core/market/profile/`) and its blockchain-style trade ledger
(`validation.py`, with the `ledger_difficulty` setting) were removed: the ledger
changes no market result. Both are in the original on the `main` branch
(`src/profile/`, `src/market/validation.py`). When unsure, keep it and ask.

## RL layer

- RLlib's own PPO with RLlib's own modules and distributions: no custom losses,
  distributions or training loops. PPO is the only algorithm.
  Only the environment and, for CTDE, what the actor reads differ between
  paradigms, each in its own module: `core/rl/ctce.py` (`CTCEEnv`),
  `core/rl/ctde.py` (`CTDEEnv`, `CTDEPPOModule`), both on the global state of
  `core/rl/state.py`. Same network settings for every paradigm.
- Objectives: DTDE and CTDE learn from each agent's own reward, with one module,
  one critic and one PPO ratio per agent; CTCE is one controller on the summed
  reward, with one joint ratio.
- An environment the trainer can use is a `MultiAgentEnv` built as
  `Env(env_config)`, with `agents_id`, a flat `Box` observation per agent, an
  action space per agent that RLlib's catalog gives a distribution for (`Box`,
  `Discrete`, and `Dict` / `Tuple` of them; the market's is a `Dict`), and
  `"__all__"` in `terminateds` and `truncateds`. Optional hooks, read by duck
  typing so `core/rl` imports no market module: `resolved_config()` (the config
  with what the environment computed, e.g. the market's scales; a run records and
  reuses it), `contract()` (what observations and actions mean, for `run.json`)
  and `baseline_policies(seed)`. `MarketEnv` and the test environments in
  `core/rl/envs/` provide this.
- The market action's semantics (side, quantity share and no-order threshold,
  price range, partner candidates) live in `core/env/market_env.py` only; the
  chosen partner goes to `OrderIntent.partner_id` unchanged. Do not change the
  clearing (`core/market/clearing.py`) to suit the RL layer.
- **Run the probes first after any change to `core/rl/` or its test environments**:
  `python core/rl/scripts/probe_ppo.py` (probes 1-10, PPO, all three paradigms;
  the same procedure as `notebooks/rl/probe_paradigms.ipynb`, which also runs on
  the cluster: `core/rl/scripts/probe_check.py`), then
  `tests/rl/`. The probes follow Andy Jones's guide
  (https://andyljones.com/posts/rl-debugging.html); each has an exact answer.
  Probe 6 has a mixed (categorical and continuous) action; probes 7-10 each
  isolate one feature of the market (a gated choice, mutual partner choice, a
  side-dependent part, the 24-step day).
- The original RL code with its `FAULT`, `DECIDE` and `DEVIATION` annotations is
  at commit `bbef313`, under `RL/core/rl/`.

## Running

- Start training experiments with `python -m core.runner`, not from a notebook
  cell, so they outlive the session.
- A seed repeats a run only with `PYTHONHASHSEED` fixed (the runner's jobs do
  this); build algorithms with `core.rl.config.build_algo`.
- RL notebooks put the repository root on `PYTHONPATH` before Ray starts, so
  worker processes can import `core.rl`.
- Several processes that each load torch (parallel runs, or environment runners
  set in a spec) can fail with "The paging file is too small" on this machine;
  Ray's start-up also fails sometimes under load (a run then shows `failed` or
  `lost`). Run fewer in parallel; `start` on the same experiment re-runs only
  those.
- The Studio keeps one state file per browser (`studio-state/storage-user-<id>.json`
  in the Studio's home) and a browser with no cookie gets a new one. A session that
  starts the Studio to drive it with a browser (a render check, a screenshot) sets
  `NICEGUI_STORAGE_PATH` to its scratchpad first, so the real folder keeps only the
  author's own browser; the variable must be set before the Studio starts.
