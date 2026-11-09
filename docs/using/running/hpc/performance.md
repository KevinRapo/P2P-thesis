# Measurements and costs

What runs cost on TalTech, measured from 13 October to 5 November 2026. The
runner's settings that follow from it are in [resources](resources.md).

## The cluster

| Nodes | Count | Per node | Partitions |
|---|---|---|---|
| green | 28 | 40 cores (80 threads, 78 for SLURM), 95 GB | `short`, `common`, `long` |
| blackwell1 | 1 | 256 cores (512 threads, AMD EPYC 9755), 1 TB | `short` (and `mig-test`, not used here) |
| ada | 2 | 64 cores, 1.5 TB, 2 × L40 48 GB | `gpu`, `short` |
| amp, amp2 | 2 | 128 cores, 1–2 TB, 8 × A100 | `gpu`, `short` |

- Partitions: `short` up to 4 h, `common` 8 days, `long` 22 days, `gpu` 5 days.
  `short` can land on any node type; `-p common` is green only, `-w blackwell1`
  asks for that node. `sinfo` shows what is free.
- SLURM counts hyper-threads: `-c 78` is 39 physical cores.
- **4096 processes and threads per user per node** (`ulimit -u`, checked again on
  5 November). This limits parallel training before cores or memory do
  ([how many runs fit](resources.md#how-many-runs-fit-at-once)).
- No per-user cap on jobs, CPUs or submits (`normal` QOS, checked 19 Oct).
- Compute nodes have internet; install on `base` anyway.
- Prices used below: 0.008 EUR per CPU-hour, 0.62 EUR per GPU-hour. TalTech's
  [billing table](https://docs.hpc.taltech.ee/billing.html) bills per CPU *core*
  hour and adds a memory rate above 6 GB per core, so check how a job of
  hyper-threads is billed before trusting the euro figures.

## Market runs

### Time per paradigm

`base_long_p13`, 5 November 2026: blackwell1, `lv_rural3_p13` (13 participants,
power flow, hourly steps), PPO with batch 4000, minibatches of 500 and 10 epochs, 8
env runners and 10 CPUs per run, nine runs at once. Seconds per training iteration
of 4000 environment steps (RLlib's `sampling_s_mean` and `learner_call_s_mean` in
`metrics.csv`, the mean of the last 50 iterations), and what that makes per 1000
steps and per run:

| Paradigm | Sampling | Learning | s per 1000 steps | Hours per 1M steps | 1.2M steps, wall clock |
|---|---:|---:|---:|---:|---|
| CTCE | 14.0 | 3.9 | 4.6 | 1.3 | 1 h 29 – 1 h 32 |
| DTDE | 18.2 | 13.7 | 8.0 | 2.2 | about 2 h 40 |
| CTDE | 18.9 | 19.7 | 9.7 | 2.7 | about 3 h 10 |

- **Sampling** is the market: 8 runners each play 500 steps per iteration, about
  30 ms per step with the power flow and the policy's inference. CTCE samples a
  little faster: one network answers for all 13 agents.
- **Learning** is what separates the paradigms. CTCE trains one network on one
  sample per market step. DTDE trains 13 (an actor and a critic per agent), each on
  its own agent's samples, so 13 times the rows. CTDE trains the same 13 actors as
  DTDE, but each critic reads every agent's observation (13 × 42 inputs instead of
  42): DTDE plus wider critics, so the slowest.
- The held-out evaluation at the end adds about a minute.
- The speed changes of 5 November (`da36bc0`) took sampling from 20–24 s to 14–19 s
  per iteration against `results_format-moreUpd` (3 November, same scenario and
  settings, twelve runs at once); learning did not change.

### Time against the number of participants

`scale_p13`, `scale_p26`, `scale_p43`, 27 October 2026, before those speed changes:
PPO with RP-6b's batch 500, minibatches of 64 and 10 epochs (8 times the gradient
steps per sample of the table above), 8 env runners, 192,000 steps. Seconds per 1000
environment steps:

| Participants | CTCE | DTDE | CTDE |
|---:|---:|---:|---:|
| 13 | 7.1 | 14.5 | 18.0 |
| 26 | 11.4 | 27.0 | 43.8 |
| 43 | 17.9 | 43.7 | 204 (on green20) |

All on blackwell1, except CTDE at 43 participants, which SLURM put on a green node.
Learning grows with the participants in DTDE (one network more per agent) and
faster in CTDE (one network more, and every critic's input wider); sampling grows
slowly (2.0 to 3.4 s per 500-step iteration in CTCE).

### Memory, CPUs and threads per run

The same runs of 5 November (8 env runners, 13 participants):

| | Measured | What to request |
|---|---|---|
| Memory | 8.3–9.2 GB at the job's peak (the cgroup's `memory.max_usage_in_bytes`; TalTech's Jobs Overview page shows the same curve), flat from the first minutes | `mem_gb` 12 |
| CPUs | 3.6–3.9 cores busy on average of the 10 allocated (`sacct` TotalCPU over Elapsed) | `num_env_runners` + 2 |
| Threads | about 340 per run (nine runs held 3084) | at most 10 such runs per node |

- `sacct`'s MaxRSS reports 12.6 GB for the same runs (15.4 GB with batch 8000): it
  adds up the resident memory of every process in the job, counting shared pages
  once per process. The cgroup counts each page once, and it is the cgroup's limit
  that ends a job. A larger batch does use more memory.
- PPO alternates: during sampling the runners are busy (9 processes), during
  learning only the learner (1). The average is low, but fewer CPUs than runners
  would slow every sampling phase.
- Twelve such runs at once broke the thread limit on 5 November: three crashed at
  start (`RuntimeError: can't start new thread`) and one hung at 0 steps
  ([how many runs fit](resources.md#how-many-runs-fit-at-once)).

### Cost

$$
\text{EUR per run} = \text{hours} \times \text{CPUs} \times 0.008
$$

A CTDE run of 1.2M steps at 13 participants: 3.2 h × 10 CPUs ≈ 0.26 EUR; nine runs
≈ 2 EUR.

- **Money is not the limit; wall clock is.** blackwell1 is only in `short` (4 h):
  about 1.4M steps of CTDE at 13 participants, fewer with more participants or
  smaller batches. Longer runs go to `common` (green nodes, about 2.2–3 × slower per
  run, [below](#blackwell1-against-a-green-node)).
- **No intermediate checkpoints.** [train.py](../../../../core/rl/train.py) saves only at
  the end, and a restarted run starts from scratch: a run killed by its time limit
  loses everything. Size the budget to the slowest paradigm.
- **No GPU** ([below](#gpu-against-cpu)).

## Node types

Measured 20–21 October 2026 with a benchmark script on `MarketEnv`
(`validate_market`, first week of June), the PPO settings in use then, one torch
thread, no remote samplers. Seconds per 1000 environment steps; one measurement
each. The absolute times are out of date (the market and the settings have changed
since); the ratios between the nodes are what these tables are for.

### Blackwell1 against a green node

Both jobs at the same time, 4 CPUs each.

| | green24 (Xeon Gold 6148) | blackwell1 (EPYC 9755) | Speed-up |
|---|---|---|---|
| PPO CTCE | 29.7 | 10.1 | 2.96 × |
| PPO CTDE | 32.6 | 12.1 | 2.69 × |
| PPO DTDE | 34.0 | 12.7 | 2.69 × |

- The market and power flow take about 10 s on blackwell1 and 24–32 s on green
  (about 3 ×).
- TalTech bills per core-hour at the same price on every node, so a run on
  blackwell1 costs about half as much. It is only in `short` (4 h), and it is one
  node: choose it with `resources.node` ([resources](resources.md#what-a-run-gets)).

### GPU against CPU

amp1, one A100, the same job for both:

| | CPU | GPU | CPU learning | GPU learning |
|---|---|---|---|---|
| PPO CTCE | 21.0 | 18.8 | 0.65 | 0.74 |
| PPO CTDE | 23.6 | 23.6 | 2.25 | 2.68 |
| PPO DTDE | 23.4 | 23.4 | 2.18 | 2.58 |

No gain: the networks are small (2 × 256), and the market is CPU bound; use CPU
nodes.

## The probe notebook

The probe notebook ([probe_paradigms.ipynb](../../../../notebooks/rl/probe_paradigms.ipynb))
runs many short runs in one Jupyter job, all joining one Ray instance:

| Where | Runs at once | Ray | Total |
|---|---|---|---|
| This PC, 13 Oct | 3 | one per run | about 91 min; 4 of 45 failed (Ray start-up, memory) |
| green28, 16 Oct | 16 | one per run | 27 min, capped by the thread limit |
| green24, 23 Oct (PPO, probes 1-10 × 3 paradigms, `"fast"`) | 30 | one shared | 301 s for all 30; with `escalate` (failures again at 2×, 4×, 8×) 1 h 05 min; peak memory 22 GB on `-c 78 --mem=60G` (job 1047329) |

- A probe run is one process on one core (about 95 % CPU) and about 0.75 GB.
- Ray sizes its thread pools by the machine's cores: about 1000 threads per
  instance on blackwell1, about 175 with every pool at one thread. 38 instances
  broke the 4096 limit (`Resource temporarily unavailable`, `Failed to connect to
  GCS`). The notebook therefore starts one Ray instance and sets `RAY_ADDRESS`, and
  [train.py](../../../../core/rl/train.py) joins it; each run still samples and learns
  in its own process (started with `spawn`). Workers: one per physical core less
  one, at most (4096 − 1000) / 80.
- Ray's `Failed to establish connection to the ... metrics exporter agent` lines
  are harmless.

Sizing such a job:

- CPUs = 2 × (runs at once + 1); memory about 1–1.5 GB × runs at once.
- 30–38 runs: `-c 78 --mem=60G`. One probe's 9 runs: `-c 20 --mem=16G`.
- Time limit: the slowest run plus a margin; a whole probe set takes about 20–30 min.
- After a job, `seff <jobid>` shows the real CPU efficiency and peak memory.
