# Case studies for decentralized multi-agent reinforcement learning in local energy markets

This directory contains seven Jupyter notebooks — `case1_market_mechanisms.ipynb` through `case7_scalability_analysis.ipynb` — designed to systematically examine the main research question of this doctoral research project, plus `case_studies_index.ipynb` as a navigation index. These are Jupyter notebooks, not a Python package: there is no `cases/` module to import from.

## Research question

> **Main:** How does implicit cooperation, enabled by MARL, improve the management of DERs to maximize their energy use while ensuring the balance between supply and demand in LEMs?

## Running the notebooks

Use the environment described in the root `environment.yml`, select its kernel, and run all cells from a fresh kernel.

**Cases 1–5** default to a zero-intelligence (random-policy) baseline via a `USE_ZERO_INTELLIGENCE` toggle in each notebook's configuration cell — this steps the real environment with random valid actions rather than training, so it runs in minutes rather than hours and matches the zero-intelligence baseline the papers' own published results use. Set `USE_ZERO_INTELLIGENCE = False` to switch to real MARL training instead (`TRAINING_EPISODES`, `ALGORITHM`, `TRAINING_MODE` are configured in the same cell) — see `docs/thesis/training-benchmarks.md` before doing this, since real training at the notebooks' committed iteration counts can take many hours depending on population size and algorithm.

**Case 6** (`case6_implicit_cooperation.ipynb`) is the core research-validation notebook and defaults to the paper's 10,000-iteration budget over all nine CTCE/CTDE/DTDE × PPO/APPO/SAC variants. It uses one local Tune sample by default so the restored protocol remains executable; the paper-scale PBT population is explicitly opt-in. This full matrix is not viable at typical desktop scale without a multi-day budget, so reduce `TRAINING_EPISODES`/`TUNE_SAMPLES` for a smoke check first. Checkpoint/restore/inference paths are derived dynamically from the run that just completed (`results.experiment_path`, `trainer.get_best_checkpoint(results)`), not hardcoded.

**Case 7** (`case7_scalability_analysis.ipynb`) sweeps agent population × training mode × algorithm (54 combinations by default via `ScalabilityConfig`) — also not viable at full scale without a large time budget; reduce the population/mode/algorithm lists for a quick check.

## Validation methodology

**Do not use `jupyter nbconvert --execute` to validate notebooks on this machine.** It dispatches to a `jupyter-nbconvert` executable resolved via PATH, which on this machine resolves to a broken environment and silently reports success (exit code 0) even when it crashed at import. All notebooks in this repository were validated with a direct in-process harness instead:

```python
import nbformat
from nbclient import NotebookClient

nb = nbformat.read("notebooks/case1_market_mechanisms.ipynb", as_version=4)
client = NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": "notebooks"}})
client.execute()  # raises CellExecutionError on any real failure
```

Cases 1–5 pass this way end-to-end. Cases 6–7 have been validated through temporary reduced-scale copies of their training-heavy cells, since running them at the committed 10,000-iteration/54-combination scale is a multi-hour-to-multi-day undertaking — see `docs/thesis/validation-fix-plan.md`.

## Related material

- `examples/getting_started.ipynb` — a step-by-step walkthrough of the `RLTrainer`/`RLInference` API on a small 3-agent scenario. It has a `TRAINING` toggle (default `True`, 3 real training iterations) that gates the training/restore/checkpoint-continuation/inference sections; checkpoint paths are derived dynamically from the run, not hardcoded.
- `examples/zero_to_hero.ipynb` — executable educational walkthrough; its basic, full-day, and quickstart examples now construct the explicit component graph required by the restored environment.
- `docs/thesis/validation-fix-plan.md` — the defect-by-defect audit and fix record for this restoration, including the paper correspondence for each fix and the known gaps not yet addressed.
- `docs/thesis/training-benchmarks.md` — measured real-training wall-clock costs on this hardware; check before running any notebook with `USE_ZERO_INTELLIGENCE = False` or `TRAINING = True`.
- `docs/tests.md` — the automated test suite; `pytest -q` is the fast, code-level counterpart to running these notebooks.
