# Getting started: set the tool up

> From an empty machine to a running Studio, a passing test and the docs in your
> browser. About half an hour, most of it the environment's download. Then go on with
> [First steps](first-steps.md).

## What you need

- **Git** and **conda** (Miniforge or Miniconda). Every Python package comes from
  [environment.yml](../../environment.yml).
- **Windows or Linux.** The tool is developed on Windows. The cluster is Linux.
  A GPU is optional: PPO here trains on the CPU.
- **For cluster runs only:** an account on the TalTech HPC and an SSH key. The
  [HPC setup](../hpc/setup.md) covers that. Everything below works without it.

## 1. Get the code

The code is the `marlem-v2` branch of one public repository:

```
git clone -b marlem-v2 https://github.com/KevinRapo/P2P-thesis.git marlem-v2
cd marlem-v2
```

All commands on these pages run from this folder, the **repository root**.

The other branches are reference only:
- `main` holds the original MARLEM as published;
- `marlem-v1` holds the first rebuild.

## 2. Create the environment

```
conda env create -f environment.yml
conda activate marlem
```

This creates the `marlem` environment with Python 3.12. It holds:
- pandapower and SimBench (the grid);
- Ray RLlib and PyTorch (learning);
- NiceGUI (the Studio);
- Jupyter, pytest and MkDocs.

The versions are pinned to the ones the results were produced with. After someone
changes `environment.yml`, run `conda env update -f environment.yml`.

PyTorch comes from its CUDA 12.6 index. Without a GPU, the same wheel runs on the
CPU.

In VS Code, open the repository root as a single folder and choose `marlem` as
the interpreter. The tests and notebooks find the root from there.

## 3. Check it works

```
pytest tests/market
```

The market tests load SimBench networks and run power flows. They take under a
minute. If they pass, the grid and the market are installed correctly.

`pytest tests/rl` trains small PPO policies and takes longer. Run it when you change
the learning layer.

## 4. Start the Studio

```
python run_studio.py
```

Then open <http://localhost:8091>. The [Studio](../studio/index.md) is the
interface to the whole workflow:
- look at networks and profiles;
- build a scenario;
- step through the market;
- start runs and read their results.

It reads and writes the same files as the command line, so you can mix the two.

## 5. Read the docs locally

The documentation is not published online. Build it on your own machine:

```
python run_docs.py
```

Then open <http://127.0.0.1:8001>. The preview updates while you edit `docs/`.
After a change, check it:

```
python run_docs.py build
```

This build stops on broken links.

`python run_all.py` starts both the Studio and the docs preview, each in its own
window (Windows only).

## 6. This machine's settings (optional)

Settings that belong to a person or a machine, not to the project, go in a file
`.env` in the repository root. The file is not committed. To make one, copy
[.env.example](../../.env.example) to `.env` and fill in what you need.

Usually that is only `MARLEM_SLURM_ACCOUNT`, and only to run on the cluster. The
other keys have working defaults:
- the runs folder;
- the Studio's port;
- the SSH host.

Every key is listed in the [HPC setup](../hpc/setup.md#this-machines-settings-env).

## Where things are

| Folder | Holds |
|---|---|
| `core/` | Everything that computes. `grid/` (SimBench, power flow), `market/`, `env/` (the market as an RL environment), `rl/` (PPO), `runner/` (experiments, results) |
| `config/` | `scenarios/` (a network, day, participants, market settings), `experiments/` (training runs), `data/` (price files) |
| `studio/` | The Studio. It shows what `core/` computes |
| `notebooks/` | Validation and analysis, calling `core/` |
| `tests/` | `market/`, `rl/`, `runner/`, `studio/` |
| `runs/` | Every training run and its results. Created on the first run; not committed |
| `docs/` | These pages |

Every folder and file is described in [Code structure](../structure.md).
