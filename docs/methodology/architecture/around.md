# Around the code

Data and settings, notebooks, tests, and the files that run and build everything.

## config/: settings and data

| Folder | What it holds |
|---|---|
| [`config/scenarios/`](../../../config/scenarios/) | Saved scenarios, opened from the Studio's header or named by an experiment ([Config](../../using/running/config.md)) |
| [`config/experiments/`](../../../config/experiments/) | Experiments, one file each; the thesis's are in [Thesis experiments](../../experiments/thesis/index.md) |
| [`config/data/`](../../../config/data/) | Price files: synthetic days and German 2024 prices, with the script that builds them ([Prices](../../using/data/prices.md)) |

## notebooks/

The core without the Studio: each imports `core/` only and runs in the `marlem`
environment.

| Folder | What the notebooks do |
|---|---|
| [`notebooks/market/`](../../../notebooks/market/) | Validate the market in three levels (formulas, one step, the test days), time it, compare the grid methods, SimBench's study cases, the money ceiling |
| [`notebooks/rl/`](../../../notebooks/rl/) | The RL probe check in the three paradigms |
| [`notebooks/runner/`](../../../notebooks/runner/) | Running an experiment on a target, and comparing finished runs |

## tests/

`python -m pytest` from the root (`pytest.ini` finds `tests/`). What each group
checks and how long it takes: [Validation](../validation/index.md).

| Folder | Checks |
|---|---|
| [`tests/market/`](../../../tests/market/) | The market, the environment, the grid methods, the signals, the market probes |
| [`tests/rl/`](../../../tests/rl/) | The probe environments, the paradigms' structure, mixed actions, same seed same run, evaluation tables |
| [`tests/runner/`](../../../tests/runner/) | Specs, run states, targets, SLURM and SSH without a cluster, results and indicators |
| [`tests/studio/`](../../../tests/studio/) | Charts and pages, driven by a simulated user |

## Everything else

| Path | What it is |
|---|---|
| `run_studio.py`, `run_all.py` | Start the Studio, or the Studio and the docs preview together |
| `mkdocs.yml` | The docs site: its navigation, theme and build settings |
| `hpc/` | `targets.toml` (where experiments run) and the cluster's Jupyter helper ([HPC setup](../../getting-started/hpc-setup.md)) |
| `.env.example`, `.env` | This machine's settings; `.env` is not in git ([HPC setup](../../getting-started/hpc-setup.md#this-machines-settings-env)) |
| `runs/` | Training runs and their results; not in git ([What a run saves](../evaluation/files.md)) |
| `docs/`, `docs_site/` | This documentation and its site: build hooks, diagram export, screenshots ([About](../../about.md)) |
| `environment.yml` | The `marlem` conda environment |
| `AGENTS.md` | Rules for working in this repository |
