# AGENTS.md: implementation guide for MARLEM v1

MARLEM rebuilt step by step on SimBench networks: configure a local energy market,
then step through it by hand and watch the network's power flow. Reinforcement
learning lives in `core/rl/`, independent of the market layer; `core/runner/`
is where the two meet: it starts and watches training experiments.

## Code structure

### Three layers

```
core/        the MARLEM functionality: everything a notebook can call
  settings.py             this machine's settings (.env)
  grid/ config/ market/   the network, the scenario, the market
  env/                    MarketEnv: the market as an RL environment
  rl/                     the RL layer, with envs/ (test environments)
  runner/                 experiments: start, watch and stop training runs
experiments/ experiment specs (JSON): which runs to train
scenarios/   saved scenario files (JSON)
notebooks/   calls core/ only: validates it without the Studio (market/, rl/)
tests/       market/, rl/ and runner/ checks
studio/      the NiceGUI Studio: pages and components on top of adapters/
```

When something looks wrong in the Studio, reproduce it in a notebook first. If
the notebook shows it, the problem is in `core/`; if not, it is in `studio/`.

### Top-level folders

| Folder | Holds |
|---|---|
| `core/` | The core API: the market and its network, callable without any UI |
| `core/config/` | The scenario (`Scenario`), placing participants on its network, saving and loading it |
| `core/grid/` | The SimBench network: catalogue, topology, profiles, power flow. The only place that imports pandapower or simbench |
| `core/market/` | The MARLEM market: orders, matching, pricing, DSO, agents, profiles, and `LocalEnergyMarket` (`lem.py`), the one class that runs a market step and its power flow |
| `core/env/` | `MarketEnv`: the market as an RLlib multi-agent environment |
| `core/rl/` | The RL layer: the three paradigms on RLlib's algorithms (grouping, CTDE modules, configuration, policy, training, benchmark); `core/rl/envs/` holds the test environments (probes, toy, spread, shapes) |
| `core/runner/` | Experiments: `spec.py` (the JSON spec, its grid of runs, resources, the test profile), `launch.py` (a detached worker and its job processes, `stop`), `slurm.py` (a SLURM job array per experiment, submitit; on the cluster), `targets.py` (where an experiment runs: `local` or a cluster, `hpc/targets.toml`), `remote.py` (the cluster over SSH from this PC, asyncssh), `registry.py` (read-only view of `runs/`), `results.py` (the saved results of runs, to compare), `__main__.py` (`python -m core.runner start / status / stop / sync / check [--target]`). The one place that imports both `core.env` and `core.rl` |
| `experiments/` | Experiment specs (JSON, tracked): algorithms x paradigms x seeds x variants, budgets, train and test days |
| `scenarios/` | Saved scenarios (JSON, the Studio's format): the market notebook, the tests and the Studio's Open dialog read them |
| `notebooks/` | Jupyter notebooks that call `core/` directly: `market/` validates the market, `rl/` validates the RL layer |
| `tests/` | `market/` (market environment, power flow, Studio against core), `rl/` (probe environments, CTDE structure) and `runner/` (experiment specs, run states) |
| `runs/` | Training runs, checkpoints and benchmark results (git-ignored); `runs/<experiment>/` is where the runner keeps its files, the one source of truth for CLI and Studio |
| `studio/` | The NiceGUI Studio: `pages/` (inspect, grid, market, summary, step, runs, results, settings), `components/`, `adapters/`, layout, theme |
| `studio/adapters/` | What the pages call: a thin layer over `core/` (caching, background threads, the current scenario, the market being played, the experiments in `runs/`, workspace paths) |
| `docs/` | The documentation, Markdown (see `docs/about.md`) |
| `docs_site/` | The MkDocs site built from `docs/`: config, build hooks, diagram assets |
| `core/settings.py` | This machine's settings (cluster account, SSH host, ports, folders): the environment variable, else `.env` (git-ignored; keys in `.env.example`), else a default. Never hard-code such a value: add a key |
| `scripts/` | The Jupyter job on the cluster: `hpc.ps1` (and its `hpc.cmd` launcher), which reads `.env`, and `jupyter.slurm`; the setup and PATH instructions are in `docs/hpc/setup.md` |
| `hpc/` | `targets.toml`: local and Slurm targets, with `${KEY}` settings from `.env`; the active remote checkout is `~/marlem-v1` |

### Layer rules

- **`core/`** imports nothing from `studio/` or `notebooks/`. Its API is
  `core/grid/contract.py` for the grid, `LocalEnergyMarket` (`core/market/lem.py`)
  for the market, and `Scenario` (`core/config/`) with its rules, e.g. placing
  participants (`core/config/placement.py`). `core/config/` may import
  `core/grid/`, never the reverse. Every rule of the market or the network lives
  here, so a notebook can check it.
- **`notebooks/`** import `core/` only, never `studio/`. They find the repository
  root from wherever they run and write runs to `<root>/runs/`.
- **`studio/adapters/`** is the Studio's thin layer over the core: caching,
  background threads, the current scenario, the market being played between
  clicks, workspace paths. No domain rules, no records that copy the core's:
  return the core's records as they are. `studio/adapters/models.py` holds only
  what the Studio alone needs (profile classes and types, chart series). Test for
  any logic here: if a notebook would want it too, it belongs in `core/`.
- **`studio/pages/` and `studio/components/`** call `studio/adapters/`. They may
  import the core's plain data records (`StepRecord`, `Trade`, `NetworkRef`,
  `BatterySetup`, `DSO_ID`, the `DESCRIPTIONS` captions) to read and display them,
  but never construct or drive a core engine class. Inside the Studio,
  `MarketService` builds and holds the `LocalEnergyMarket` between clicks; a
  notebook uses `LocalEnergyMarket` directly. A page may name `LocalEnergyMarket`
  as a type (under `TYPE_CHECKING`) to annotate what it reads.

