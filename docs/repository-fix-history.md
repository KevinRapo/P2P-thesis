# Repository Fix History

This document records defects, portability problems, stale examples, and reproducibility gaps found while bringing the original MARLEM repository into a runnable and scientifically reviewable state.

It is intentionally broader than an environment migration diary. Entries describe what was present in the original repository, how the issue was exposed, what changed, how the change was checked, and what remains unresolved. The current baseline is the repository `HEAD`; working-tree changes are treated as proposed fixes until they are committed.

For the larger model-validation backlog, see [validation-fix-plan.md](validation-fix-plan.md). That document defines the planned correctness work. This history records the issues actually encountered and the changes made over time.

## Status convention

- `Open`: confirmed or suspected issue with no completed fix.
- `Investigating`: evidence exists, but the cause or correct fix still needs validation.
- `Fixed in working tree`: a correction exists locally but has not yet been committed as the new baseline.
- `Validated`: the correction has passed its stated check.
- `Superseded`: retained for history but replaced by a later decision.

## Current working-tree inventory

As of 2026-08-14, the changes relative to the original repository baseline are concentrated in:

- `.gitignore`: generated training and inference artifacts are excluded.
- `examples/getting_started.ipynb`: portable paths, real input data, Windows/Ray setup, environment smoke testing, checkpoint handoff, and inference workflow.
- `src/environment/train.py`: evaluation-duration validation and reliable Ray shutdown.
- `pyproject.toml` and `uv.lock`: reproducible UV-managed Python environment.
- `examples/zero_to_hero.ipynb`: currently contains execution evidence of unresolved example failures; its source workflow has not yet been repaired.

## 2026-08-05 — Environment and test baseline

### RF-001 — No project-native locked Python environment

- **Status:** `Fixed in working tree`
- **Category:** Reproducibility and portability
- **Original issue:** The repository provided `environment.yml`, but no `pyproject.toml` or cross-platform lockfile. The Conda file fixed Python at 3.12.10 while the active Miniconda base interpreter was 3.12.3.
- **Observed impact:** Recreating the exact Python and package set depended on manually following the Conda definition. PyTorch CUDA wheel selection was not explicitly represented outside the environment setup.
- **Change:** Added `pyproject.toml`, pinned Python to 3.12.10, migrated the package requirements, separated development and notebook groups, selected the PyTorch CUDA 12.6 index, and generated `uv.lock`. The original `environment.yml` remains as a reference and Conda fallback.
- **Validation:** `uv sync` created the project `.venv`; Python 3.12.10, Torch 2.6.0+cu126, Ray 2.51.1, and CUDA availability were confirmed.
- **Follow-up:** Decide whether `environment.yml` remains supported or becomes an explicitly documented legacy setup after the UV workflow is committed.

### RF-002 — Test suite and implementation have drifted apart

- **Status:** `Open`
- **Category:** Testing and validation
- **Original issue:** Several files under `tests/` use function parameters such as `path`, `algo`, and `mode` as though pytest will supply them, but no fixtures or parametrization define those values. Other tests call signatures that no longer match the source implementation.
- **Observed impact:** The original suite cannot serve as a clean regression gate.
- **Evidence:** `uv run python -m pytest` collected 35 tests: 15 passed, 3 failed, 17 errored, and 6 warnings. The failures included stale calls involving `get_kpis`, `DERProfileHandler`, and `RewardHandler`.
- **Follow-up:** Repair collection and fixture structure first, then determine which failures represent stale tests and which expose source defects. Track the deeper corrections in `validation-fix-plan.md`.

## 2026-08-14 — Getting-started workflow audit

### RF-003 — The getting-started notebook was tied to the author's machine

- **Status:** `Validated`
- **Category:** Portability
- **Original issue:** `examples/getting_started.ipynb` contained absolute macOS paths under `/Users/nasalazar/...` for storage, experiments, and checkpoints. Its import setup assumed a specific working directory through `sys.path.append('../')`.
- **Observed impact:** A fresh clone on Windows could not use the documented paths and could import the project only from a narrow launch location.
- **Change:** Resolve `PROJECT_ROOT` from either the repository root or `examples/`, derive all paths from it, and reject unsupported launch locations with a clear error.
- **Validation:** Notebook JSON and code-cell syntax passed; the setup section executed successfully from the repository root.

### RF-004 — Bundled input data was not connected to the introductory example

