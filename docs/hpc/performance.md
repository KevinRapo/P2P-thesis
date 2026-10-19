# Measurements and costs

Observations from 13–16 October 2026 and the cost estimates built on them. The
runner's own settings are in [resources](resources.md).

## The cluster

| Nodes | Count | Per node | Partitions |
|---|---|---|---|
| green | 28 | 40 cores (80 threads, 78 for SLURM), 95 GB | `short`, `common`, `long` |
| blackwell1 | 1 | 256 cores (512 threads, AMD EPYC 9755), 1 TB | `short` |
| ada | 2 | 64 cores, 1.5 TB, 2 × L40 48 GB | `gpu`, `short` |
| amp, amp2 | 2 | 128 cores, 1–2 TB, 8 × A100 | `gpu`, `short` |

- Partitions: `short` up to 4 h, `common` 8 days, `long` 22 days, `gpu` 5 days.
  `short` can land on any node type; `-p common` is green only, `-w blackwell1`
  asks for that node. `sinfo` shows what is free.
- SLURM counts hyper-threads: `-c 78` is 39 physical cores.
- **4096 processes and threads per user per node** (`ulimit -u`). This limits
  parallel training before cores or memory do
  ([how many runs fit](resources.md#how-many-runs-fit-at-once)).
- No per-user cap on jobs, CPUs or submits (`normal` QOS, checked 19 Oct).
- Compute nodes have internet; install on `base` anyway.
- Prices used below: 0.008 EUR per CPU-hour, 0.62 EUR per GPU-hour. TalTech's
  [billing table](https://docs.hpc.taltech.ee/billing.html) bills per CPU *core*
  hour and adds a memory rate above 6 GB per core, so check how a job of
  hyper-threads is billed before trusting the euro figures.

## Parallel training

The probe notebook ([probe_paradigms.ipynb](../../notebooks/rl/probe_paradigms.ipynb)),
`"thorough"` preset, 45 runs (3 algorithms × 3 paradigms × 5 probes):

| Where | Runs at once | Ray | Total |
|---|---|---|---|
| This PC, 13 Oct | 3 | one per run | about 91 min; 4 of 45 failed (Ray start-up, memory) |
| green28, 16 Oct | 16 | one per run | 27 min, capped by the thread limit |
| green node | 38 | one shared | not measured yet; about 20 min expected (the slowest run) |

- A run is one process on one core (about 95 % CPU) and about 0.75 GB. A green core
  is as fast as this PC's (SAC DTDE about 1100–1200 s).
- Ray sizes its thread pools by the machine's cores: about 1000 threads per
  instance on blackwell1, about 175 with every pool at one thread. 38 instances
  broke the 4096 limit (`Resource temporarily unavailable`, `Failed to connect to
  GCS`).
- Fix ([74a59b2](https://github.com/KevinRapo/P2P-thesis/commit/74a59b2)): the
  notebook starts one Ray instance and sets `RAY_ADDRESS`, and
  [train.py](../../core/rl/train.py) joins it. Each run still samples and learns in
  its own process (started with `spawn`). Workers: one per physical core less one,
  at most (4096 − 1000) / 80.
- Ray's `Failed to establish connection to the ... metrics exporter agent` lines
  are harmless.

## Cost of the market experiment at 50 agents

Estimates until a 50-agent run is timed on the cluster
([what to measure first](#what-to-measure-first)).

### Where time goes

| Level | Side by side | Gain |
|---|---|---|
| Between runs | algorithms × paradigms × seeds × variants | One run per core; a 3 × 3 grid with 5 seeds (45 runs) is about one green node |
| Sampling inside a run | `num_env_runners = k` copies of the market | Helps where the market dominates (CTCE) |
| Learning inside a run | more threads or a GPU | Little for these small networks |

Per 1000 environment steps (one market hour for all agents):

| Part | Seconds | Source |
|---|---|---|
| Market + power flow | about 42 | [market_step.csv](../../notebooks/market/results/market_step.csv): 41 ms at 53 agents (urban6), 40 ms at 39 |
| RL, PPO CTCE | about 5.5 | [benchmark_speed.ipynb](../../notebooks/rl/benchmark_speed.ipynb), "paper" preset, between 39 and 118 agents |
| RL, PPO CTDE | about 40 | same (27 at 39 agents, 124 at 118) |
| RL, PPO DTDE | about 100 | same (76 at 39 agents, 248 at 118) |

The RL benchmark ([shapes.py](../../core/rl/envs/shapes.py)) uses the original
MARLEM market's sizes, 42 observations and 4 actions per agent; `MarketEnv` has 16
and 2, so these learner times are on the high side. The learner dominates in CTDE
and DTDE (one network per agent); CTCE has one network.

### Per run

PPO, 240,000 steps as in [market_3x3.json](../../experiments/market_3x3.json). The
earlier 5-agent market runs on this PC took about twice the sum of the benchmarks
(evaluation, runs sharing a 6-core PC), so the table uses a factor 1.5. The euro
column assumes 2 CPUs per run; the runner's default is 4, which doubles it.

| Paradigm | s per 1000 steps | Hours per run | CPU-hours (2 CPUs) | EUR per run |
|---|---|---|---|---|
| CTCE | 48 × 1.5 = 72 | 4.8 | 9.6 | 0.08 |
| CTDE | 82 × 1.5 = 123 | 8.2 | 16.4 | 0.13 |
| DTDE | 142 × 1.5 = 213 | 14.2 | 28.4 | 0.23 |

$$
\text{EUR per run} = \frac{\text{steps}}{1000} \times \frac{\text{s per 1000 steps}}{3600} \times \text{CPUs} \times 0.008
$$

| Grid | Runs | CPU-hours | EUR | Wall clock, all at once |
|---|---|---|---|---|
| PPO, 3 paradigms, 1 seed | 3 | 54 | 0.45 | about 14 h (DTDE) |
| PPO + APPO, 3 paradigms, 5 seeds | 30 | 545 | 4.4 | about 14 h on one node |
| + SAC | 45 | ? | ? | ? |

APPO is assumed to cost what PPO does (not benchmarked). Add about 20 % for idle
booked CPUs at start-up and in the tail.

### What follows

- **Money is not the limit; wall clock is.** A DTDE run at 50 agents takes about
  half a day: `-p common`, not `short`.
- **Long runs need intermediate checkpoints.** [train.py](../../core/rl/train.py)
  saves only at the end, so a run killed by its time limit loses everything.
- **Parallel sampling helps CTCE, not DTDE.** CTCE spends about 88 % of a step in
  the market: 4 samplers make it about 3 × faster for 1.7 × the CPU-hours. DTDE
  spends about 70 % learning: at most 1.4 × faster for nearly 4 × the CPU-hours.
- **No GPU at 50 agents.** The GPU was slower than the CPU up to 39 agents and
  clearly faster only for CTDE at 118.
- **SAC is the unknown.** Its 5-agent market runs took 150–400 ms per step. If its
  learner grows with the agents like PPO's, SAC DTDE at 50 agents is about 4 s per
  step: about a day for 24,000 steps, about 0.4 EUR.

### What to measure first

1. A 50-agent scenario on a green node: the market step
   ([benchmark_market_step.ipynb](../../notebooks/market/benchmark_market_step.ipynb))
   and the RL benchmark for PPO, APPO and SAC at N = 50
   ([benchmark_speed.ipynb](../../notebooks/rl/benchmark_speed.ipynb)).
2. One short real run per paradigm (e.g. 10,000 steps) through `core.runner`, to
   replace the factor 1.5.
3. Then refill the tables above.

## Sizing

For the probe notebook in one Jupyter job with shared Ray (the runner's arrays
are sized in [resources](resources.md)):

- CPUs = 2 × (runs at once + 1); memory about 1–1.5 GB × runs at once.
- 38 runs: `-c 78 --mem=60G`. One probe's 9 runs: `-c 20 --mem=16G`.
- Time limit: the slowest run plus a margin; a whole probe set takes about 20–30 min.
- After a job, `seff <jobid>` shows the real CPU efficiency and peak memory.
