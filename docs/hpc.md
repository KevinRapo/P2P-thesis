# TalTech HPC

`marlem-v1` is the source of truth for the market, RL layer, experiment runner,
Studio and this site. The Slurm work has been integrated into this branch; the
cluster target now uses `~/marlem-v1`. Older worktrees and their ignored result
folders are historical copies, not the active code or documentation.

There are two distinct workflows:

| Workflow | Runs where | Control |
|---|---|---|
| Notebook session | One Slurm allocation hosts Jupyter and the notebook's training processes | `hpc start`, VS Code kernel, `hpc stop` |
| Training experiment | One Slurm array element per independent run | `python -m core.runner` or the Studio's Runs page |

A Jupyter job is **not needed** to submit an experiment. The `hpc` helper manages
Jupyter; `core.runner` manages experiment arrays. Their CPU settings are separate.

| Read next | What it covers |
|---|---|
| [Setup and helper scripts](hpc/setup.md) | SSH, tracked Windows helpers, PATH, Git aliases, rebuilding Python and Jupyter |
| [Notebook sessions](hpc/notebooks.md) | Start a session, connect VS Code, change its allocation, stop it |
| [Training experiments](hpc/experiments.md) | Experiment/profile/target, CLI and Studio, files, restart and sync semantics |
| [Resources and parallelism](hpc/resources.md) | Independent runs versus environment runners, CPUs/RAM/time, supported settings |
| [Measurements and estimates](hpc/performance.md) | Dated probe timings, shared Ray, market cost assumptions and unmeasured work |
| [Monitoring and troubleshooting](hpc/operations.md) | Logs, `seff`, scheduler state, results and common failures |

Run commands from the `marlem-v1` worktree unless a page says to run them on the
cluster. The target is configured in [hpc/targets.toml](../hpc/targets.toml), and
the Windows helpers are tracked in [scripts/](../scripts/).

## Links from the previous single-page guide

The old `/hpc/` address is retained. These links lead to the relocated sections.

<span id="1-update-the-code-on-the-cluster-only-after-changing-core"></span>

- [Update the code on the cluster](hpc/notebooks.md#1-update-the-code-on-the-cluster)

<span id="access"></span>

- [Access](hpc/setup.md#access)

<span id="what-is-where"></span>

- [What is where](hpc/setup.md#what-is-where)

<span id="the-loop"></span>

- [The loop](hpc/notebooks.md#the-loop)

<span id="quick-commands-hpc"></span>

- [Quick commands (`hpc`)](hpc/setup.md#quick-commands-hpc)

<span id="start-a-session-by-hand"></span>

- [Start a session (by hand)](hpc/notebooks.md#start-a-session-by-hand)

<span id="stop"></span>

- [Stop](hpc/notebooks.md#stop)

<span id="change-the-job"></span>

- [Change the job](hpc/notebooks.md#change-the-job)

<span id="hardware-and-limits"></span>

- [Hardware and limits](hpc/performance.md#hardware-and-limits)

<span id="parallel-training-what-was-learned"></span>

- [Parallel training (what was learned)](hpc/performance.md#parallel-training-what-was-learned)

<span id="cost-estimate-the-market-experiment-at-50-agents"></span>

- [Cost estimate: the market experiment at 50 agents](hpc/performance.md#cost-estimate-the-market-experiment-at-50-agents)

<span id="sizing"></span>

- [Sizing](hpc/performance.md#sizing)

<span id="watch-and-measure"></span>

- [Watch and measure](hpc/operations.md#watch-and-measure)

<span id="experiments-on-the-cluster"></span>

- [Experiments on the cluster](hpc/experiments.md#experiments-on-the-cluster)

<span id="results"></span>

- [Results](hpc/operations.md#results)

<span id="problems"></span>

- [Problems](hpc/operations.md#problems)

<span id="rebuild-the-cluster-environment"></span>

- [Rebuild the cluster environment](hpc/setup.md#rebuild-the-cluster-environment)

<span id="git-aliases"></span>

- [Git aliases](hpc/setup.md#git-aliases)

<span id="2-start-jupyter-as-a-job"></span>

- [2. Start Jupyter as a job](hpc/notebooks.md#2-start-jupyter-as-a-job)

<span id="3-open-the-tunnel"></span>

- [3. Open the tunnel](hpc/notebooks.md#3-open-the-tunnel)

<span id="4-connect-the-notebook"></span>

- [4. Connect the notebook](hpc/notebooks.md#4-connect-the-notebook)

<span id="edit-the-job-script"></span>

- [Edit the job script](hpc/notebooks.md#edit-the-job-script)

<span id="what-can-run-in-parallel"></span>

- [What can run in parallel](hpc/performance.md#what-can-run-in-parallel)

<span id="cost-of-one-environment-step-at-50-agents"></span>

- [Cost of one environment step at 50 agents](hpc/performance.md#cost-of-one-environment-step-at-50-agents)

<span id="per-run-ppo-240-000-steps-as-in-market_3x3json"></span>

- [Per run (PPO, 240 000 steps as in market_3x3.json)](hpc/performance.md#per-run-ppo-240-000-steps-as-in-market_3x3json)

<span id="the-whole-grid"></span>

- [The whole grid](hpc/performance.md#the-whole-grid)

<span id="what-the-numbers-say"></span>

- [What the numbers say](hpc/performance.md#what-the-numbers-say)

<span id="what-to-measure-first"></span>

- [What to measure first](hpc/performance.md#what-to-measure-first)