- **Status:** `Validated`
- **Category:** Example correctness and reproducibility
- **Original issue:** The notebook passed `None` to the DER and DSO profile handlers, causing generated profiles even though the repository includes generation, demand, feed-in-tariff, and utility-price CSV files.
- **Observed impact:** The introductory run did not exercise the repository's bundled input-data workflow and was harder to reproduce from known data.
- **Change:** Point the example to the local 60-minute files under `data/generation`, `data/demand`, and `data/prices`.
- **Validation:** All four files were found, the handlers initialized, and the environment reset and stepped successfully.

### RF-005 — Training output, checkpoint selection, and inference were disconnected

- **Status:** `Fixed in working tree`
- **Category:** Example workflow
- **Original issue:** Training was commented out, while inference referenced an author-specific checkpoint that could not exist in a fresh clone. The notebook did not transfer a checkpoint produced by training into inference.
- **Observed impact:** Running inference either failed on a foreign path or required the user to manually discover and copy a Ray checkpoint.
- **Change:** Enable the short training cell, store experiments under `storage/TRAIN`, copy the selected checkpoint to `storage/INFERENCE/selected_checkpoint`, assign it to `CHECKPOINT_PATH_INFERENCE`, and guard inference when no checkpoint exists.
- **Validation:** A checkpoint was created, copied, restored by `RLInference`, and used for three complete inference episodes.
- **Caveat:** RF-011 shows that the current checkpoint is not genuinely selected by evaluation performance yet.

### RF-006 — Environment smoke test stepped before an explicit reset

- **Status:** `Validated`
- **Category:** Example correctness
- **Original issue:** The random-action smoke-test cell assumed the trainer's environment was already in a valid episode state.
- **Observed impact:** Cell behavior depended on constructor side effects and prior execution order.
- **Change:** Explicitly call `trainer.env.reset(seed=SEED)` before the three random steps.
- **Validation:** Three steps completed and returned rewards.

### RF-007 — Positive integer evaluation durations were rejected

- **Status:** `Validated`
- **Category:** Source-code defect
- **Original issue:** `RLTrainer._check_init` used incorrect boolean logic and raised an error for valid positive integer values such as `evaluation_duration=3`.
- **Observed impact:** The documented notebook configuration could not construct `RLTrainer`.
- **Change:** Accept either the string `"auto"` or an integer greater than zero.
- **Validation:** `evaluation_duration=3` passed a targeted initialization check and the notebook constructed the trainer.

### RF-008 — Failed training could leave Ray running

- **Status:** `Validated`
- **Category:** Resource lifecycle
- **Original issue:** `ray.shutdown()` ran only after successful training or experiment restoration.
- **Observed impact:** Exceptions could leave Ray processes and memory allocations alive, affecting retries in the same notebook session.
- **Change:** Wrap training and restoration result handling in `try/finally` and shut Ray down whenever it remains initialized.
- **Validation:** Source compilation passed, and subsequent failed and successful notebook attempts could restart Ray after a kernel restart.

### RF-009 — Ray workers could not import the repository's `src` package

- **Status:** `Validated`
- **Category:** Packaging and worker portability
- **Original issue:** The project is configured with `package = false` and runs directly from the source tree. Adding the repository only to the notebook kernel's `sys.path` did not make `src` importable inside Ray worker processes.
- **Observed impact:** The first training trial died with `ModuleNotFoundError: No module named 'src'`.
- **Change:** Export the repository root through `PYTHONPATH` in the notebook before Ray starts.
- **Validation:** A direct Ray actor probe imported `src`, and the later SAC trial constructed its environment and completed.
- **Follow-up:** Consider packaging MARLEM properly so worker imports do not depend on notebook-managed `PYTHONPATH`.

### RF-010 — Windows PyTorch build could not use Ray's requested libuv store

- **Status:** `Validated`
- **Category:** Windows compatibility
- **Original issue:** Ray's Torch learner initialization requested the libuv TCPStore backend, but the installed Windows PyTorch 2.6.0+cu126 wheel was built without libuv support.
- **Observed impact:** SAC actor creation failed with `RuntimeError: use_libuv was requested but PyTorch was built without libuv support`.
- **Change:** Set `USE_LIBUV=0` before Ray creates Torch worker processes, selecting PyTorch's legacy TCPStore backend.
- **Validation:** The next SAC run completed all three configured iterations and created checkpoints.
- **Follow-up:** Move the compatibility setting to a documented central startup location if Windows remains a supported platform.

### RF-011 — Evaluation duration uses the wrong type and produces no evaluation episodes

