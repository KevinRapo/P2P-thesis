# Measurements and cost estimates

[HPC overview](../hpc.md) · [Resources](resources.md) · [Experiments](experiments.md)

These are dated observations from 13–16 October 2026 and planning estimates,
not fresh measurements of the migrated runner. The shared-Ray notebook and the
per-run-Ray job array have different resource costs. Use
[the current resource model](resources.md) when configuring an experiment.

## Hardware and limits

The inventory below records the original setup notes. Check `sinfo` for current
availability and [TalTech's partition documentation](https://docs.hpc.taltech.ee/index.html#slurm-partitions)
for policy; the runner uses the explicit limits in `hpc/targets.toml`.

| Nodes | Count | Per node | Partitions |
|---|---|---|---|
| green | 28 | 40 cores (80 threads, 78 usable by SLURM), 95 GB | `short`, `common`, `long` |
| blackwell1 | 1 | 256 cores (512 threads, AMD EPYC 9755), 1 TB | `short` (seen there) |
| ada | 2 | 64 cores, 1.5 TB, 2 x L40 48 GB | `gpu`, `short` |
| amp, amp2 | 2 | 128 cores, 1-2 TB, 8 x A100 | `gpu`, `short` |

- Partitions: `short` up to 4 h, `common` up to 8 days, `long` up to 22 days,
  `gpu` up to 5 days. `short` can land on any node type; `-w blackwell1` asks for
  that node, `-p common` for green only.
- SLURM counts hyper-threads: `-c 78` is 39 physical cores.
- Thread limit: 4096 processes and threads per user per node (`ulimit -u`). This
  limits parallel training before cores or memory do (see below).
- Compute nodes have internet (pip, git work in jobs). Install on `base` anyway.
- The original estimates below use 0.008 EUR per booked CPU-hour and 0.62 EUR
  per GPU-hour. TalTech's [billing table](https://docs.hpc.taltech.ee/billing.html)
  instead labels the CPU unit **CPUcore-hour** and has a separate memory-based
  rate above 6 GB per core. Do not treat a Slurm hardware thread as a billed
  physical core without checking the allocation's billing calculation. See
  [resource monitoring](https://docs.hpc.taltech.ee/quickstart.html).


## Parallel training (what was learned)

Probe notebook ([probe_paradigms.ipynb](../../notebooks/rl/probe_paradigms.ipynb)),
`"thorough"` preset, 45 runs (3 algorithms x 3 paradigms x 5 probes):

| Where | Workers | Ray | Total | Notes |
|---|---|---|---|---|
| This PC, 2026-10-13 | 3 | one per run | about 91 min | 4 of 45 failed (Ray start-up, memory) |
| green28, 2026-10-16 | 16 | one per run | 1596 s (27 min) | capped by the thread limit |
| green node, 38 workers | 38 | one shared | (to measure) | expected about 20 min: the slowest run |

- One run is one process on one core (about 95 % CPU), about 0.75 GB RAM.
  Per-run times on a green core match this PC (SAC DTDE about 1100-1200 s).
- Every run used to start its own Ray instance. Ray sizes its thread pools by the
  machine's core count: about 1000 threads per instance on blackwell1, about 175
  with every pool set to one thread. With 38 runs that broke the 4096 limit
  (`Resource temporarily unavailable`, GCS crashes, `Failed to connect to GCS`).
- Fix (commit [74a59b2](https://github.com/KevinRapo/P2P-thesis/commit/74a59b2)):
  the notebook's train cell starts one Ray instance and sets `RAY_ADDRESS`;
  [train.py](../../core/rl/train.py) then joins it instead of starting its own.
  Each run still samples and learns in its own process. The run
  processes are started with `spawn`.
- Workers in the train cell: one per physical core less one (`-c 78`: 38), capped
  at (thread limit - 1000) / 80.
- `Failed to establish connection to the ... metrics exporter agent` lines from
  Ray are harmless.
- Not yet tested: GPU (`num_gpus=1`); expected little gain for 2 x 256 networks.
  Parallel sampling inside a run (`num_env_runners`) matters for the market
  environment, not the probes.


## Cost estimate: the market experiment at 50 agents

Planning numbers for the thesis's market experiments, built from what has been
measured on this PC. Every number below is an estimate until a 50-agent run has
been timed on the cluster (see [What to measure first](performance.md#what-to-measure-first)).

### What can run in parallel

These are three conceptual ways to scale work. The current experiment runner
exposes independent runs and PyTorch threads; parallel samplers and GPUs require
lower-level Python configuration. APPO also has internal asynchronous learning,
so the sampling/learning overlap depends on the algorithm.

| Level | What runs side by side | Speed-up | Cost |
|---|---|---|---|
| 1. Between runs | algorithms x paradigms x seeds x variants: independent runs | number of runs at once (one core each) | ideally similar work; startup and contention can change the cost |
| 2. Inside a run: sampling | `num_env_runners = k`: k copies of the market simulate days at once | potentially accelerates sampling; scaling is workload-dependent | additional sampler resources; overlap depends on the algorithm |
| 3. Inside a run: learning | the learner on more threads or a GPU | small networks gain little; measured GPU gains only for CTDE at 118 agents | GPU-hours cost 78 x a CPU-hour |

Level 1 is where the cluster pays off: a 3 x 3 grid with 5 seeds is 45
independent runs, about one green node's worth (38 at once, shared Ray).

### Cost of one environment step at 50 agents

One environment step is one market hour for all agents. Per 1000 steps:

| Part | Seconds per 1000 steps | Source |
|---|---|---|
| Market + power flow | about 42 | [market_step.csv](../../notebooks/market/results/market_step.csv): 41 ms at 53 agents (urban6), 40 ms at 39 |
| RL, PPO CTCE | about 5.5 | [benchmark_speed.ipynb](../../notebooks/rl/benchmark_speed.ipynb), "paper" preset, between 39 and 118 agents |
| RL, PPO CTDE | about 40 | same (27 at 39 agents, 124 at 118) |
| RL, PPO DTDE | about 100 | same (76 at 39 agents, 248 at 118) |

The RL cost is the learner: CTDE and DTDE have one network per agent, so it grows
with the number of agents; CTCE has one network. The market's cost grows slowly.

### Per run (PPO, 240 000 steps as in market_3x3.json)

The table preserves the original two-Slurm-CPU-per-run planning assumption.
The current array default is **four** CPUs per run, and the billing unit needs
verification as explained above. These euro totals are not current job quotes.
At unchanged timing, doubling a booked resource quantity doubles its resource-hours.

The budget is that of [market_3x3.json](../../experiments/market_3x3.json). The
earlier market runs on this PC (`runs/market_learn`, 5 agents) took about twice the
sum of the benchmarks (evaluation episodes, runs sharing a 6-core PC), so the table
uses a factor 1.5.

| Paradigm | s per 1000 steps | Hours per run | CPU-hours (2 SLURM CPUs per run) | EUR per run |
|---|---|---|---|---|
| CTCE | 48 x 1.5 = 72 | 4.8 | 9.6 | 0.08 |
| CTDE | 82 x 1.5 = 123 | 8.2 | 16.4 | 0.13 |
| DTDE | 142 x 1.5 = 213 | 14.2 | 28.4 | 0.23 |

$$
\text{EUR per run} = \frac{\text{steps}}{1000} \times \frac{\text{s per 1000 steps}}{3600} \times \text{CPUs} \times 0.008
$$

### The whole grid

| Grid | Runs | CPU-hours | EUR | Wall clock, all at once |
|---|---|---|---|---|
| PPO, 3 paradigms, 1 seed | 3 | 54 | 0.45 | about 14 h (DTDE) |
| PPO + APPO, 3 paradigms, 5 seeds | 30 | 545 | 4.4 | about 14 h on one node |
| + SAC (unmeasured, see below) | 45 | ? | ? | ? |

APPO is assumed to cost about what PPO does (not benchmarked). Add about 20 % for
idle booked CPUs (start-up, the tail while the last runs finish).

### What the numbers say

- **The original estimate suggested modest cost.** Recalculate against the
  actual allocation, memory request and account billing units before deciding
  whether a grid fits the account allowance.
- **Wall clock is.** A DTDE run at 50 agents takes about half a day. That needs
  `-p common` (8 days), not `short` (4 h).
- **Long runs need checkpoints.** [train.py](../../core/rl/train.py) saves only at the
  end: a run killed by the time limit or a node failure loses everything. Saving
  every N steps and resuming is needed before multi-hour runs.
- **Parallel sampling (level 2) helps CTCE, not DTDE.** CTCE spends about 88 %
  of a step in the market: 4 env runners would make it about 3 x faster for
  about 1.7 x the CPU-hours. DTDE spends about 70 % learning: at most about 1.4 x
  faster, for nearly 4 x the CPU-hours.
- **GPU: no, at 50 agents.** In the benchmark the GPU was slower than the CPU up
  to 39 agents and only clearly faster for CTDE at 118.
- **SAC is the unknown.** Its 5-agent market runs took 150-400 ms per step
  (learning-heavy: many updates per step). If its learner grows with the agents
  like PPO's, SAC DTDE at 50 agents could take about 4 s per step: about a day
  for 24 000 steps. Cheap in euros (about 0.4 EUR), long in wall clock.

### What to measure first

1. One 50-agent scenario on the cluster: the market step time
   ([benchmark_market_step.ipynb](../../notebooks/market/benchmark_market_step.ipynb))
   and the RL benchmark for PPO, APPO and SAC at N = 50
   ([benchmark_speed.ipynb](../../notebooks/rl/benchmark_speed.ipynb)), on a green node.
2. One short real run per paradigm (e.g. 10 000 steps) through `core.runner`, to
   replace the factor 1.5 with a measured one.
3. Then fill this table with the measured seconds per 1000 steps.


## Sizing

These are **shared-Ray probe-notebook** sizing examples, not defaults for the
experiment job array. The 38-worker shared-instance timing above remains an
estimate. For current array settings, use [Resources](resources.md).

- CPUs = 2 x (runs at once + 1); memory about 1-1.5 GB x runs at once.
- 38 runs: `-c 78 --mem=60G`. One probe's 9 runs: `-c 20 --mem=16G`.
- Time limit: the slowest run plus margin; a whole probe set is about 20-30 min.
- After a job, `seff <jobid>` shows the real CPU efficiency and peak memory.

