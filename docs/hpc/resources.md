# Resources and parallelism

There are two levels: **independent runs** side by side, and the **work inside one
run**. The experiment spec controls the first and what each run asks of SLURM; it
does not (yet) parallelise inside a run.

## Runs side by side

An experiment expands to algorithms × paradigms × seeds × variants, each one an
independent run with its own model, seed, replay buffer, metrics and checkpoint.
[market_3x3.json](../../experiments/market_3x3.json) is 3 × 3 × 1 = 9 runs;
[sac_alpha.json](../../experiments/sac_alpha.json) 1 × 1 × 1 × 3 variants = 3.
Five seeds would make `market_3x3` 45 runs.

```mermaid
flowchart TD
    E["Experiment: nine runs"] --> S["max_parallel = 3"]
    S --> A["Run A: 4 CPUs, 4 GB"]
    S --> B["Run B: 4 CPUs, 4 GB"]
    S --> C["Run C: 4 CPUs, 4 GB"]
    S --> Q["The other runs wait"]
    A --> L["One process: sampler and learner,<br/>its own Ray instance"]
```

| Target | Who schedules | One run is |
|---|---|---|
| `local` | The worker (`launch.work`): at most `max_parallel` runs, started 10 s apart | A job process on this PC |
| `taltech` | SLURM: one array, at most `max_parallel` tasks at once | One array task, on a node SLURM picks |

Both call the same [`launch.job`](../../core/runner/launch.py). A slot refills as
soon as its run ends. `max_parallel` is per experiment, not across experiments.

## What a run gets

Defaults in [spec.py](../../core/runner/spec.py), the same for every run of an
experiment:

| Field | Default | Effect |
|---|---|---|
| `max_parallel` | 3 | Runs at once |
| `resources.cpus` | 4 | SLURM CPUs per run; creates no extra samplers |
| `resources.mem_gb` | 4 | Memory per run (not per CPU) |
| `resources.minutes` | 120 | Wall time per run, evaluation and saving included |
| `torch_threads` | 1 | `torch.set_num_threads` in each run |

At the defaults three runs take 12 CPUs and 12 GB. On this PC `resources` is
ignored (no reservation, no time limit); `max_parallel` and `torch_threads` apply.
On the cluster the runner takes the first partition in `targets.toml` whose limit
allows `minutes`: `short` up to 240, then `common` up to 11,520; longer is refused.

## Inside one run

The runner leaves the sampler and GPU settings of [`Run`](../../core/rl/train.py)
at their defaults, so with [`build_config`](../../core/rl/config.py):

| Setting | Value | Meaning |
|---|---|---|
| `num_env_runners` | 0 | Sampling in the run's own process, no sampler actors |
| `num_envs_per_env_runner` | 1 | One market environment |
| `num_learners` | 0 | One learner, in the same process |
| `num_gpus` | 0 | CPU only |
| Ray `num_cpus` | 1 | Ray's own bookkeeping, not a CPU pin |

So one run is essentially one busy core (APPO adds learner threads). Raising
`resources.cpus` alone does not make it faster; 4 is an allowance for Ray's own
threads and processes. The five market participants are agents inside the one
environment, not processes; training days are what an episode draws from, not
parallel environments. `budget` counts environment steps (one market step for all
agents) and is checked after each training iteration, so a run can overshoot it
(APPO: 480 asked, 500 done). Evaluation runs in the same job, after training.

## Full and test profiles

For `market_3x3`:

| | Full | Test |
|---|---:|---:|
| Runs, at once | 9, 3 | 9, 3 |
| CPUs / memory per run | 4 / 4 GB | 4 / 4 GB |
| Minutes per run | 120 | 15 |
| Train / test days | 30 / 14 | 1 / 1 |
| Budget SAC / PPO / APPO | 24,000 / 240,000 / 240,000 | 1,100 / 2,400 / 480 |

The test profile keeps algorithms, paradigms, variants and settings, and takes the
first seed, one evaluation episode and one held-out seed. Its budget per algorithm
is one training batch (`train_batch_size_per_learner`, else 100), or the warm-up
plus 100 steps where learning starts after a warm-up (SAC: the spec's 1,000, else
RLlib's 1,500), the largest over the variants, so every test run really updates
its networks. A `test` block in the spec overrides seeds, days, budget, evaluation
and resources.

## What the spec can set

| Choice | In the spec | Otherwise |
|---|---|---|
| Runs and how many at once | grid fields, `max_parallel` | |
| Cluster allocation per run | `resources` | |
| PyTorch threads | `torch_threads` | |
| Training and network settings | `training`, `model`, `variants` | |
| Sampler processes | no | `Run(num_env_runners=...)` in Python |
| GPU | no | `Run(num_gpus=...)` in Python, on a GPU node |

Unknown fields are refused. `num_env_runners` inside `training` does not work: that
block goes to RLlib's training settings.

## Shared Ray

[train.py](../../core/rl/train.py) joins an existing Ray instance when
`RAY_ADDRESS` is set, instead of starting its own. The probe notebook uses this to
run 38 runs in one Jupyter job; the runner does not, so its sizing is not the
notebook's ([sizing](performance.md#sizing)).

Before longer runs, measure a short one with `seff <jobid>` (CPU efficiency, peak
memory) and size from that: five agents say little about fifty.