Every folder and script, with how far it is built, is in
`docs/structure.md`: update it whenever a file is added, moved, renamed or built.

### Studio: pages and components

- **A page** is one file in `studio/pages/`. Code that only one page uses stays in
  that page's file.
- **A component** goes in `studio/components/` only when it is actually used in
  more than one place. Being in `components/` means "reused", not "could be
  reused someday".
- When a second place needs code that lives in a page, move it to `components/`
  at that moment, not before.

### Sections inside a file

- A file that does more than one thing is split into **sections** with a banner,
  so each part of its functionality is easy to find:

  ```python
  # --------------------------------------------------------------------------------------
  # Catalog: which networks exist and their names
  # --------------------------------------------------------------------------------------
  ```

  The title says what the section is for. Inside a large class, a one-line
  marker groups its methods: `    # --- Network cache ----------…`.
- A file with one purpose (one class, a few lines) needs no sections.
- When adding code, put it in the section it belongs to; when a section grows its
  own purpose, give it its own banner.

## Layers inside `core/`

- `core/grid`, `core/config`, `core/market` import nothing from `core/env`,
  `core/rl` or `core/runner`.
- `core/rl` imports no market module: the environment arrives as a class, so the
  probes still test it alone.
- `core/env` imports the market, never `core/rl`.
- `core/runner` is the one place that knows both `core/env` and `core/rl`; it
  imports them only inside a job, so reading status stays fast. Neither imports
  the runner.
- `core/settings.py` imports nothing from the project (standard library only), so
  any layer, the Studio and the notebooks may use it.

## Planned: the paper's grid model as a second grid method

Once the implementation is finished, validated and its final functionality
decided, the market gets a choice of grid method: the current one (the SimBench
network with an AC power flow, `core/grid/`) or MARLEM's original graph model
([P1] §3.5, [methodology §6](docs/marlem/methodology.md): shortest-path electrical
distance $d_{ij}$, zones, linear losses, congestion from edge flows; the original's
`src/grid/network.py`), built on the same SimBench network. The two can then be
compared on one setup. This comes after the current clean-up and the RL work, not
now.

Until then, be conservative: do not delete original-paper grid or market
functionality, or anything the second grid method could use, only because nothing
calls it today (e.g. `electrical_distance`, the paths and zones of
`core/grid/powerflow.py`, the ledger, the reputation helpers,
`core/market/profile/`). When unsure, keep it and ask.

## RL layer (`core/rl/`)

The three paradigms on RLlib's own PPO, APPO and SAC, with RLlib's own modules.
Each file's docstring names the issues it fixes (IDs in
[validation/rl.md](docs/validation/rl.md)). The original code and its
annotations (`FAULT`, `DECIDE`, `DEVIATION` comments) live on the `clean`
branch, under `RL/core/rl/`.

