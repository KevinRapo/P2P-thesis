# Training experiments

[HPC overview](../hpc.md) · [Resources and parallelism](resources.md)

The runner is the shared execution API for CLI, Python and the Studio. Its
implementation is [core/runner/](../../core/runner/); generated signatures and
docstrings are in the [runner API](../api/runner/index.md).

## Experiment, profile and target

| Concept | Definition | Location |
|---|---|---|
| Experiment | Algorithms × paradigms × seeds × variants, budgets, scenario and training settings | [experiments/](../../experiments/) |
| Profile | `full` uses the spec; `test` derives a smaller workload named `<name>--test` | `Experiment.with_profile` in [spec.py](../../core/runner/spec.py) |
| Target | This PC (`local`) or a Slurm cluster (`taltech`) | [hpc/targets.toml](../../hpc/targets.toml) |

The active cluster checkout is `~/marlem-v1`, on branch `marlem-v1`. The previous
Slurm worktree is a reference copy. Run commands below from the local `marlem-v1`
root in the `marlem` environment. The remote environment must have the same code
and the dependencies needed by the chosen environment and algorithm.

## Experiments on the cluster

```powershell
python -m core.runner check experiments/smoke.json --target taltech
python -m core.runner start experiments/smoke.json --profile test --target taltech
python -m core.runner status smoke--test --target taltech
python -m core.runner sync smoke--test --target taltech
```

To stop the experiment, or just a named run:

```powershell
python -m core.runner stop smoke--test --target taltech
python -m core.runner stop smoke--test ppo_dtde_s0 --target taltech
```

Use the run name printed by `status`; names depend on the spec. To run locally,
omit `--target taltech` or use `--target local`. To train the full experiment,
choose `--profile full` (the default); its folder is `smoke`, not `smoke--test`.

`check` returns `{target, ok, problems, local_commit, cluster_commit, active}`.
From this PC, readiness checks the remote command, code commits, remote dirty
checkout and, when a spec is supplied, tracked/unmodified spec and scenario.
`start` calls the same check. `active` lists queued/running experiments as a
reminder; it is not a lock. `check --json` exits 1 when not ready; command errors
are returned as JSON errors when `--json` is requested. This JSON protocol is also
how the remote target talks to the cluster CLI.

Local readiness is lightweight, not a dependency or memory stress test. On the
cluster itself the Slurm target submits directly; the cross-machine Git checks
belong to the remote target used from this PC.

## Python and Studio

```python
from core.runner import targets

target = targets.get("taltech")
try:
    report = target.check("experiments/smoke.json")
    print(report)
    # Explicit actions, when ready:
    # name = target.start("experiments/smoke.json", profile="test")
    # print(target.runs(name))
    # folder = target.sync(name)
finally:
    target.close()
```

[targets_demo.ipynb](../../notebooks/runner/targets_demo.ipynb) walks through the
workflow. `Target.overview()` is the common read path. The Studio adapter delegates
to these same operations; it does not implement a second scheduler.

Start Studio with `python run_studio.py` and open **Runs**. Each target has a tab.
The Start dialog lists experiment specs and full/test profiles; cluster checks
use the selected spec. Start stays disabled while checks report problems and
while a start request is in flight. Local data refreshes every two seconds and
cluster data every 20 seconds while the tab is shown. Failed reads retain the
last view and timestamp with a persistent error. Action failures are notifications.
**Sync results** is manual; viewing the tab does not copy result files.

## Files, status and restart

| File | Owner and purpose |
|---|---|
| `experiment.json` | Normalized spec saved before starting runs |
| `worker.json`, `worker.log` | Local supervisor identity and launch history |
| `slurm.json`, `slurm/` | Cluster array/task IDs and submitit scripts, pickles and logs |
| `<run>/status.json` | Runner lifecycle, timing, errors, process identity or Slurm job ID |
| `<run>/run.json` | Training configuration, versions, commit and training outcome |
| `<run>/metrics.csv` | Training iterations, sampled steps and learner metrics |
| `<run>/evaluation.csv` | Evaluation on the configured training environment |
| `<run>/heldout.csv` | Final market evaluation on held-out days and seeds |
| `<run>/checkpoint/` | Checkpoint saved at the end of training |
| `<run>/log.txt` | Local job stdout/stderr; cluster output is under `slurm/` |

`run.json` describes training; `status.json` describes the encompassing runner job,
which also performs held-out evaluation. Their completion times can differ.

Starting the same experiment again keeps completed runs and restarts unfinished
runs that are eligible to restart. Failed/stopped/lost runs train from scratch;
this is **not checkpoint resume**. Active workers/Slurm tasks prevent duplicate
restarts of the same experiment. A changed normalized spec is refused before
saved files or states are altered. Use a new experiment name for changed specs,
code or scenario contents; code/scenario-content changes are not automatically
detected by the saved-spec comparison.

`sync` downloads to a temporary sibling folder and replaces
`runs/@taltech/<experiment>` only when the copy succeeds. Stale mirror files are
removed, so do not keep hand-edited analysis in that directory. Checkpoints and
`slurm/` are excluded. Download failure leaves the previous mirror intact;
replacement failure attempts to restore it. For policy loading, copy the
checkpoint separately or load it on the cluster.

## Working rules and current limits

- Keep the cluster checkout unchanged while its experiments are queued or running.
  Tasks read that checkout on start; there is no immutable per-run code snapshot.
  `git shipc` and `git pushc` also pull on the cluster, so wait before using them.
- Submit one operation at a time across CLI and Studio. The Start button blocks
  repeated UI requests, but there is no cross-process submission lock.
- Keep the default four-CPU request initially. Each run normally starts its own
  Ray instance; the dated thread-limit observations are in [performance](performance.md).
  Increasing CPU reservations does not create environment runners.
- The runner exposes CPU/memory/time requests, not multi-node learning or GPU
  requests. [Resources](resources.md) lists what the JSON actually supports.
- An SSH failure is surfaced without automatically replaying the operation. The
  next call can reconnect. If a submission response is lost, inspect status before
  deciding whether another submission is needed.

## Existing execution evidence

The following saved artifacts were inspected on 17 October 2026 in the former
`marlem-slurm/runs/` worktree. They are ignored local results, not published data
or new tests of the migrated checkout:

| Workload | Evidence |
|---|---|
| Local `market_3x3--test` | All nine runs completed; records show zero remote environment runners and zero GPUs |
| TalTech `market_3x3--test` | Array `1042752`, all nine task status records completed |
| TalTech `sac_alpha--test` | Array `1042740`: two runs completed with learner metrics beyond warm-up; one task recorded stopped |

These establish short pipeline executions, not full-budget learning comparisons
or a complete manual Studio acceptance test. [tests/runner/](../../tests/runner/)
contains automated checks of the spec, registry, Slurm commands, remote transport,
target interface and Studio adapter; inspecting those tests is not a claim that
they were rerun during this documentation refresh. Earlier research results remain
in [the implementation page](../v1.md#5-validation), with their original budgets.
