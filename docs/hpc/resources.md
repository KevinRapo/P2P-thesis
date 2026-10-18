# Resources and parallelism

There are two levels: **independent runs** side by side, and the **work inside one
run**. The experiment spec controls both: `max_parallel` limits independent runs,
and `num_env_runners` sets remote sampling processes inside each run. SLURM
resources are requested separately.

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
    A --> L["Local learner and its own Ray instance<br/>Sampling locally or on num_env_runners actors"]
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
| `num_env_runners` | 0 | Remote sampling processes per run; zero samples locally |

At the defaults three runs take 12 CPUs and 12 GB. On this PC `resources` is
ignored (no reservation, no time limit); `max_parallel`, `torch_threads` and
`num_env_runners` apply.
On the cluster the runner takes the first partition in `targets.toml` whose limit
allows `minutes`: `short` up to 240, then `common` up to 11,520; longer is refused.

## Inside one run

The runner passes `num_env_runners` to [`Run`](../../core/rl/train.py).
The default remains zero; GPU training is not exposed in the spec.
With [`build_config`](../../core/rl/config.py):

| Setting | Value | Meaning |
|---|---|---|
| `num_env_runners` | Spec value (default 0) | Zero: local sampling; positive: that many remote sampler actors |
| `num_envs_per_env_runner` | 1 | One market environment per sampler |
| `num_learners` | 0 | One learner, in the same process |
| `num_gpus` | 0 | CPU only |
| Ray `num_cpus` | `num_env_runners + 1` | Samplers plus the driver/learner; Ray bookkeeping, not a CPU pin |

At zero runners, one run is essentially one busy core (APPO adds learner threads). Raising
`resources.cpus` alone does not make it faster; 4 is an allowance for Ray's own
threads and processes. The five market participants are agents inside the one
environment, not processes; training days are what an episode draws from, not
parallel environments. `budget` counts environment steps (one market step for all
agents) and is checked after each training iteration, so a run can overshoot it
(APPO: 480 asked, 500 done). Evaluation stays in the job's driver process.

For example, these top-level experiment fields request three remote samplers per
run and four SLURM CPUs for the samplers and driver/learner:

```json
{
  "num_env_runners": 3,
  "max_parallel": 3,
  "resources": {"cpus": 4, "mem_gb": 4, "minutes": 120}
}
```

With three runs active, this gives nine training samplers and reserves twelve
SLURM CPUs. Each sampler has its own environment and inference model; allow for
their additional memory. Size `resources.cpus` for at least `num_env_runners + 1`
as a starting point; the runner does not automatically change the allocation.
`torch_threads` is set in the driver, not explicitly in remote sampler actors.
More samplers can improve sampling throughput but do not guarantee higher CPU
utilization or faster learning. The training-step budget is aggregated across
samplers, not repeated for each sampler. Use a new experiment name when changing
this setting for an existing experiment.

## Full and test profiles

For `market_3x3`:

| | Full | Test |
|---|---:|---:|
| Runs, at once | 9, 3 | 9, 3 |
| CPUs / memory per run | 4 / 4 GB | 4 / 4 GB |
| Minutes per run | 120 | 15 |
| Train / test days | 30 / 14 | 1 / 1 |
| Budget SAC / PPO / APPO | 24,000 / 240,000 / 240,000 | 1,100 / 2,400 / 480 |

The test profile keeps algorithms, paradigms, variants and settings (including
`num_env_runners`), and takes the
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
| Sampler processes | `num_env_runners` | Also `Run(num_env_runners=...)` in Python |
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

## Comparing sampling and learning time

`metrics.csv` records reports that advance sampled environment steps or lifetime
learner environment steps. Idle APPO polls are omitted; non-finite learner metrics
still stop the run and are recorded. `iteration` remains the number of calls to
`algo.train()`, so gaps in that column are expected and are not missing updates.

| Column | Meaning |
|---|---|
| `sampler_sample_s_mean` | RLlib's mean sample-call duration on the environment runners, aggregated across runners |
| `sampling_s_mean` | RLlib's driver sampling timer (PPO/SAC), including waiting for samples |
| `learner_call_s_mean` | RLlib's driver learner-call timer; for APPO this queues work, not the background update duration |
| `async_learner_update_s_mean` | APPO's background learner update timer |
| `learner_env_steps` | Lifetime environment steps processed by the learner; replay and reuse can count data repeatedly |
| `train_call_s` | Wall time of the reported `algo.train()` call |
| `train_calls_s_total` | Cumulative wall time of all training calls, including omitted idle polls |
| `sampled_steps_per_train_s` | Collected environment steps divided by cumulative training-call time; includes learning/communication, so this is not pure rollout throughput |
| `elapsed_s` | Wall time since the training loop began, including intermediate evaluation and reporting |

RLlib timers are smoothed means in seconds, not cumulative times. Missing timers
are blank in the CSV. Do not sum these columns to derive total runtime, or divide
the whole run's step count by a mean sample-call duration. Asynchronous sampling
and learning can overlap, and timer values may reflect earlier completed work.

`run.json` also records `timings`: `ray_init_s`, `build_s`, `train_calls_s`,
`evaluation_s` (including evaluation CSV writes) and `checkpoint_s`. These help
separate initialization from sustained training. They exclude the runner's later
held-out evaluation and do not constitute a complete breakdown of job wall time.
Compare longer runs on the same code and settings; a one-iteration test is mainly
a startup and pipeline check.
