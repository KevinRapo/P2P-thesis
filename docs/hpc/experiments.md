# Training experiments

An experiment is defined once, as a spec in [config/experiments/](../../config/experiments/), and
runs on a target; the CLI, Python and the Studio's Runs page call the same runner,
[core/runner/](../../core/runner/) ([API](../api/runner/index.md)).

| Term | Meaning |
|---|---|
| Experiment | Algorithms × paradigms × seeds × variants, with budgets, scenario, train and test days, training settings and cluster resources ([spec.py](../../core/runner/spec.py)) |
| Profile | `full`: the spec as written. `test`: its smallest version, named `<name>--test` ([what it keeps](resources.md#full-and-test-profiles)) |
| Target | `local` (this PC: a detached worker) or `taltech` (one SLURM job array, a task per run, via submitit), from [hpc/targets.toml](../../hpc/targets.toml) with your account and host from `.env` ([setup](setup.md#this-machines-settings-env)) |

Every run ends with a held-out evaluation: the trained policy and the baselines
play **every test day once** (seeds 2000, 2001, ...), and the results are kept per
day, per participant and per step ([Files](#files)). The [Results](#results) page
compares the runs.

## The experiment file

A spec gives only what differs from the defaults. Written out in full, with every
setting at the value its runs use, [market_ppo.json](../../config/experiments/market_ppo.json)
is the one below; the Studio's Experiments page shows every template this way
([`written_out`](../../core/runner/spec.py), the same runs as the file), with the
paradigms, seeds, budget, PPO settings, workers and cluster resources also as
fields that rewrite the JSON:

```json
{
  "name": "market_ppo",
  "description": "PPO in the three paradigms (CTCE, CTDE, DTDE) on the market with the mixed action.",
  "env": "market",
  "scenario": "config/scenarios/validate_market.json",
  "train_days": {"from": "2016-06-01", "to": "2016-06-30"},
  "test_periods": {"july": {"from": "2016-07-01", "to": "2016-07-14"}},
  "env_config": {"energy_scale": null, "reward_scale": null},
  "algorithms": ["ppo"],
  "paradigms": ["ctce", "ctde", "dtde"],
  "seeds": [0],
  "variants": {},
  "budget": 240000,
  "eval_points": 10,
  "eval_episodes": 10,
  "training": {
    "ppo": {
      "lr": 0.0003,
      "gamma": 0.99,
      "lambda_": 0.95,
      "num_epochs": 10,
      "minibatch_size": 240,
      "entropy_coeff": 0.01,
      "clip_param": 0.2,
      "grad_clip": 0.5,
      "use_kl_loss": true,
      "kl_coeff": 0.0,
      "vf_clip_param": 1000000.0,
      "train_batch_size_per_learner": 2400
    }
  },
  "model": {
    "fcnet_hiddens": [256, 256],
    "fcnet_activation": "tanh",
    "head_fcnet_hiddens": [],
    "head_fcnet_activation": "relu",
    "free_log_std": false,
    "log_std_clip_param": 20.0,
    "vf_share_layers": false
  },
  "max_parallel": 3,
  "torch_threads": 1,
  "num_env_runners": 3,
  "ray_thread_caps": true,
  "resources": {"cpus": 4, "mem_gb": 4, "minutes": 120, "node": null},
  "test": {}
}
```

| Settings | What they set | Defaults from |
|---|---|---|
| `name`, `description` | The experiment's folder name (default: the file's name) and free text | |
| `env`, `scenario`, `env_config` | The environment: `"market"` (or `"module:Class"`), the scenario file (or the scenario itself), and the market environment's `energy_scale` and `reward_scale` (null: computed on the training days, recorded in each run's `run.json` and reused for its held-out days, [market_env.py](../../core/env/market_env.py)) | [spec.py](../../core/runner/spec.py) `MARKET_ENV_CONFIG` |
| `train_days`, `test_periods` | Days drawn from in training, and the held-out days as named continuous periods (`{"from", "to"}` or a list each) | |
| `algorithms`, `paradigms`, `seeds`, `variants` | The grid of runs (`algorithms` is `["ppo"]`); a variant is an arm: it overwrites the base file's settings ([Config](../config/reference.md#variants)) | |
| `budget`, `eval_points`, `eval_episodes` | Environment steps per run (one number or one per algorithm) and the evaluations during training | |
| `training` | Per algorithm (`ppo`), RLlib's training settings: the project's defaults with the spec's overrides on top. Any other key of RLlib's PPO `training()` can be added (e.g. `vf_loss_coeff`) and has RLlib's default until it is; `run.json` records every PPO setting with the value it ran with (`settings_effective`) | [rl_defaults.py](../../core/rl_defaults.py) `SETTINGS` |
| `model` | The network, the same for every paradigm | [rl_defaults.py](../../core/rl_defaults.py) `NETWORK` |
| `max_parallel`, `torch_threads`, `num_env_runners`, `ray_thread_caps`, `resources` | How runs share this PC or a cluster node ([Resources and parallelism](resources.md)) | [spec.py](../../core/runner/spec.py) `RESOURCE_DEFAULTS` |
| `test` | Changes to the [test profile](resources.md#full-and-test-profiles) | |

What is not in the experiment: the market itself (network, participants, market
and DSO rules) is the scenario's, edited in the Studio's other pages and saved in
[config/scenarios/](../../config/scenarios/); the agents' observation and action design is
[MarketEnv](../../core/env/market_env.py)'s ([Action](../full-cycle/environment/action.md), [Observation](../full-cycle/environment/observation.md)).

## Commands

From the `marlem-v2` root, in the `marlem` environment:

```powershell
python -m core.runner check config/experiments/smoke.json --target taltech
python -m core.runner start config/experiments/smoke.json --profile test --target taltech
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
`config/scenarios/` later does not change an experiment already started.

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
    print(target.check("config/experiments/smoke.json"))
    # name = target.start("config/experiments/smoke.json", profile="test")
    # A changed copy, as the Studio's Experiments page makes it; a taken name is dated:
    # experiment = Experiment.load("config/experiments/smoke.json")
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

The *Experiments* page takes a spec from `config/experiments/` as a **template** and shows its
JSON in an editor: change anything. The editor writes out every setting, each at
its default where the template gives none ([The experiment
file](#the-experiment-file)), so all that can be set is in front of you. Every
edit is checked as a start would check it,
and the page shows the runs it makes, or what is wrong. The template file is
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

## Training one run from Python

In Python, from the `marlem-v2` root (the RL code is imported as `core.rl`, the
market as `core.*`):

```python
from core.env import MarketEnv, net_position_policy, zero_policy
from core.rl import Run, evaluation, load_policy, train

config = {"scenario": "config/scenarios/validate_market.json",
          "days": [f"2016-06-{d:02d}" for d in range(1, 31)]}
record = train(Run("ppo", "ctde", MarketEnv, config, budget=24_000, eval_every=4_800))

held_out = {"scenario": config["scenario"], "days": [f"2016-07-{d:02d}" for d in range(1, 15)]}
env = MarketEnv(held_out)
policies = {"trained": load_policy(record["out_dir"])[0],
            "zero": zero_policy(env), "net_position": net_position_policy(env)}
days = held_out["days"]  # every test day once
found = evaluation(MarketEnv, held_out, policies, seeds=list(range(2000, 2014)),
                   options=[{"day": d} for d in days])
found.summary, found.episodes, found.agents  # means; per day; per day and participant
```

Each run writes `run.json`, `metrics.csv`, `evaluation.csv` (with its per-episode
and per-agent tables) and a checkpoint to `runs/` (not in git).

For more than one run, or one that should outlive the terminal, describe the runs
in `config/experiments/<name>.json` (algorithms × paradigms × seeds × variants,
budget, train days and test periods; every setting is in [Config](../config/reference.md))
and use the runner. It keeps everything in files under `runs/<name>/`, so the CLI,
Python (`core.runner.targets`) and the Studio see the same state. Each run ends
with `heldout.csv` (trained policy and baselines on the test periods), with per-day
and per-participant tables next to it; the Studio's Results page and
`notebooks/runner/results.ipynb` compare runs from them. The `test` profile is the
smallest version of the same experiment, to check the pipeline before spending
cluster time. The workflow, the readiness check and restarting are in
[Training experiments](experiments.md), what each setting controls in
[Resources and parallelism](resources.md).

Each run writes `run.json`, `metrics.csv`, `evaluation.csv` (with its per-episode
and per-agent tables) and a checkpoint to `runs/` (not in git).

For more than one run, or one that should outlive the terminal, use the runner as
described above.

**What the Studio's Experiments page adds.**
The Studio's Experiments page edits an experiment's JSON, with fields for the
  paradigms, seeds, budget, PPO settings (learning rate, batch, minibatch, epochs,
  entropy, clip, γ), environment runners, runs in parallel, torch threads and SLURM
  resources; each rewrites its setting in the JSON editor, which stays what starts.

**What the Results page shows.**
The Results page shows every test day step by step: each participant's side, order,
  named partner, whether the choice was mutual and its stage-1 energy, and the step's
  stage-1 volume next to the P2P and DSO volumes.

**The cluster's checkout.**
The cluster's checkout is `~/marlem-v2` (branch `marlem-v2`), with its own `runs/`;
  on this PC the synced results are in `runs/@taltech/`. Account and cluster settings
  are in `.env`.

## Files

Everything is in `runs/<experiment>/`, so any terminal and the Studio see the same
state:

| File | What |
|---|---|
| `experiment.json` | The spec as started, with its base scenario and all its variants (a later start must match it) |
| `scenario.json` | The base scenario (a copy of the one in `experiment.json`) |
| `worker.json`, `worker.log` | This PC: the worker that keeps `max_parallel` runs going |
| `slurm.json`, `slurm/` | Cluster: the array and submitit's scripts and task logs |
| `<run>/experiment.json` | The run's arm: the spec with its variant applied |
| `<run>/scenario.json` | The arm's scenario, the file the run reads |
| `<run>/status.json` | The run's state, times, error, process or SLURM task |
| `<run>/run.json` | Training settings, versions, commit and outcome |
| `<run>/metrics.csv` | Training iterations: environment steps, training return, learner metrics per module and their mean, min and max over the modules (`modules/<metric>_mean`, ...), timing |
| `<run>/evaluation.csv` | Evaluations during training: one row per evaluation point and policy (means) |
| `<run>/evaluation_agents.csv`, `evaluation_episodes.csv` | The same evaluations per episode and participant, and per episode (with its day) |
| `<run>/heldout.csv` | The held-out evaluation: one row per policy (means over the test days) |
| `<run>/heldout_episodes.csv` | One row per policy and test day: team return, P2P and DSO energy, trade losses, fees, the power flow's grid import, export, losses, violations and non-converged steps |
| `<run>/heldout_agents.csv` | One row per policy, test day and participant: return, profit, bill, bought, sold, deferred demand and supply |
| `<run>/heldout_steps.csv`, `heldout_agent_steps.csv` | Every test day step by step, for every policy: market, grid and tariffs per step, and each participant's energy, order, partner, battery and reward parts |
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

To keep experiments apart, move their folders by hand into folders of your own
(`runs/@taltech/test/<experiment>`, or `runs/test/<experiment>` on this PC; at any
depth). The Results and RL probes pages read them as `test/<experiment>`, and their
run table narrows by target, then folder, then experiment. Every folder level is an
option, and a folder includes those under it. The runner does not see
inside these folders, and the cluster keeps its copy at the top level: **Sync
results** on such an experiment brings a second copy back to the mirror's top level.

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
4. **Each run starts its own Ray instance**, of about 230–300 threads with the
   runner's thread caps (`ray_thread_caps`, on by default; 540–760 without), and
   TalTech allows 4096 threads per user per node. SLURM packs runs onto one node
   by CPU and does not know this limit: with `num_env_runners: 3`, more than 12
   runs on a node (5 without the caps) crash at start. Size `max_parallel` and
   `resources.cpus` from [how many runs fit](resources.md#how-many-runs-fit-at-once).
5. **No retries over SSH.** A failed call raises its error and the next call
   reconnects; after a lost answer to `start`, look at `status` before starting
   again.
