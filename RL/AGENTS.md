# AGENTS.md: implementation guide for MARLEM RL

The `RL/` folder on branch `clean` (copied from the former `RL` worktree):
validate the RL part of MARLEM separately from the market, then bring it back
to the market once it is understood.

## Layers

```
core/        everything a notebook can call
  rl/        the original RL code: modules, trainer, inference
  fixed/     the RL layer rebuilt on RLlib's own algorithms and modules, issues fixed
  envs/      test environments for both
notebooks/   call core/ only
  original/  notebooks that test core/rl/
  fixed/     notebooks that test core/fixed/
```

Same layering as marlem-clean: `core/` imports nothing from `notebooks/`; there is
no Studio here.

## The original code (`core/rl/`)

| File | What it is | State |
|---|---|---|
| `base.py` | `RLAlgorithm` (PPO, APPO, SAC), `TrainingMode` (CTCE, CTDE, DTDE), `RLProtection` | original, unchanged |
| `ctce.py` | `CTCEModule`: one central actor and critic for all agents | original, unchanged |
| `ctde.py` | `CTDEModule`: central actor and critic for training, one head per agent for acting | original, unchanged |
| `train.py` | `RLTrainer` (Ray Tune with population-based training), `GroupedEnv` | original, isolated |
| `inference.py` | `RLInference`: roll out a trained checkpoint | original, isolated |
| `local.py` | `build_local`, `train`, `train_local`: the trainer's configuration in one process, with the learner's health metrics (PPO, APPO and SAC) | new |
| `probe.py` | `run_probe`, `evaluate`, `query`: train on a probe, then read the learner's value and action outputs in the probe's states | new |

- Copied from `src/environment/` of the original repository (`main`, 15d6715) in
  the first commit, unchanged, so `git diff` against it shows every change.
- Every change to original code carries a `DEVIATION:` comment saying what the
  original did. Keep the original formatting in these files (no black), so the
  diff stays readable.
- Every known issue is marked above the lines at fault, with the ID from
  [validation/rl.md](../docs/validation/rl.md), which explains it:
  `FAULT <ID>:` for a defect, `DECIDE <ID>:` for a question that needs a
  decision (evidence *Judgment*). These are Todo Tree tags, highlighted like
  `DEVIATION:`. Comments only: the code is not changed. When an issue is fixed,
  its `FAULT` comment becomes a `DEVIATION:` one. Not marked: I-52 (the
  original's `tests/test_trainer.py` is not copied here).
- Isolation: the trainer and inference take the environment class
  (`env_class`) instead of importing `LocalEnergyMarket`; `GroupedLEM` became
  `GroupedEnv`, built for any class with `grouped(env_class)`.

## The fixed implementation (`core/fixed/`)

The three paradigms on RLlib's own PPO, APPO and SAC, with RLlib's own modules;
kept apart from `core/rl/` so the two stay comparable. Each file's docstring
names the issues it fixes.

| File | What it is |
|---|---|
| `grouping.py` | `GroupedEnv`: all agents as one (CTCE, CTDE), joint `Box` spaces in agent order, summed reward |
| `ctde_modules.py` | CTDE: RLlib's default modules with the actor split into one network per agent |
| `config.py` | `build_config`: one algorithm and paradigm; `SETTINGS` (the original's hyperparameters, less the defective ones) |
| `policy.py` | `Policy` (acts as training does), baselines, `rollout`, `evaluate` on held-out seeds |
| `train.py` | `train(Run(...))`: budget in environment steps, NaN stop, `run.json`, metrics, evaluation, checkpoint; `load_policy` |
| `benchmark.py` | `benchmark(Bench(...))`: time one algorithm and paradigm at one problem size (build, warm-up, timed iterations, sampling alone), with every setting that decides the cost in the record |

- No custom losses, distributions or training loops: only the environment
  (grouping) and, for CTDE, the actor network differ between paradigms.
- Same network settings for every paradigm (RLlib's defaults).
- Runs write to `runs/` (not in git).

## Environments (`core/envs/`)

- `probes.py`: probe environments after Andy Jones's guide
  (https://andyljones.com/posts/rl-debugging.html), multi-agent and continuous;
  each adds one piece of the learning problem and has an exact answer. They
  validate the training paradigms; run them first after any change to
  `core/rl/` or `core/fixed/` (`probe_paradigms.ipynb` in `notebooks/original/`
  and `notebooks/fixed/`).
- `spread.py`: Farama MPE2 `simple_spread` (3 agents cover 3 landmarks, cooperative,
  continuous actions `Box(0, 1, (5,))`: no-op, left, right, down, up), the second
  test after the probes, as a 3 x 3 matrix of paradigms and algorithms
  (`simple_spread.ipynb` in `notebooks/original/` and `notebooks/fixed/`). Needs
  `pip install mpe2` (PettingZoo, pygame-ce); `baseline_return` gives the random
  and zero-action returns to read curves against.
- `toy.py`: two small tasks with a known best return (individual and team
  reward), for comparing how fast the paradigms learn
  (`notebooks/original/validate_rl.ipynb`).
- `shapes.py`: `MarketShapedEnv`, N agents with the market's sizes (42
  observations, 4 actions, 24-step days), random observations and a cheap
  learnable reward: times the RL layer at market size without the market
  (`notebooks/fixed/benchmark_speed.ipynb`, results in `runs/benchmark/`). The
  market's own time per step comes from `marlem-clean`'s
  `notebooks/benchmark_market_step.ipynb`.

An environment the trainer can use: a `MultiAgentEnv` built as
`Env(env_config)`, with `agents_id`, `observation_spaces` and `action_spaces`
(one `Box` per agent), and `"__all__"` in `terminateds` and `truncateds`. This
is what the market environment provides too.

## Running

- Notebooks set `PYTHONPATH` to the clean repository root before Ray starts, so
  workers can import `RL.core`. Paths in this guide are relative to `RL/`.
- Import RL code as `RL.core.*`; the market owns the separate `core.*` package.
  Neither layer imports the other. Notebook `ROOT` and saved runs stay in `RL/`.
- `RLTrainer.train` starts several worker processes that each load torch; on
  this machine they can fail with "The paging file is too small" when memory is
  short. `train_local` runs the same configuration in one process.
- New Python files: Black style, 88-character lines.
- Never `git stash` in these worktrees.
