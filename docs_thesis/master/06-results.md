# 6. Runs and results

[Previous: learning](05-learning.md) · [Master overview](README.md)

## Why this stage exists

A run should preserve what was executed, its progress and its evidence. Separating
worker execution from the UI keeps long jobs out of the interface process and
makes saved results inspectable later.

## What goes in and comes out

The worker's input is a run directory containing resolved configuration and a
manifest. It produces state transitions, logs and whatever metrics its runner
actually records. The intended research outputs include both learning returns
and physical/economic measures such as unmet demand and cost.

| Artifact | Meaning in the storage implementation |
|---|---|
| `resolved.json` | Settings fixed for this run |
| `manifest.json` | Identity/provenance and selected run cell |
| `status.json` | Current lifecycle/progress information |
| `metrics/<name>.csv` | Rows appended by a caller using the store |

The presence of a folder or a completed status does not by itself prove that a
market episode was executed. In particular, `NoopRunner` completes a smoke job
that reports progress without training a policy.

## Where it happens

| Function / class | Actual responsibility |
|---|---|
| [ExperimentStore.create_run](../../src_thesis/platform/experiments/store/filesystem.py) | Creates run storage and writes its initial records |
| [process.run_one](../../src_thesis/platform/experiments/worker/process.py) | Reads configuration/manifest, checks the hash, handles cancellation, selects a runner and records terminal state |
| [select_runner / NoopRunner](../../src_thesis/platform/experiments/worker/runner.py) | Chooses job implementation; the smoke runner reports synthetic progress |
| [EpisodeRecorder](../../src_thesis/platform/experiments/store/recorder.py) | Records supplied episode/step data according to record mode |
| [ExperimentService](../../src_thesis/platform/services/experiment_service.py) | Application-facing run operations; currently sample responses |
| [ResultService](../../src_thesis/platform/services/result_service.py) | Application-facing results; currently generated samples |

An `EpisodeRecorder` must be fed real step records by a runner. Defining the
recorder does not automatically connect it to `LocalEnergyMarket.step`.

## Who calls it

The worker module entry point delegates to `process.main`; `run_one` invokes
`(runner or select_runner(manifest.cell)).run(ctx)`.

The Studio accesses application services. The shared page shell calls
`ExperimentService.list_runs` for its running-count chip. The intended
`ExperimentService.start` → worker pool handoff is absent: `start` currently
returns without launching work. `create_runs` derives IDs from expanded cells
but does not create the corresponding run folders.

## Current status

The store/worker lifecycle infrastructure has implementation, and the no-op runner
has a body. Baseline and training runners are stubs. `ExperimentService` and
`ResultService` declare `SAMPLE_DATA = True`; the latter synthesizes summaries,
learning curves and replay data rather than reading completed training runs.

Consequently, the current Studio's progress, success states and result charts
must not be used as evidence of learning or physical validity. Ray Tune output
from a direct trainer invocation is a separate output path until integration is
implemented. See [experiment-layer design](../thesis/architecture/03-experiment-layer.md)
for the intended lifecycle and artifact contract.

## What to understand before the next implementation change

You can now locate the five major handoffs: file → participant mapping → factory
→ environment step → learning/results. The factory and application execution
handoffs are the main gaps in this inspected path. A proposed change should name
which handoff it completes and show evidence for that behaviour.

**Return:** [Master overview](README.md), or use the **API Reference** tab for
detailed signatures and expandable source code. The
[validation plan](../thesis/validation/plan.md) remains the place for work order
and acceptance criteria.
