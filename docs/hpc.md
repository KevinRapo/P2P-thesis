# TalTech HPC: running on the cluster

> How the thesis code runs on TalTech's HPC cluster: Jupyter notebooks whose kernel
> is a cluster compute node, and training experiments (`core.runner`) as SLURM job
> arrays. Set up on 2026-10-16; the measurements below are from that day.

Two ways to use the cluster:

- **Notebooks on a compute node.** VS Code on this PC, the notebook's kernel on a
  cluster compute node, connected through an SSH tunnel. Used for the probe
  notebook and the benchmarks.
- **Experiments as SLURM jobs.** `core.runner` submits the runs of an experiment as
  a job array from this PC or from the Studio, no Jupyter job needed.

| I want to | Go to |
|---|---|
| run a notebook on a compute node | [The loop](#the-loop) |
| train an experiment on the cluster | [Experiments on the cluster](#experiments-on-the-cluster) |
| choose CPUs, memory and time | [Sizing](#sizing), [Change the job](#change-the-job) |
| estimate what a market experiment costs | [Cost estimate](#cost-estimate-the-market-experiment-at-50-agents) |
| find out why something fails | [Problems](#problems) |
| set the cluster up again | [Rebuild the cluster environment](#rebuild-the-cluster-environment) |

## Access

- Login node: `base.hpc.taltech.ee`, user `kerapo`, short name `taltech` (in your
  `~/.ssh/config`, key login).
- Billing account: `user_kerapo` (personal, about 10 EUR per quarter).
  Later a project account: change `--account` in the job script.
- Off campus: connect the TalTech VPN first.
- Docs: <https://docs.hpc.taltech.ee/>. Support: hpcsupport@taltech.ee.

## What is where

| Thing | Location |
|---|---|
| Notebook files you edit | This PC |
| Code the kernel imports (`core/`) | Cluster: `~/marlem-v1` (a git clone) |
| Files the code writes (`runs/`) | Cluster: `~/marlem-v1/runs/` |
| Python environment | Cluster: `~/miniforge3/envs/marlem` |
| Jupyter job script | Cluster: `~/jupyter.slurm` |
| Jupyter token | Cluster: `~/.jupyter_token` |
| Job logs | Cluster: `~/jupyter-<jobid>.out` |

Cell edits need no sync: VS Code sends the cell text when you run it. Changes to
`core/` (or scenario / experiment files) need a push here and a pull there, then a
kernel restart.

## The loop

On this PC, in `marlem-v1`:

```powershell
git shipc "what changed"
hpc start -c 78 --mem=60G -t 01:30:00
```

Then in VS Code: kernel `TalTech`, restart it, run the cells. When done:

```powershell
hpc stop
```

- `git shipc` commits everything, pushes, and pulls on the cluster (section below).
- `hpc start` submits the Jupyter job, waits for it and opens the tunnel.
- Only notebook cells changed: skip `git shipc`.
- The job above is a whole green node for the probe notebook's 38 workers; size it
  to the work (see [Sizing](#sizing)).

## Quick commands (`hpc`)

`hpc.ps1` wraps the steps below. It and `hpc.cmd` (so that `hpc` also works in cmd)
are in the `scripts/` folder next to the repository checkouts, which is on the
user PATH; they are not part of the repository.

| Command | Does |
|---|---|
| `hpc start` | submit `~/jupyter.slurm` with its own settings, wait for Jupyter, open the tunnel |
| `hpc start -c 78 --mem=60G -t 01:30:00` | the same with `sbatch` options (they override the script) |
| `hpc tunnel` | reopen the tunnel to the running job (closes old ones first) |
| `hpc status` | your jobs and the end of the Jupyter log |
| `hpc log` | the last 30 lines of the Jupyter log |
| `hpc top` | live `top` inside the job |
| `hpc stop` | cancel the job, close local tunnels |

The tunnel window stays open while you work; Ctrl+C closes only the tunnel. Then in
VS Code: kernel `TalTech`, restart it.

- `hpc start` refuses to submit a second job while one named `jupyter` exists.
- If the job dies before Jupyter starts, it prints the job's log.
- The cluster folder of the code is named after the branch checked out here
  (`marlem-v1` is `~/marlem-v1`).
- After changing the user PATH, VS Code has to be restarted fully once to see it
  (it is read when a program starts).

### Git aliases

Two aliases in the repository's `.git/config` (shared by all worktrees; open it with
`git config --edit`):

```ini
[alias]
	pushc = "!f() { b=$(git rev-parse --abbrev-ref HEAD); if [ $# -eq 0 ]; then git push -u origin HEAD; else git push \"$@\"; fi && ssh -o BatchMode=yes taltech \"cd ~/$b && git pull --ff-only\" 2>&1 | grep -v \"^tput:\"; }; f"
	shipc = "!f() { if [ -z \"$1\" ]; then echo \"usage: git shipc \\\"commit message\\\"\"; return 1; fi; git add -A && git commit -m \"$1\" && git pushc; }; f"
```

| Command | Does |
|---|---|
| `git shipc "message"` | `git add -A`, commit, push, pull on the cluster |
| `git pushc` | push, then pull on the cluster |

## Start a session (by hand)

### 1. Update the code on the cluster (only after changing `core/`)

On this PC, in `marlem-v1`, after committing:

```powershell
git pushc
```

`git pushc` is the alias above: `git push`, then, if that succeeded,
`git pull --ff-only` in `~/marlem-v1` on the cluster. Extra arguments go to
`git push` (e.g. `git pushc origin marlem-v1`). VS Code's Sync button runs plain
`git push` (pull by hand, below).

Everything in one go (stage all changes, commit, push, pull on the cluster):

```powershell
git shipc "commit message"
```

`git shipc` runs `git add -A`, `git commit -m "..."` and `git pushc`, each only
if the previous step succeeded; without a message it only prints its usage.
`add -A` stages everything in the worktree, new files included: check
`git status` first when unsure.

Pull by hand after a plain push:

```powershell
ssh taltech "cd ~/marlem-v1 && git pull --ff-only"
```

Restart the cluster kernel afterwards so it imports the new code.

### 2. Start Jupyter as a job

Log in:

```powershell
ssh taltech
```

Then on the cluster, one of:

```bash
sbatch ~/jupyter.slurm
```

```bash
sbatch -c 78 --mem=60G -t 01:30:00 ~/jupyter.slurm
```

```bash
sbatch -c 20 --mem=20G -t 03:00:00 ~/jupyter.slurm
```

- The first uses the script's own settings (4 CPUs, 8 GB, 2 h, partition `short`).
- The second takes a whole green node: 39 physical cores, 38 training workers.
- The third fits one probe's 9 runs at full speed.
- Options on the command line override the `#SBATCH` lines in the script.

Wait until the job runs (`ST` = `R`; `NODELIST` shows the node):

```bash
squeue -u $USER
```

Check that Jupyter started (look for `Jupyter Server ... is running at`):

```bash
tail -5 ~/jupyter-*.out
```

### 3. Open the tunnel

On this PC, in a new PowerShell window, left open while you work:

```powershell
$node = ssh taltech "squeue -u kerapo -n jupyter -h -o %N"
echo $node
ssh -N -L 9437:${node}:9437 taltech
```

The window looks frozen: that is the open tunnel. A new job means a new node, so
close the old tunnel (Ctrl+C) and run these three lines again.

### 4. Connect the notebook

In VS Code: kernel picker, then `TalTech` server, then `Python 3 (ipykernel)`.
After a new job, restart the kernel and run the cells from the top.

First time only: Select Another Kernel, Existing Jupyter Server,
`http://localhost:9437/?token=<token>`. Show the token with:

```powershell
ssh taltech "cat ~/.jupyter_token"
```

Check where the kernel runs (expect the node name, the job ID, the CPU count):

```python
import os, socket
print(socket.gethostname(), os.environ.get("SLURM_JOB_ID"), os.environ.get("SLURM_CPUS_PER_TASK"))
```

## Stop

On the cluster (billing stops here):

```bash
scancel -n jupyter
squeue -u $USER
```

Then Ctrl+C in the tunnel window, and switch the notebook back to the local
`marlem` kernel for local work. A forgotten job ends by itself at its `-t` limit.

## Change the job

| To change | Option | Notes |
|---|---|---|
| CPUs | `-c 20` | SLURM counts hyper-threads: CPUs = 2 x physical cores |
| Memory | `--mem=20G` | Green node: about 90 GB usable |
| Time limit | `-t 03:00:00` | Job and every run are killed when it is reached |
| Partition | `-p short` | `short` up to 4 h, `common` up to 8 days |
| GPU | `-p gpu --gres=gpu:L40:1` | 0.62 EUR per GPU-hour; likely little gain for this code |
| Account | `--account=project_xxx` | Once a project account exists |

One-off changes: put the option on the `sbatch` line. Permanent changes: edit
`~/jupyter.slurm` (script below).

### Edit the job script

- VS Code: Remote-SSH, connect to `taltech`, File, Open File, `~/jupyter.slurm`.
  Close that window when done; it runs a small server on the login node.
- Browser: OnDemand, Files, Home Directory, `jupyter.slurm`, Edit.
- Terminal on the cluster: `nano ~/jupyter.slurm` (Ctrl+O, Enter, Ctrl+X).

## Hardware and limits

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
- Prices: 0.008 EUR per CPU-hour, 0.62 EUR per GPU-hour. Billing is CPUs booked x
  wall time, used or idle.

## Parallel training (what was learned)

Probe notebook ([probe_paradigms.ipynb](../notebooks/rl/probe_paradigms.ipynb)),
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
  [train.py](../core/rl/train.py) then joins it instead of starting its own.
  Results are unchanged (each run samples and learns in its own process). The run
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
been timed on the cluster (see [What to measure first](#what-to-measure-first)).

### What can run in parallel

A market training run is one long sequential loop (sample a day, learn, repeat),
so there is no "one market" to split. Parallelism comes from three places:

| Level | What runs side by side | Speed-up | Cost |
|---|---|---|---|
| 1. Between runs | algorithms x paradigms x seeds x variants: independent runs | number of runs at once (one core each) | none: the same CPU-hours, just sooner |
| 2. Inside a run: sampling | `num_env_runners = k`: k copies of the market simulate days at once | only the market's share of a step gets k times faster | the k runner cores wait while the learner updates: more CPU-hours |
| 3. Inside a run: learning | the learner on more threads or a GPU | small networks gain little; measured GPU gains only for CTDE at 118 agents | GPU-hours cost 78 x a CPU-hour |

Level 1 is where the cluster pays off: a 3 x 3 grid with 5 seeds is 45
independent runs, about one green node's worth (38 at once, shared Ray).

### Cost of one environment step at 50 agents

One environment step is one market hour for all agents. Per 1000 steps:

| Part | Seconds per 1000 steps | Source |
|---|---|---|
| Market + power flow | about 42 | [market_step.csv](../notebooks/market/results/market_step.csv): 41 ms at 53 agents (urban6), 40 ms at 39 |
| RL, PPO CTCE | about 5.5 | [benchmark_speed.ipynb](../notebooks/rl/benchmark_speed.ipynb), "paper" preset, between 39 and 118 agents |
| RL, PPO CTDE | about 40 | same (27 at 39 agents, 124 at 118) |
| RL, PPO DTDE | about 100 | same (76 at 39 agents, 248 at 118) |

The RL cost is the learner: CTDE and DTDE have one network per agent, so it grows
with the number of agents; CTCE has one network. The market's cost grows slowly.

### Per run (PPO, 240 000 steps as in market_3x3.json)

The budget is that of [market_3x3.json](../experiments/market_3x3.json). The
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

- **Money is not the constraint.** A full PPO/APPO grid costs a few euros; even
  10 seeds stays near 10 EUR. The personal account's 10 EUR per quarter is about
  one such grid; a project account removes the limit.
- **Wall clock is.** A DTDE run at 50 agents takes about half a day. That needs
  `-p common` (8 days), not `short` (4 h).
- **Long runs need checkpoints.** [train.py](../core/rl/train.py) saves only at the
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
   ([benchmark_market_step.ipynb](../notebooks/market/benchmark_market_step.ipynb))
   and the RL benchmark for PPO, APPO and SAC at N = 50
   ([benchmark_speed.ipynb](../notebooks/rl/benchmark_speed.ipynb)), on a green node.
2. One short real run per paradigm (e.g. 10 000 steps) through `core.runner`, to
   replace the factor 1.5 with a measured one.
3. Then fill this table with the measured seconds per 1000 steps.

## Sizing

- CPUs = 2 x (runs at once + 1); memory about 1-1.5 GB x runs at once.
- 38 runs: `-c 78 --mem=60G`. One probe's 9 runs: `-c 20 --mem=16G`.
- Time limit: the slowest run plus margin; a whole probe set is about 20-30 min.
- After a job, `seff <jobid>` shows the real CPU efficiency and peak memory.

## Watch and measure

Live view inside the running job (`q` to quit):

```bash
srun --jobid=$(squeue -u $USER -n jupyter -h -o %i) --overlap --pty top
```

After a job: how much of the CPUs and memory it used, to size the next one:

```bash
seff <jobid>
```

Jobs since a date, with run time and CPUs:

```bash
sacct -u $USER --starttime=2026-10-01 --format=JobID,JobName,Partition,Elapsed,AllocCPUS,State
```

Free nodes per partition:

```bash
sinfo -p short,common
```

## Experiments on the cluster

Training experiments (`core.runner`, specs in [experiments/](../experiments/)) run
as a SLURM job array, one task per run, started from this PC without a Jupyter
job. The cluster is a *target* in [hpc/targets.toml](../hpc/targets.toml). What a
target, a profile and the Studio's Runs page are, and the limits of this version,
are in [v1.md](v1.md#on-this-pc-or-on-the-cluster).

```powershell
python -m core.runner check experiments/smoke.json --target taltech
python -m core.runner start experiments/smoke.json --profile test --target taltech
python -m core.runner status smoke--test --target taltech
python -m core.runner sync smoke--test --target taltech
```

`check` says `ready`, or lists what stops a start (cluster not answering, commits
differ, uncommitted changes on the cluster, spec not committed) and which
experiments are queued or running. `start` refuses with the same list. Run the
test profile first. The Studio's Runs page does the same (TalTech tab).

Two things from above matter here:

- While an experiment is queued or running, do not update or edit the cluster's
  checkout: no `git shipc` or `git pushc` (they pull there), no edits. A task reads
  the checkout when it starts.
- Each run starts its own Ray instance, so keep `resources.cpus` at 4 or more to
  have few runs share a node (4096 threads per user per node, see
  [Parallel training](#parallel-training-what-was-learned)).

## Results

Browse without a job: <https://ondemand.hpc.taltech.ee> (Files, Home Directory).

Copy a run folder to this PC (from the repository root):

```powershell
scp -r taltech:~/marlem-v1/runs/probes_thorough .\runs\
```

## Problems

| Symptom | Fix |
|---|---|
| `ssh taltech` hangs | VPN off |
| Tunnel: `channel ... open failed` | Job not running yet, or Jupyter crashed: read `~/jupyter-<jobid>.out` |
| Log says port in use | Change `9437` in the script and in the tunnel lines |
| VS Code cannot connect | Tunnel window closed or job ended |
| Kernel dies suddenly | `-t` limit reached, or out of memory (`seff <jobid>`) |
| Old code runs | `git pull` on the cluster, restart the kernel |
| `git pull` refuses | Files changed on the cluster: `git status` there |
| `tput: No value for $TERM` | Harmless |
| Many `Failed to connect to GCS`, `Resource temporarily unavailable` | Thread limit hit: too many Ray instances; use the shared Ray (train cell) or fewer workers |
| All runs stay `running` in `run.json`, no processes | They died before recording a failure; rerun the cell (only unfinished runs train) |
| `hpc` not found in VS Code terminal | Restart VS Code fully (PATH is read at start) |

## Rebuild the cluster environment

On `base` (free; the environment is not backed up):

```bash
cd ~
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3
~/miniforge3/bin/conda init bash
source ~/.bashrc
conda create -n marlem python=3.12 -y
conda activate marlem
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu126
pip install "ray[rllib]==2.51.1" benchmarl==1.5.2 torchrl==0.11.1 gymnasium==1.1.1 pettingzoo==1.27.0 pandapower==3.5.4 simbench==1.6.2 numpy==2.4.6 pandas==2.3.3 scipy matplotlib plotly numba pyyaml pydantic tensorboard jupyterlab ipykernel
git clone -b marlem-v1 https://github.com/KevinRapo/P2P-thesis.git ~/marlem-v1
```

The Jupyter token (a file only you can read) and the job script `~/jupyter.slurm`:

```bash
openssl rand -hex 16 > ~/.jupyter_token
chmod 600 ~/.jupyter_token
```

```bash
#!/bin/bash
#SBATCH --job-name=jupyter
#SBATCH --account=user_kerapo        # later: project_xxx
#SBATCH --partition=short            # max 4 h
#SBATCH --time=02:00:00              # job and billing end here at the latest
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out

source ~/miniforge3/etc/profile.d/conda.sh
conda activate marlem
cd "${REPO:-$HOME/marlem-v1}"
echo "Jupyter on node $(hostname), port 9437"
jupyter lab --no-browser --ip=0.0.0.0 --port=9437 --ServerApp.port_retries=0 \
    --IdentityProvider.token="$(cat ~/.jupyter_token)"
```

`hpc start` passes `REPO`, the cluster folder named after the current branch;
without it the script uses `~/marlem-v1`. Jupyter listens on the node's network,
protected by the token: reach it only through the tunnel, and keep the token file
private.
