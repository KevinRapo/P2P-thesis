# Implementation status

> What of the architecture plan exists in code today, how it is tested, and how to check it yourself. Update this file in the same commit that changes the status of a part.
> Plan: [README.md](README.md) (roadmap R1–R9) · Updated: 2026-10-04.

**Legend:** ✅ done and tested · 🟡 partly done (what is missing is named) · 🎭 sample data (the method exists but returns sample data) · ⬜ not started.

<!-- BEGIN toc (python docs_thesis/toc.py) -->
## Contents

- [1. How to check the experiment file yourself](#1-how-to-check-the-experiment-file-yourself)
- [2. Roadmap phases](#2-roadmap-phases)
- [3. Code, by layer](#3-code-by-layer)
  - [3.1 MARLEM (domain)](#31-marlem-domain)
  - [3.2 Adapters](#32-adapters)
  - [3.3 Experiment layer (`src_thesis/experiments/`, 03)](#33-experiment-layer-src_thesisexperiments-03)
  - [3.4 Application layer (`src_thesis/application/`, 04)](#34-application-layer-src_thesisapplication-04)
- [4. Studio, page by page (`src_thesis/studio/`, 05)](#4-studio-page-by-page-src_thesisstudio-05)
- [5. Walking the workflow guide](#5-walking-the-workflow-guide)
- [6. How to verify each working part](#6-how-to-verify-each-working-part)
- [7. Next steps (in the order proposed)](#7-next-steps-in-the-order-proposed)

<!-- END toc -->

## 1. How to check the experiment file yourself

The Studio's Build and Experiment pages edit one **draft experiment file**. Where controls are wired (§4), "Apply to draft" or "Save" writes that file to disk, and you can open it.

| What | Where |
|---|---|
| Your experiment files | `<workspace>\library\<id>.marlem.json`. The workspace folder is shown and chosen on the **Settings** page; default `C:\Users\Kevin\AppData\Local\MARLEM` |
| Which file is the draft | The chip in the Studio header, and "File id" on the Summary page |
| Presets (read-only) | [src_thesis/experiments/presets/](../../../src_thesis/experiments/presets/) |

Three ways to see what a UI action changed:

1. **Open the JSON** in VS Code (with the default folder: `code C:\Users\Kevin\AppData\Local\MARLEM\library\case6-3x3-draft.marlem.json`). VS Code reloads it when the Studio writes it.
2. **Summary page → "Experiment file (JSON)"** shows the same file.
3. **Summary page → "Diff against origin"** lists every field that differs from the preset the draft came from, as dotted paths (`market.price.max: 600 → 444`).

Only fields you change are written. A field you never touched stays absent from the file and takes its default when a run is resolved (02 §3).

[↑ Contents](#contents)

## 2. Roadmap phases

| Phase | Status | What exists | What is missing |
|---|---|---|---|
| R1 Rebuild and validate | ⬜ | The issue register (80 issues), the plan, 48 issue demos as strict-xfail tests ([validation/](../validation/README.md)) | Every fix: 0 of 80 issues closed |
| ~~R2 Validated release~~ | retired | Retired on 2026-09-27 (D-02): no NetworkX release and no NetworkX reference results. The original code is git tag `marlem-original` | — |
| R3 Grid seam + pandapower adapter | 🟡 | Grid contract records; network catalog, topology, elements and a one-hour power-flow preview for SimBench and pandapower built-ins | `GridModel.assess` (step-time power flow), `GridTopologyInfo` / `GridSignals`, settlement ledger, injection builder, SimBench profile source, participant mapping, pandapower files |
| R4 SimBench, shadow mode | ⬜ | — | Needs R1 and R3 |
| R5 SimBench in the loop | ⬜ | — | Needs R4 |
| R6 Experiment file | 🟡 | Format, load/save, hash, expansion into runs, defaults, day split, manifest, 7 presets | `build_env` (needs R1/R4); presets have a placeholder mapping and only Case 1 has its sweep |
| R7 Services, CLI, worker | 🟡 | Real `ConfigService`, grid catalog and `ProfileService`; experiment store, worker process and pool (tested with a no-op runner) | Real `ExperimentService`, `ResultService`, `ValidationService`; training and baseline runners; the CLI |
| R8 Studio | 🟡 | Shell and all pages; real grid browsing; the whole experiment file is edited on the Build pages (Grid, Participants, Market & DSO, RL, Summary) and managed in the Library | Validate, Runs, Results and Compare are sample data |
| R9 Evidence runs | ⬜ | — | Needs R1–R8 |

[↑ Contents](#contents)

## 3. Code, by layer

### 3.1 MARLEM (domain)

| Part | Status | Notes |
|---|---|---|
| `src_thesis/marketplace`, `marl`, `cooperation` | ⬜ (original code) | Still the original MARLEM, unchanged apart from the issue markers. Rewriting it is R1. The original before any rewrite: git tag `marlem-original` |
| Grid contract ([contract_new.py](../../../src_thesis/marketplace/grid/contract_new.py)) | 🟡 | Catalog and assessment records exist; `GridTopologyInfo`, `GridSignals` (D-13) not yet |
| `marketplace/settlement.py`, `marketplace/grid/injection.py`, `marl/baselines.py` | ⬜ | Planned new modules (README §2.4) |
| MARLEM trainer ([train.py](../../../src_thesis/marl/train.py), [inference.py](../../../src_thesis/marl/inference.py)) | 🟡 original code, environment as an argument | `RLTrainer` and `RLInference` take `env_cls` (the market by default) and load the market only on use; DTDE policy IDs are strings so other RLlib environments work; `GroupedLEM` wraps any environment. The trainer's defects (I-48, I-59, I-61, I-62, …) are not fixed yet (D-16) |
| RL testbench ([rl_testbench/](../../../src_thesis/rl_testbench/)) | 🟡 cases and manifests | CartPole (one agent), MultiAgentCartPole and Simple Spread as cases; `trainer()` builds MARLEM's `RLTrainer` for each, and every paradigm builds its RLlib configuration on MultiAgentCartPole; run manifests are written ([test_rl_testbench.py](../../../tests/test_rl_testbench.py)). Simple Spread needs mpe2 and pettingzoo; evaluation and the command line come with milestone 1 ([rl-testbench.md](../validation/rl-testbench.md) §5) |

### 3.2 Adapters

| Part | Status | Tests | Notes |
|---|---|---|---|
| pandapower grid adapter ([simbench_new.py](../../../src_thesis/adapters/grid/simbench_new.py)) | 🟡 | [test_grid_catalog.py](../../../tests/test_grid_catalog.py) | Catalog part done. `SimBenchGrid` (the step-time model) is a stub that raises |
| Participant mapping ([participants.py](../../../src_thesis/adapters/grid/participants.py)) | ✅ | [test_participants.py](../../../tests/test_participants.py) | Placement by combined filters (load types, generation, storage, position; agent owns its whole bus or only the matching loads) and profile scaling (none, peak kW, annual energy) |
| SimBench profile source (`adapters/profiles/simbench.py`) | ⬜ | — | The existing `adapters/profiles/` is the original CSV / synthetic code |

### 3.3 Experiment layer (`src_thesis/experiments/`, 03)

| Module | Status | Tests |
|---|---|---|
| `models/records.py`, `files.py`, `expand.py`, `resolve.py`, `manifest.py` | ✅ (placement rules wait for R3) | [test_experiments.py](../../../tests/test_experiments.py) |
| `store/filesystem.py`, `store/recorder.py` | ✅ | test_experiments.py |
| `factory/environment.py` | 🟡 `build_env_config` only; `build_env`, `build_grid` raise | — |
| `factory/training.py` | ⬜ interface only (stage D): `trainer_arguments` translates the file and a cell into `RLTrainer`'s arguments (D-16) | — |
| `worker/runner.py` | 🟡 no-op runner only; baseline and training runners raise | test_experiments.py |
| `worker/process.py`, `worker/pool.py` | ✅ | test_experiments.py (real subprocesses) |
| Presets (`experiments/presets/`) | 🟡 all 7 load, resolve and expand; placeholder mapping; sweeps for Case 1 only | [test_config_service.py](../../../tests/test_config_service.py) |

### 3.4 Application layer (`src_thesis/application/`, 04)

| Service | Status | Tests | What it does / what is still sample data |
|---|---|---|---|
| `ConfigService` | ✅ | test_config_service.py | Presets, library, save, clone, delete, update, origin, diff, export and import of bundles, import of files. Not yet: `json_schema` |
| `GridCatalogService` | ✅ | test_grid_catalog.py | Networks, topology, elements, power-flow preview; network cache on disk (`cache_status`, `warm_cache` in a background thread, `clear_cache`) |
| `ProfileService` | ✅ | test_grid_catalog.py, test_participants.py | A network's SimBench profiles (factors and kW), SimBench's complete catalogue and its classes (Meinecke et al., 2020, Figure 1); placement rules (`suggest_mapping`), mapping import, [P2] Table 6 roles; participant previews (native and catalogue profiles, scaled); the day split of the time window; the DSO tariff CSVs and other data CSVs |
| `ValidationService` | 🎭 | — | Findings and the dry run are fixed samples; no real check runs |
| `ExperimentService` | 🎭 | — | Runs listed in the Studio are invented; "Launch" starts nothing |
| `ResultService` | 🎭 | — | All results, curves, matrices and replays are sample data |

Each service is one class in `application/<name>_service.py`; a method that is not built yet returns sample data and its docstring says what the final version will do. The Studio's header and footer list the services that still return sample data.

[↑ Contents](#contents)

## 4. Studio, page by page (`src_thesis/studio/`, 05)

"Writes" lists the experiment-file fields a page saves; everything else on the page is read-only or a placeholder ("not implemented yet").

| Page | Data shown | Writes to the experiment file | Placeholders |
|---|---|---|---|
| Home | Library and presets: real. Runs and health: sample data | "New from preset" creates `<preset>-draft` in the library | — |
| Library | Real file list | Click a preset → new draft file; click a file → opens it; clone, delete; Open file (upload a `.marlem.json`), Import bundle (upload a `.zip`) | — |
| Inspect | All real: any network's facts, topology, elements, SimBench profile inspector, a comparison with a second network, and SimBench's complete profile catalogue | Nothing (read-only by design) | — |
| Grid | Real networks, topology, elements, power-flow preview | "Apply to draft": `grid.source` (asks whether to keep or remove the participants), `grid.background.*`, `grid.limits.*`, `grid.ratings.*`, `grid.reactive.*`, `grid.power_flow.*`, `grid.assessment.non_convergence*` | Upload network |
| Participants | All real: participants with checks against the network, map with their buses, profile preview, day counts | The whole `participants` list on every add, edit, duplicate, move, remove, placement rule, mapping import or Table 6 roles; `time.*` (its own Apply) | — |
| Market & DSO | All real, including the tariff CSVs | "Apply to draft": `market.*`, `dso.tariffs.*` (source, files and columns, mapping, reset), `dso.fees.*`, `environment.observation.*`, `environment.reward.*` (version, log scale, all weights, grid-violation attribution and weights), `environment.reputation.*`, `grid.assessment.mode` | — |
| Summary | The draft (real), values set per section | Save: `meta.name`, `description`, `author`, `tags`, `data_status`. Save as: a new file with a new id. Export bundle: `exports/<id>.zip` | — |
| RL | The draft's learning plan (real); run count from `ConfigService.expand`, following unsaved changes | "Apply to draft": `learning.*` (paradigms, algorithms, seeds, budget, hyperparameters, paradigm options, model, tuning with mutations, checkpoints, rollouts), `evaluation.*`, `baselines`, `sweep`, `resources.*`, `outputs.*` | — |
| Validate | Sample findings and dry run | Nothing ("Launch" calls the sample `ExperimentService.create_runs`) | — |
| Runs, Results, Compare | Sample data. The Results replay draws the default network's preview power flow, not the run's grid; the Runs experiment filter and the Compare experiment list and paper-reference switch do nothing yet | — | Export figures |
| Settings | The real workspace folder and its `library/`, `store/`, `exports/`; the network cache with its preparation progress | Not the experiment file: "Use this folder" chooses the workspace folder (kept in `%APPDATA%\MARLEM\settings.json`); dark mode | — |

[↑ Contents](#contents)

## 5. Walking the workflow guide

The [Studio workflow guide](../../guide/studio-workflow.md), step by step, against what the code does (updated 2026-10-04, after the Build pages were finished). The guide describes the intended workflow; this table says where a user following it still hits a gap.

| Guide step | Works today | Gap | Closed by |
|---|---|---|---|
| 0 Launch, Settings | ✅ Launch, workspace folder, draft chip | The *valid* and *running* chips read sample services | §7 steps 1 and 2 |
| 1 Inspect | ✅ All three tabs on real data | — | — |
| 2 Start a file | ✅ New draft from a preset; Library: open, clone, delete, open from disk, import bundle | Presets: placeholder participant mapping; sweeps for Case 1 only | Preset work (R6) |
| 3 Grid | ✅ Network and every grid rule are written to the draft | Uploading a pandapower file | Later (R3) |
| 3 Participants | ✅ Every participant field, placement rules, mapping import, Table 6 roles, time window; checks, map, preview, day counts | — | — |
| 3 Market & DSO | ✅ Every field of `market`, `dso`, `environment`; real tariff CSVs | — | — |
| 4 RL | ✅ Every field of `learning`, `evaluation`, `baselines`, `sweep`, `resources`, `outputs`; real run count | No time estimate (needs benchmark timings in `ExperimentService.estimate`) | §7 step 2 |
| 5 Summary | ✅ `meta`, values per section, save as, diff, export | — | — |
| 6 Validate | 🎭 | Findings and dry run are fixed samples; "Launch" starts nothing | §7 step 1 (schema and network checks); the dry run needs `build_env` (track B) |
| 7 Runs | 🎭 | Runs are invented | §7 step 2 (store, worker and pool are ready) |
| 8 Results | 🎭 | Everything is sample data | §7 step 3 for the run's record; real outcomes need real runs (track B) |
| 9 Compare | 🎭 | Everything is sample data | §7 step 3; meaningful only with real runs (track B) |

**The wall.** Steps 0–7 can all become real without touching MARLEM: the experiment file, store, worker and pool exist, and a run can use the no-op runner. Real runs need `build_env` (`factory/environment.py` raises), which needs the rewritten MARLEM (R1, 0 of 80 issues closed) and the SimBench grid model (R4). So Results and Compare can show a run's record (manifest, state, log) early, but research outcomes only after track B.

[↑ Contents](#contents)

## 6. How to verify each working part

| Part | Check |
|---|---|
| Experiment files | §1: change "Price max" on Market & DSO → Apply → the JSON shows `"max": <value>` under `market.price`, and Summary → Diff lists `market.price.max` |
| Save as / origin | Summary → Save as `my-test` → Library lists it → its Diff shows the original draft as origin |
| Grid catalog | Grid page: pick a SimBench network, see its topology, run the power-flow preview |
| Experiment layer | `python -m pytest tests/test_experiments.py` (no Studio involved) |
| Everything automated | `python -m pytest tests/test_config_service.py tests/test_experiments.py tests/test_grid_catalog.py tests/test_studio_boundaries.py` |

[↑ Contents](#contents)

## 7. Next steps (in the order proposed)

Two tracks. **Track A** makes the workflow guide walkable end to end on real files and real (no-op) runs; it needs only the Studio, the services and the experiment layer. **Track B** makes the runs real; it is the long one.

Track A, in the order of the guide (§5). Done: the Grid, Participants, Market & DSO, RL and Summary pages write the whole experiment file, and the Library manages files (2026-10-04).

1. **`ValidationService`** (next step): schema level, plus checks against the network: every bus, element and profile exists, no element is owned twice or on another bus, the time window lies in the profile year and selects days, battery and scaling values are feasible, mutation domains contain their start values (02 §9).
2. **`ExperimentService` with the no-op runner**: "Launch" creates the runs in the store and starts them in the pool; Runs shows their real state, log and cancel; the run estimate from benchmark timings.
3. **`ResultService` over the store**: a run's manifest, state, log and progress; curves and outcomes once a runner records them.

Track B: R1 (rewrite MARLEM against the issue register), then `build_env`, the baseline and training runners, and R4 (SimBench grid in shadow mode). Baseline runners (`no_order`, `random`) come first: they need `build_env` but no training.

[↑ Contents](#contents)
