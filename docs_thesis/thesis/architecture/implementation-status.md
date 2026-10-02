# Implementation status

> What of the architecture plan exists in code today, how it is tested, and how to check it yourself. Update this file in the same commit that changes the status of a part.
> Plan: [README.md](README.md) (roadmap R1–R9) · Updated: 2026-10-02.

**Legend:** ✅ done and tested · 🟡 partly done (what is missing is named) · 🎭 demo only (sample data, nothing real behind it) · ⬜ not started.

<!-- BEGIN toc (python docs_thesis/toc.py) -->
## Contents

- [1. How to check the experiment file yourself](#1-how-to-check-the-experiment-file-yourself)
- [2. Roadmap phases](#2-roadmap-phases)
- [3. Code, by layer](#3-code-by-layer)
  - [3.1 MARLEM (domain)](#31-marlem-domain)
  - [3.2 Adapters](#32-adapters)
  - [3.3 Experiment layer (`src_thesis/experiments/`, 05)](#33-experiment-layer-src_thesisexperiments-05)
  - [3.4 Application layer (`src_thesis/application/`, 03)](#34-application-layer-src_thesisapplication-03)
- [4. Studio, page by page (`src_thesis/studio/`, 04)](#4-studio-page-by-page-src_thesisstudio-04)
- [5. How to verify each working part](#5-how-to-verify-each-working-part)
- [6. Next steps (in the order proposed)](#6-next-steps-in-the-order-proposed)

<!-- END toc -->

## 1. How to check the experiment file yourself

The Studio's Build and Experiment pages edit one **draft experiment file**. Where controls are wired (§4), "Apply to draft" or "Save" writes that file to disk, and you can open it.

| What | Where |
|---|---|
| Your experiment files | `C:\Users\Kevin\AppData\Local\MARLEM\library\<id>.marlem.json` (outside OneDrive; `MARLEM_HOME` moves it) |
| Which file is the draft | The chip in the Studio header, and "File id" on the Summary page |
| Presets (read-only) | [src_thesis/experiments/presets/](../../../src_thesis/experiments/presets/) |

Three ways to see what a UI action changed:

1. **Open the JSON** in VS Code (`code C:\Users\Kevin\AppData\Local\MARLEM\library\case6-3x3-draft.marlem.json`). VS Code reloads it when the Studio writes it.
2. **Summary page → "Experiment file (JSON)"** shows the same file.
3. **Summary page → "Diff against origin"** lists every field that differs from the preset the draft came from, as dotted paths (`market.price.max: 600 → 444`).

Only fields you change are written. A field you never touched stays absent from the file and takes its default when a run is resolved (02 §3).

[↑ Contents](#contents)

## 2. Roadmap phases

| Phase | Status | What exists | What is missing |
|---|---|---|---|
| R1 Rebuild and validate | ⬜ | The issue register (80 issues), the plan, 48 issue demos as strict-xfail tests ([validation/](../validation/README.md)) | Every fix: 0 of 80 issues closed |
| R3 Grid seam + pandapower adapter | 🟡 | Grid contract records; network catalog, topology, elements and a one-hour power-flow preview for SimBench and pandapower built-ins | `GridModel.assess` (step-time power flow), `GridTopologyInfo` / `GridSignals`, settlement ledger, injection builder, SimBench profile source, participant mapping, pandapower files |
| R4 SimBench, shadow mode | ⬜ | — | Needs R1 and R3 |
| R5 SimBench in the loop | ⬜ | — | Needs R4 |
| R6 Experiment file | 🟡 | Format, load/save, hash, expansion into runs, defaults, day split, manifest, 7 presets | `build_env` (needs R1/R4); presets have a placeholder mapping and only Case 1 has its sweep |
| R7 Services, CLI, worker | 🟡 | Real `ConfigService` and grid catalog; experiment store, worker process and pool (tested with a no-op runner) | Real `ExperimentService`, `ResultService`, `ValidationService`, `ProfileService`; training and baseline runners; the CLI |
| R8 Studio | 🟡 | Shell and all pages; real grid browsing; real experiment files; editing on Market & DSO and Summary | Editing on Grid, Participants, Design; everything about runs and results is demo data |
| R9 Evidence runs | ⬜ | — | Needs R1–R8 |

[↑ Contents](#contents)

## 3. Code, by layer

### 3.1 MARLEM (domain)

| Part | Status | Notes |
|---|---|---|
| `src_thesis/marketplace`, `marl`, `cooperation` | ⬜ (original code) | Still the original MARLEM, unchanged apart from the issue markers. Rewriting it is R1. Frozen copy: `src_thesis_reference/` |
| Grid contract ([contract_new.py](../../../src_thesis/marketplace/grid/contract_new.py)) | 🟡 | Catalog and assessment records exist; `GridTopologyInfo`, `GridSignals` (D-13) not yet |
| `marketplace/settlement.py`, `marketplace/grid/injection.py`, `marl/baselines.py` | ⬜ | Planned new modules (README §2.4) |

### 3.2 Adapters

| Part | Status | Tests | Notes |
|---|---|---|---|
| pandapower grid adapter ([simbench_new.py](../../../src_thesis/adapters/grid/simbench_new.py)) | 🟡 | [test_grid_catalog.py](../../../tests/test_grid_catalog.py) | Catalog part done. `SimBenchGrid` (the step-time model) is a stub that raises |
| SimBench profile source (`adapters/profiles/simbench.py`) | ⬜ | — | The existing `adapters/profiles/` is the original CSV / synthetic code |

### 3.3 Experiment layer (`src_thesis/experiments/`, 05)

| Module | Status | Tests |
|---|---|---|
| `models/records`, `files`, `expand`, `resolve`, `manifest` | ✅ (placement rules wait for R3) | [test_experiments.py](../../../tests/test_experiments.py) |
| `store/filesystem`, `store/recorder` | ✅ | test_experiments.py |
| `factory/environment` | 🟡 `build_env_config` only; `build_env`, `build_grid` raise | — |
| `factory/training` | ⬜ interface only (stage D) | — |
| `worker/runner` | 🟡 no-op runner only; baseline and training runners raise | test_experiments.py |
| `worker/process`, `worker/pool` | ✅ | test_experiments.py (real subprocesses) |
| Presets (`experiments/presets/`) | 🟡 all 7 load, resolve and expand; placeholder mapping; sweeps for Case 1 only | [test_config_service.py](../../../tests/test_config_service.py) |

### 3.4 Application layer (`src_thesis/application/`, 03)

| Service | Status | Tests | What the real one does / what the demo fakes |
|---|---|---|---|
| `ConfigService` | ✅ real (`FileConfigService`) | test_config_service.py | Presets, library, save, clone, delete, update, origin, diff, export bundle. Not yet: `import_bundle`, `json_schema` |
| `GridCatalogService` | ✅ real (`PandapowerGridCatalogService`) | test_grid_catalog.py | Networks, topology, elements, power-flow preview |
| `ProfileService` | 🎭 | — | Profile previews, tariffs and day lists are generated sample curves |
| `ValidationService` | 🎭 | — | Findings and the dry run are fixed samples; no real check runs |
| `ExperimentService` | 🎭 | — | Runs listed in the Studio are invented; "Launch" starts nothing |
| `ResultService` | 🎭 | — | All results, curves, matrices and replays are sample data |

Which implementation the Studio uses is shown in its footer (`services: demo · grid: pandapower · files: files`).

[↑ Contents](#contents)

## 4. Studio, page by page (`src_thesis/studio/`, 04)

"Writes" lists the experiment-file fields a page saves; everything else on the page is read-only or a placeholder ("not implemented yet").

| Page | Data shown | Writes to the experiment file | Placeholders |
|---|---|---|---|
| Home | Library and presets: real. Runs and health: demo | "New from preset" creates `<preset>-draft` in the library | — |
| Library | Real file list | Click a preset → new draft file; click a file → opens it | Open file, Import bundle |
| Grid | Real networks, topology, elements, power-flow preview | **Nothing yet**: choosing a network only browses | Apply limits, Upload network |
| Participants | The draft's participants (real); map: real topology; profile previews: demo | Nothing yet | Add participant, Import mapping, Load Table 6 roles, Add battery, Apply rule |
| Market & DSO | The draft's values (real); tariff chart: demo | "Apply to draft": `market.*` (mechanism, price/quantity bounds, partner preference, async orders, ledger), `dso.tariffs.source/mode`, `dso.fees.*`, `environment.observation.version/forecast_error`, `environment.reward.version`, `environment.reward.grid_violation.attribution`, `grid.assessment.mode` | Edit weights |
| Summary | The draft (real) | Save: `meta.name`, `meta.description`. Save as: a new file with a new id. Export bundle: `exports/<id>.zip` | — |
| Design | The draft's learning plan (real); run estimate: demo | Nothing yet | Apply learning plan, Edit sweep, Edit mutations |
| Validate | Demo findings and dry run | Nothing ("Launch" calls the demo `ExperimentService`) | — |
| Runs, Results, Compare | Demo | — | Export figures |
| Settings | Store path field is a static sample (`C:/marlem-store`), not the real workspace | Dark mode only | Store path |

[↑ Contents](#contents)

## 5. How to verify each working part

| Part | Check |
|---|---|
| Experiment files | §1: change "Price max" on Market & DSO → Apply → the JSON shows `"max": <value>` under `market.price`, and Summary → Diff lists `market.price.max` |
| Save as / origin | Summary → Save as `my-test` → Library lists it → its Diff shows the original draft as origin |
| Grid catalog | Grid page with `MARLEM_STUDIO_GRID` unset: pick a SimBench network, see its topology, run the power-flow preview |
| Experiment layer | `python -m pytest tests/test_experiments.py` (no Studio involved) |
| Everything automated | `python -m pytest tests/test_config_service.py tests/test_experiments.py tests/test_grid_catalog.py tests/test_studio_boundaries.py` |

[↑ Contents](#contents)

## 6. Next steps (in the order proposed)

1. Grid page writes `grid.source`, `grid.limits`, `grid.ratings`.
2. Design page writes the learning plan (paradigms × algorithms, seeds, budget, hyperparameters, sweep).
3. Library: delete, clone, open file, import bundle.
4. Real `ExperimentService` with no-op runs (store, worker and pool are ready), then `ResultService` over the store.
5. Real `ValidationService` at schema level.

[↑ Contents](#contents)