| File | What it is |
|---|---|
| `grouping.py` | `GroupedEnv` (CTCE): all agents as one, joint `Box` spaces in agent order, summed reward. `CentralStateEnv` (CTDE): each agent observes `[o_i, o_1..o_N]`, own reward |
| `ctde_modules.py` | CTDE: one RLlib default module per agent; the actor reads only the agent's own observation, the critic all of it (MAPPO / MASAC with per-agent critics) |
| `config.py` | `build_config`: one algorithm and paradigm; `SETTINGS` (the original's hyperparameters, less the defective ones) |
| `policy.py` | `Policy` (acts as training does), baselines, `rollout`, `evaluate` on held-out seeds |
| `train.py` | `train(Run(...))`: budget in environment steps, NaN stop, `run.json`, metrics, evaluation, checkpoint; `load_policy` |
| `benchmark.py` | `benchmark(Bench(...))`: time one algorithm and paradigm at one problem size (build, warm-up, timed iterations, sampling alone), with every setting that decides the cost in the record |

- No custom losses, distributions or training loops: only the environment
  (grouping, central state) and, for CTDE, what the actor reads differ between
  paradigms.
- Objectives: DTDE and CTDE learn from each agent's own reward (per-agent
  critics, advantages and PPO clip); CTCE is one controller on the summed
  reward (social planner).
- Same network settings for every paradigm (RLlib's defaults).
- Runs write to `runs/` (not in git).

### Environments (`core/rl/envs/`)

- `probes.py`: probe environments after Andy Jones's guide
  (https://andyljones.com/posts/rl-debugging.html), multi-agent and continuous;
  each adds one piece of the learning problem and has an exact answer. They
  validate the training paradigms; run them first after any change to
  `core/rl/`, `spread.py`, `toy.py` or `shapes.py` (`notebooks/rl/probe_paradigms.ipynb`
  and `tests/rl/`).
- `spread.py`: Farama MPE2 `simple_spread` (3 agents cover 3 landmarks, cooperative,
  continuous actions `Box(0, 1, (5,))`: no-op, left, right, down, up), the second
  test after the probes, as a 3 x 3 matrix of paradigms and algorithms
  (`notebooks/rl/simple_spread.ipynb`). Needs `pip install mpe2` (PettingZoo,
  pygame-ce); `baseline_return` gives the random and zero-action returns to read
  curves against.
- `toy.py`: two small tasks with a known best return (individual and team
  reward), for comparing how fast the paradigms learn.
- `shapes.py`: `MarketShapedEnv`, N agents with the original MARLEM market's
  sizes (42 observations, 4 actions, 24-step days; `MarketEnv` has 16 and 2),
  random observations and a cheap learnable reward: times the RL layer at market
  size without the market
  (`notebooks/rl/benchmark_speed.ipynb`, results in `runs/benchmark/`). The
  market's own time per step comes from
  `notebooks/market/benchmark_market_step.ipynb`.

An environment the trainer can use: a `MultiAgentEnv` built as
`Env(env_config)`, with `agents_id`, `observation_spaces` and `action_spaces`
(one `Box` per agent), and `"__all__"` in `terminateds` and `truncateds`. This
is what the market environment (`core/env/`) provides too.

### Running

- RL notebooks put the repository root on `PYTHONPATH` before Ray starts, so
  worker processes can import `core.rl`.
- A seed repeats a run only in a process started with `PYTHONHASHSEED` fixed
  (RLlib keeps agent ids in sets); the runner's jobs do this
  (`launch.job_environment`). Build algorithms with `core.rl.config.build_algo`,
  not `config.build_algo()`, so the replay buffer follows the seed too.
- Several worker processes that each load torch (parallel runs, or
  `num_env_runners > 0`) can fail with "The paging file is too small" on this
  machine when memory is short; the default runs everything in the driver.
- Training experiments are started with `python -m core.runner` (see
  `docs/v1.md` section 4), not from a notebook cell, so they outlive the session.
  Ray's start-up sometimes fails on this machine under load (a run then shows
  `failed` or `lost`); `start` on the same experiment re-runs only those.
- New Python files: Black style, 88-character lines.
- Never `git stash` in these worktrees.
