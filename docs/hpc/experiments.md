# Training experiments

An experiment is defined once, as a spec in [experiments/](../../experiments/), and
runs on a target; the CLI, Python and the Studio's Runs page call the same runner,
[core/runner/](../../core/runner/) ([API](../api/runner/index.md)).

| Term | Meaning |
|---|---|
| Experiment | Algorithms × paradigms × seeds × variants, with budgets, scenario, train and test days, training settings and cluster resources ([spec.py](../../core/runner/spec.py)) |
| Profile | `full`: the spec as written. `test`: its smallest version, named `<name>--test` ([what it keeps](resources.md#full-and-test-profiles)) |
| Target | `local` (this PC: a detached worker) or `taltech` (one SLURM job array, a task per run, via submitit), from [hpc/targets.toml](../../hpc/targets.toml) with your account and host from `.env` ([setup](setup.md#this-machines-settings-env)) |

Every run ends with a held-out evaluation: the trained policy and the baselines
play **every test day once** (seeds 2000, 2001, ...), and the results are kept per
day and per participant ([Files](#files)). With `"results_detail": "detailed"` in the
spec the days of `trace_days` (default: the first 3 test days, or a list of them) are
also kept step by step. The [Results](#results) page compares the runs.

## Commands

From the `marlem-v1` root, in the `marlem` environment:

```powershell
python -m core.runner check experiments/smoke.json --target taltech
python -m core.runner start experiments/smoke.json --profile test --target taltech
python -m core.runner status --target taltech
python -m core.runner status smoke--test --target taltech
python -m core.runner sync smoke--test --target taltech
python -m core.runner stop smoke--test [run] --target taltech
```

Without `--target` (or with `--target local`) the same commands run on this PC.
`start` returns at once; `status` lists every experiment, or one experiment's runs
with state, progress, ETA and scores (on the cluster also the SLURM state and
node). `--json` gives the same answers as JSON; that is also how this PC talks to
the cluster.

**`check`** says whether a start would work: `ready`, or the problems (the cluster
does not answer, this PC and the cluster are at different commits, the cluster's
checkout has changes, the spec or its scenario does not load), with both commits
and the experiments queued or running there. `start` runs the same check and
refuses with its problems. Exit code 1 when not ready.

**What a start sends.** The spec and its scenario go with the start: this PC reads
both, applies the profile and sends the experiment as one JSON object over SSH
(`python -m core.runner start -` on the cluster, reading standard input). The
cluster saves it in the experiment's folder and its runs read only that copy. So
a spec or scenario changed here, committed or not, starts on the cluster as it is
here, with no commit and no `git shipc`. Only the **code** must be the same on both
machines: that is still what `check` compares. The same holds on this PC: every
start saves the spec with its scenario in `runs/<experiment>/`, so editing
`scenarios/` later does not change an experiment already started.

**`sync`** copies the experiment's results to `runs/@taltech/<experiment>`,
without checkpoints and `slurm/`. The copy goes to a temporary folder that replaces
the old one only when complete, so a failed download keeps the previous copy;
files removed on the cluster disappear here too. Nothing is copied unless asked.

**Restarting:** `start` on an existing experiment keeps its completed runs and
starts failed, stopped and lost ones again, **from scratch** (there is no
checkpoint resume). A changed spec, or a changed scenario, is refused: use a new
name.

## Python and the Studio

```python
from core.runner import targets
from core.runner.spec import Experiment

target = targets.get("taltech")
try:
    print(target.check("experiments/smoke.json"))
    # name = target.start("experiments/smoke.json", profile="test")
    # A changed copy, as the Studio's start dialog makes it; a taken name is dated:
    # experiment = Experiment.load("experiments/smoke.json")
    # experiment.seeds = [0, 1, 2]
    # name = target.start_new(experiment, profile="test")
    # target.restart(name)  # again from its saved settings
    # print(target.runs(name))
    # folder = target.sync(name)
finally:
    target.close()
```

[targets_demo.ipynb](../../notebooks/runner/targets_demo.ipynb) walks through it.

The Studio (`python run_studio.py`, page **Runs**) has a tab per target. This PC is
read every 2 s, the cluster every 10 s while its tab is shown. The cluster's tab
shows the `check` line with a Check button, and each experiment has a *Sync
results* button. When the cluster cannot be read, the page keeps the last data with
its time.

*Start experiment* takes a spec from `experiments/` as a **template** and shows its
JSON in an editor: change anything (the fields are those of [an experiment
file](../../core/runner/spec.py)). Every edit is checked as a start would check it,
and the dialog shows the runs it makes, or what is wrong. The template file is
never changed. Two presets rewrite the editor's run size settings (name,
description, seeds, train and test days, budget, evaluation, traced days,
resources) and leave every other edit: **Test preset** makes them the template's
[test version](resources.md#full-and-test-profiles) (`<name>--test`) and picks this
PC, **Full preset** puts back the template's values and picks the cluster. The
text can be edited again after a preset; what the editor holds is what starts.
Start sends the edited experiment to the chosen target, always as a **new**
experiment: if the target already has one of that name, the
date and time are added (`<name>-20261018-143200`), so one template can start any
number of experiments, each with its own saved settings. For the cluster the
dialog checks the target and keeps Start disabled while there are problems.

**Restart failed runs** (on an experiment with failed, stopped or lost runs and none
queued or running) starts the experiment again from the settings saved in its
folder, whatever the template says now: its completed runs stay.

## Files

Everything is in `runs/<experiment>/`, so any terminal and the Studio see the same
state:

| File | What |
|---|---|
| `experiment.json` | The spec as started, with its scenario in it (a later start must match it) |
| `scenario.json` | The scenario the runs read (a copy of the one in `experiment.json`) |
| `worker.json`, `worker.log` | This PC: the worker that keeps `max_parallel` runs going |
| `slurm.json`, `slurm/` | Cluster: the array and submitit's scripts and task logs |
| `<run>/status.json` | The run's state, times, error, process or SLURM task |
| `<run>/run.json` | Training settings, versions, commit and outcome |
| `<run>/metrics.csv` | Training iterations: environment steps, training return, learner metrics per module and their mean, min and max over the modules (`modules/<metric>_mean`, ...), timing |
| `<run>/evaluation.csv` | Evaluations during training: one row per evaluation point and policy (means) |
| `<run>/evaluation_agents.csv`, `evaluation_episodes.csv` | The same evaluations per episode and participant, and per episode (with its day) |
| `<run>/heldout.csv` | The held-out evaluation: one row per policy (means over the test days) |
| `<run>/heldout_episodes.csv` | One row per policy and test day: team return, P2P and DSO energy, trade losses, fees, the power flow's grid import, export, losses, violations and non-converged steps |
| `<run>/heldout_agents.csv` | One row per policy, test day and participant: return, profit, bill, bought, sold, deferred demand and supply |
| `<run>/heldout_trace_steps.csv`, `heldout_trace_agents.csv` | Only with `"results_detail": "detailed"`: the traced test days per step (market, grid, clearing price, voltages) and per step and participant (order, trades, battery state of charge, reputation, reward) |
| `<run>/checkpoint/` | The policy at the end of training |
| `<run>/log.txt` | This PC: the job's output (on the cluster it is in `slurm/`) |

`run.json` covers training; `status.json` the whole job, held-out evaluation
included. Amounts are in kWh and the scenario's money unit, summed over a day; the
fields are defined in [market_env.py](../../core/env/market_env.py) (its infos).
The tables grow in rows, not columns, with the number of participants.

## Results

The Studio's **Results** page and the notebook
[results.ipynb](../../notebooks/runner/results.ipynb) read the same saved files
through [results.py](../../core/runner/results.py): this PC's runs and a cluster's
**after Sync results** (`runs/@taltech/`, listed under the cluster's name, never
twice). Nothing is trained, no market is built and nothing connects to the cluster.

| Question | What is shown |
|---|---|
| Did it learn? | The trained policy's evaluation return over environment steps, per run, with each run's own baselines at step 0 (one line when they are the same); team or per participant; optionally the training return |
| How good is the final policy? | Every held-out test day: the trained policy minus each baseline on the same day |
| How consistent is it? | Each configuration (experiment, algorithm, paradigm, variant) over its training seeds: mean, spread over seeds, seeds done, and the settings that differ inside a group |
| One run in detail | Its settings, test days, participants × days (an outcome: return, profit, bill, energy; trained minus a baseline; with many participants the 30 with the largest difference, or those a filter names), the market and grid per day, and the traced days step by step (read when opened) |

Runs are compared on their full saved settings (the scenario's contents, every
train and test day, budget, training settings, model, results detail, commit):
the page lists every one that differs. Runs from more than one target keep the
target in their names.

An evaluation day and a training seed are different units: the spread over seeds
comes from separate runs, never from the days or participants of one run. Runs from
before the per-day tables show their means only.

## Limits

1. **Leave the cluster's checkout alone while its experiments are queued or
   running** (`git shipc`, `git pull`, edits): each task reads the checkout when it
   starts, so a queued task would run the newer code. `check` lists them.
2. **Changes to the code are not detected**, only changes to the spec and its
   scenario: use a new experiment name for them too. `run.json` records the commit
   each run trained with.
3. **One start at a time** across the CLI and the Studio; nothing stops two
   starts from two places at once.
4. **Each run starts its own Ray instance.** Keep `resources.cpus` at 4 or more so
   few runs share a node: TalTech allows 4096 threads per user per node
   ([why](performance.md#parallel-training)).
5. **No retries over SSH.** A failed call raises its error and the next call
   reconnects; after a lost answer to `start`, look at `status` before starting
   again.

## Existing execution evidence

Test-profile runs, inspected on 17 October 2026 in the former `marlem-slurm`
worktree (results not in git):

| Workload | Outcome |
|---|---|
| `market_3x3--test`, this PC | All nine runs completed (no remote environment runners, no GPU) |
| `market_3x3--test`, TalTech | Array `1042752`: all nine tasks completed |
| `sac_alpha--test`, TalTech | Array `1042740`: two runs completed with learner metrics past the warm-up, one stopped |

They show the pipeline working end to end, not learning results. The earlier
market results are in [v1.md §5](../v1.md#5-validation).
