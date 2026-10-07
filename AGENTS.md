# AGENTS.md: implementation guide for MARLEM RL

Branch `RL` (worktree `marlem-rl`, no shared history with the other branches):
validate the RL part of MARLEM separately from the market, then bring it back
to the market once it is understood.

## Layers

```
core/        everything a notebook can call
  rl/        the original RL code: modules, trainer, inference
  envs/      test environments for it
notebooks/   call core/ only
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
| `local.py` | `build_local`, `train`, `train_local`: the trainer's configuration in one process, with the learner's health metrics | new |
| `probe.py` | `run_probe`, `evaluate`, `query`: train on a probe, then read the learner's value and action outputs in the probe's states | new |

- Copied from `src/environment/` of the original repository (`main`, 15d6715) in
  the first commit, unchanged, so `git diff` against it shows every change.
- Every change to original code carries a `DEVIATION:` comment saying what the
  original did. Keep the original formatting in these files (no black), so the
  diff stays readable.
- Isolation: the trainer and inference take the environment class
  (`env_class`) instead of importing `LocalEnergyMarket`; `GroupedLEM` became
  `GroupedEnv`, built for any class with `grouped(env_class)`.

## Environments (`core/envs/`)

- `probes.py`: probe environments after Andy Jones's guide
  (https://andyljones.com/posts/rl-debugging.html), multi-agent and continuous;
  each adds one piece of the learning problem and has an exact answer. They
  validate the training paradigms; run them first after any change to
  `core/rl/` (`notebooks/probe_paradigms.ipynb`).
- `toy.py`: two small tasks with a known best return (individual and team
  reward), for comparing how fast the paradigms learn
  (`notebooks/validate_rl.ipynb`).

An environment the trainer can use: a `MultiAgentEnv` built as
`Env(env_config)`, with `agents_id`, `observation_spaces` and `action_spaces`
(one `Box` per agent), and `"__all__"` in `terminateds` and `truncateds`. This
is what the market environment provides too.

## Running

- Notebooks set `PYTHONPATH` to the repository root before Ray starts, so Ray's
  worker processes can import `core/`.
- `RLTrainer.train` starts several worker processes that each load torch; on
  this machine they can fail with "The paging file is too small" when memory is
  short. `train_local` runs the same configuration in one process.
- New Python files: Black style, 88-character lines.
- Never `git stash` in these worktrees.
