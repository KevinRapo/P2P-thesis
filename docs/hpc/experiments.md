# Training experiments

An experiment is defined once, as a spec in [experiments/](../../experiments/), and
runs on a target; the CLI, Python and the Studio's Runs page call the same runner,
[core/runner/](../../core/runner/) ([API](../api/runner/index.md)).

| Term | Meaning |
|---|---|
| Experiment | Algorithms × paradigms × seeds × variants, with budgets, scenario, train and test days, training settings and cluster resources ([spec.py](../../core/runner/spec.py)) |
| Profile | `full`: the spec as written. `test`: its smallest version, named `<name>--test` ([what it keeps](resources.md#full-and-test-profiles)) |
| Target | `local` (this PC: a detached worker) or `taltech` (one SLURM job array, a task per run, via submitit), from [hpc/targets.toml](../../hpc/targets.toml) with your account and host from `.env` ([setup](setup.md#this-machines-settings-env)) |

Every run ends with a held-out evaluation (`heldout.csv`: the trained policy and
the baselines on the test days).

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
checkout has changes, the spec or its scenario is not committed), with both
commits and the experiments queued or running there. `start` runs the same check
and refuses with its problems. Exit code 1 when not ready.

**`sync`** copies the experiment's results to `runs/@taltech/<experiment>`,
without checkpoints and `slurm/`. The copy goes to a temporary folder that replaces
the old one only when complete, so a failed download keeps the previous copy;
files removed on the cluster disappear here too. Nothing is copied unless asked.

**Restarting:** `start` on an existing experiment keeps its completed runs and
starts failed, stopped and lost ones again, **from scratch** (there is no
checkpoint resume). A changed spec is refused: use a new name.

## Python and the Studio

```python
from core.runner import targets

target = targets.get("taltech")
try:
    print(target.check("experiments/smoke.json"))
    # name = target.start("experiments/smoke.json", profile="test")
    # print(target.runs(name))
    # folder = target.sync(name)
finally:
    target.close()
```

[targets_demo.ipynb](../../notebooks/runner/targets_demo.ipynb) walks through it.

The Studio (`python run_studio.py`, page **Runs**) has a tab per target. This PC is
read every 2 s, the cluster every 20 s while its tab is shown. The cluster's tab
shows the `check` line with a Check button, and each experiment has a *Sync
results* button. *Start experiment* picks a spec, the profile and the target; for
the cluster it checks the spec and keeps Start disabled while there are problems.
When the cluster cannot be read, the page keeps the last data with its time.

## Files

Everything is in `runs/<experiment>/`, so any terminal and the Studio see the same
state:

| File | What |
|---|---|
| `experiment.json` | The spec as started (a later start must match it) |
| `worker.json`, `worker.log` | This PC: the worker that keeps `max_parallel` runs going |
| `slurm.json`, `slurm/` | Cluster: the array and submitit's scripts and task logs |
| `<run>/status.json` | The run's state, times, error, process or SLURM task |
| `<run>/run.json` | Training settings, versions, commit and outcome |
| `<run>/metrics.csv`, `evaluation.csv` | Training iterations; evaluations during training |
| `<run>/heldout.csv` | The held-out evaluation |
| `<run>/checkpoint/` | The policy at the end of training |
| `<run>/log.txt` | This PC: the job's output (on the cluster it is in `slurm/`) |

`run.json` covers training; `status.json` the whole job, held-out evaluation
included.

## Limits

1. **Leave the cluster's checkout alone while its experiments are queued or
   running** (`git shipc`, `git pull`, edits): each task reads the checkout when it
   starts, so a queued task would run the newer code. `check` lists them.
2. **Changes to code or to a scenario file are not detected**, only changes to the
   spec: use a new experiment name for them too.
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