- **Status:** `Open`
- **Category:** Experimental validity
- **Original issue:** `RLTrainer` passes `StorageUnit.EPISODES` from the replay-buffer API as `evaluation_duration_unit`. Ray's algorithm configuration expects the string `"episodes"`.
- **Observed impact:** The saved Ray configuration contains `"StorageUnit.EPISODES"`. Each evaluation sampled only three timesteps, completed zero episodes, and produced no evaluation-return metric. The notebook's “best evaluation checkpoint” therefore was not selected using actual evaluation performance.
- **Evidence:** The successful run logged `evaluation/env_runners/num_episodes = 0`, emitted an empty-evaluation warning, and had no evaluation return fields.
- **Required fix:** Pass `evaluation_duration_unit="episodes"`, add a regression assertion that evaluation completes the requested number of episodes, and fail checkpoint selection when the requested metric is absent.

### RF-012 — The SAC quick run ends before learning begins

- **Status:** `Open`
- **Category:** Example semantics and experimental validity
- **Original issue:** The notebook labels its three-iteration SAC run as training, but Ray's SAC configuration waits for 1,500 sampled environment steps before learner updates begin.
- **Observed impact:** The run stopped after 483 sampled steps. Both checkpoint model-state files had identical hashes, confirming that no policy weights changed. Inference therefore evaluated the initialized policy rather than a learned policy.
- **Evidence:** Training collected 21 episodes; mean reported returns were 135.69, 188.73, and 171.44, but there were no learner-update metrics. Deterministic inference returned -125.3869 in all three episodes.
- **Required fix:** Clearly distinguish a pipeline smoke test from a learning run. For a learning demonstration, run beyond SAC warm-up and enough additional updates to assess a trend; for a very short test, explicitly lower the warm-up only as a test configuration.

### RF-013 — Inference metrics are calculated but not surfaced or persisted

- **Status:** `Open`
- **Category:** Result reporting
- **Original issue:** `RLInference.inference()` returns a metrics dictionary, but the notebook calls it inside an `if` block without assigning, displaying, or saving the return value.
- **Observed impact:** Episode rewards appear in console output, but aggregate reward, episode-length, market, grid, and DSO metrics are not available as a named notebook result or artifact.
- **Required fix:** Assign the return value to `inference_metrics`, display a compact summary, and save a machine-readable result with the run configuration and checkpoint identifier.

### RF-014 — SAC evaluation emitted action-scaling overflows

- **Status:** `Investigating`
- **Category:** Numerical stability
- **Original issue:** Ray emitted `overflow encountered in multiply` while mapping SAC outputs into the environment action bounds.
- **Observed impact:** Extremely large pre-clipped actions may hide an initialization, distribution, normalization, or custom-module problem. Results should not be trusted until the executed actions are shown to be finite and consistent with the policy distribution.
- **Required investigation:** Record raw model outputs, transformed actions, and final environment actions; assert finite values and valid bounds; inspect the custom SAC module's action distribution and squashing behavior.

### RF-015 — Generated experiment output was visible as repository content

- **Status:** `Validated`
- **Category:** Repository hygiene
- **Original issue:** Ray experiments, checkpoints, inference copies, figures, and serialized environment configurations were written beneath `storage/`, but that directory was not ignored.
- **Observed impact:** Running the example immediately polluted `git status` with large generated artifacts.
- **Change:** Add `storage/` to `.gitignore`.
- **Validation:** Git's ignore check resolves generated training files through the new rule.

### RF-016 — `zero_to_hero.ipynb` is stale relative to the current source API

- **Status:** `Open`
- **Category:** Documentation and example correctness
- **Original issue:** The example's import setup can fail to locate `src`, and its minimal `env_config` omits required fields such as `agents`.
- **Observed impact:** Executing the notebook produced `No module named 'src'`, followed by `ValueError: The <env_config> is missing the required key: <key = agents>` once imports were available.
- **Evidence:** The current notebook diff contains these saved execution failures; no source correction has been made yet.
- **Required fix:** Rebuild the example against the current environment-construction API, reuse the portable project-root setup, and add an execution check that runs the notebook from a clean kernel.

## Adding future entries

Add one entry whenever an issue is confirmed, fixed, invalidated, or materially reclassified. Keep the original issue description even after fixing it so the repository's repair history remains auditable.

Use this template:

```markdown
### RF-NNN — Short title

- **Status:** `Open`
- **Category:** Area affected
- **Original issue:** What was present in the baseline repository.
- **Observed impact:** How it failed or why it matters.
- **Evidence:** Test, traceback, result artifact, or source location.
- **Change:** What was changed, if anything.
- **Validation:** How the correction was checked.
- **Follow-up:** Remaining work or decision.
```
