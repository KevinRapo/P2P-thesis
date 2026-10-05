# 04. Application layer

> `src_thesis/application/`: the services that the Studio, the CLI and notebooks call. They hide MARLEM, the experiment layer and the adapters behind typed, plain-data methods.
> Master: [README.md](README.md) · Experiment layer: [03-experiment-layer.md](03-experiment-layer.md) · Presentation: [05-presentation.md](05-presentation.md) · Decisions: D-09, D-13 · Functions: docstrings in [the code](../../../src_thesis/application/), shown in the API Reference · State: [implementation-status.md](implementation-status.md).

<!-- BEGIN toc (python docs_thesis/toc.py) -->
## Contents

- [1. Purpose](#1-purpose)
- [2. At a glance](#2-at-a-glance)
- [3. Structure in code](#3-structure-in-code)
- [4. Rules](#4-rules)
- [5. Services](#5-services)
- [6. Wiring and the workspace](#6-wiring-and-the-workspace)

<!-- END toc -->

## 1. Purpose

Every user interface needs the same operations: open and edit an experiment file, browse networks, check a file, start runs, read results. This layer offers them once, as six services, so the Studio, the CLI and notebooks behave identically and none of them depends on MARLEM, pandapower or Ray. Each service is **one class**. Services that are not built yet already have every method, returning sample data, so the user interface could be built before the engine; they are completed method by method in the same class.

[↑ Contents](#contents)

## 2. At a glance

```mermaid
flowchart LR
  CALL["Studio · CLI · notebooks"] --> BS["build_services(...)"]
  BS --> CF["ConfigService<br/>experiment files"]
  BS --> GC["GridCatalogService<br/>networks"]
  BS --> PR["ProfileService<br/>SimBench profiles"]
  BS --> PA["ParticipantService<br/>placement, previews"]
  BS --> TA["TariffService<br/>DSO tariffs"]
  BS --> VA["ValidationService<br/>preflight"]
  BS --> EX["ExperimentService<br/>runs"]
  BS --> RE["ResultService<br/>results"]
  subgraph LOW["lower layers"]
    EM["experiments.models"]
    EF["experiments.factory"]
    ES["experiments.store"]
    EW["experiments.worker.pool"]
    AG["adapters.grid"]
    AP["adapters.profiles"]
  end
  CF --> EM
  GC --> AG
  PR --> AP
  VA --> EM
  VA --> EF
  EX --> EM
  EX --> ES
  EX --> EW
  RE --> ES
```

Callers get plain data back; nothing from the lower layers reaches them. Which services are real today: [implementation status](implementation-status.md).

[↑ Contents](#contents)

## 3. Structure in code

<!-- BEGIN generated:graph application -->
```mermaid
flowchart LR
  subgraph USERS["used by"]
    n_studio__users_["studio/"]:::ext
  end
  n_application_config_service["config_service.py"]
  n_application_container["container.py"]
  n_application_data_files["data_files.py"]
  n_application_experiment_service["experiment_service.py"]
  n_application_grid_catalog_service["grid_catalog_service.py"]
  n_application_models["models.py"]
  n_application_participant_service["participant_service.py"]
  n_application_profile_classes["profile_classes.py"]
  n_application_profile_service["profile_service.py"]
  n_application_result_service["result_service.py"]
  n_application_tariff_service["tariff_service.py"]
  n_application_validation_service["validation_service.py"]
  n_application_workspace["workspace.py"]
  subgraph USES["uses"]
    n_adapters_grid["adapters/grid"]:::ext
    n_core_grid_contract["core/grid_contract.py"]:::ext
    n_env["env.py"]:::ext
    n_experiments_models["experiments/models"]:::ext
  end
  n_application_config_service -.-> n_application_models
  n_application_config_service --> n_application_workspace
  n_application_config_service --> n_experiments_models
  n_application_container --> n_application_config_service
  n_application_container --> n_application_experiment_service
  n_application_container --> n_application_grid_catalog_service
  n_application_container --> n_application_participant_service
  n_application_container --> n_application_profile_service
  n_application_container --> n_application_result_service
  n_application_container --> n_application_tariff_service
  n_application_container --> n_application_validation_service
  n_application_container --> n_application_workspace
  n_application_container --> n_env
  n_application_data_files --> n_experiments_models
  n_application_experiment_service -.-> n_application_models
  n_application_experiment_service --> n_experiments_models
  n_application_grid_catalog_service --> n_adapters_grid
  n_application_grid_catalog_service -.-> n_application_models
  n_application_grid_catalog_service --> n_core_grid_contract
  n_application_models --> n_experiments_models
  n_application_participant_service --> n_adapters_grid
  n_application_participant_service -.-> n_application_models
  n_application_participant_service --> n_application_profile_classes
  n_application_participant_service --> n_core_grid_contract
  n_application_participant_service --> n_experiments_models
  n_application_profile_classes -.-> n_application_models
  n_application_profile_service --> n_adapters_grid
  n_application_profile_service --> n_application_data_files
  n_application_profile_service -.-> n_application_models
  n_application_profile_service --> n_application_profile_classes
  n_application_profile_service --> n_core_grid_contract
  n_application_result_service --> n_application_experiment_service
  n_application_result_service -.-> n_application_models
  n_application_tariff_service --> n_application_data_files
  n_application_tariff_service -.-> n_application_models
  n_application_tariff_service --> n_experiments_models
  n_application_validation_service -.-> n_application_models
  n_application_validation_service --> n_experiments_models
  n_studio__users_ --> n_application_container
  n_studio__users_ --> n_application_models
  n_studio__users_ --> n_application_workspace
  classDef ext fill:#e5e7eb,stroke:#6b7280,color:#111
```
<!-- END generated:graph -->

Arrows are imports. Dashed arrows go to `models.py`, the data types every service returns. `result_service.py` reuses the sample constants of `experiment_service.py`. Generated from the code by `docs_thesis/graphs.py`.

| File | Class | State |
|---|---|---|
| `config_service.py` | `ConfigService`: presets from the repository, files in the workspace library; import of files and bundles | built |
| `grid_catalog_service.py` | `GridCatalogService`: networks via the pandapower adapter | built |
| `profile_service.py` | `ProfileService`: SimBench profiles of a network and of the complete catalogue, their classes | built |
| `participant_service.py` | `ParticipantService`: placement by combined filters, mapping import, [P2] Table 6 roles, participant previews | built |
| `tariff_service.py` | `TariffService`: the DSO tariff CSVs | built |
| `profile_classes.py`, `data_files.py` | Shared by the services: SimBench's profile classes; listing and reading the `data/` CSVs | |
| `validation_service.py` | `ValidationService` | sample data until R6–R7 |
| `experiment_service.py` | `ExperimentService` | sample data until R7 |
| `result_service.py` | `ResultService` | sample data until R7 |
| `models.py` | The plain data the services return; the only types that cross into the Studio (it also re-exports the experiment records) | |
| `container.py` | `build_services`: the one place that decides which implementation each caller gets | |
| `workspace.py` | Where user data lives: library, run store and exports, outside the repository and OneDrive | |

[↑ Contents](#contents)

## 4. Rules

- **Plain data only.** Services return Pydantic models, dicts, lists and chart-ready `Series`, never NiceGUI elements, Ray objects, pandapower nets or MARLEM objects. A page that held an engine object would be tied to it and could freeze or break with it.
- **Translation happens in the service.** A real service converts lower-layer records into `models.py` (e.g. the grid contract's `TopologyView` into the API model of the same name).
- **One class per service, completed in place.** A method that is not built yet returns sample data and says in its docstring what the final version will do; `SAMPLE_DATA` on the class is true until none is left, and the Studio's header lists those services. Building the services loads no pandapower (tested).
- **In-process, no REST layer (D-09).** Services run in the caller's process; anything long-running goes to the experiment layer's worker process.
- **Boundaries (tested):** `application/` never imports MARLEM runtime, pandapower, simbench, Ray or torch directly; it reaches them through `adapters/`, the grid contract and `experiments/`.

[↑ Contents](#contents)

## 5. Services

| Service | For | Uses below | Main flows |
|---|---|---|---|
| `ConfigService` | Everything done to an experiment file without running it: presets, library, edit, compare, share | `experiments.models` (files, expand, resolve), workspace | Studio "Apply to draft": `update` (dotted paths, validated) → `save` (atomic) |
| `GridCatalogService` | Choosing and understanding a network before any experiment exists | `adapters.grid` | `topology` and `preview_powerflow` feed the Grid page; no agents or RL involved |
| `ProfileService` | Understanding the available profiles before assigning any | `adapters.grid` (SimBench adapter) | `profile_types`, `catalogue_types`, series and scaled power for the Inspect page |
| `ParticipantService` | Placing participants on buses and seeing what drives them, the most error-prone setup step | `adapters.grid` (placement rules, SimBench adapter) | `suggest_mapping` by filters, `import_mapping`, `paper_roles`, `preview` per participant |
| `TariffService` | Seeing the DSO's tariffs before a run | `data/prices` CSVs | `tariff_files`, `tariffs` for the Market & DSO page |
| `ValidationService` | One set of checks (02 §9), so the Studio and the CLI accept exactly the same files | `experiments.models`, `experiments.factory` | `validate` (schema · references · full); `dry_run` builds one environment and takes one step |
| `ExperimentService` | The only way to create and control runs | `experiments.models`, `.store`, `.worker.pool` | `create_runs`: validate → expand → per run resolve, manifest, folder; `start` / `cancel` / `snapshot` via the pool (03 §5) |
| `ResultService` | Turning run folders into tables and series; outcomes kept apart from RL return | `experiments.store`, paper reference data | `summary`, curves, step replay, the 3 × 3 `matrix`; `reference` returns values reported in the papers, entered by hand with their source |

Every method, its arguments and errors are in the docstrings of each `*_service.py`; the returned types in `models.py`.

[↑ Contents](#contents)

## 6. Wiring and the workspace

**Wiring.** `build_services(home=None)` returns all six services on the given workspace; `Services.sample_data()` names those that still return sample data.

**Workspace.** User data lives in one folder outside the repository and OneDrive, because runs write many small files that sync clients lock and duplicate. Its location is, in order: `MARLEM_HOME`; the folder chosen on the Studio's Settings page (kept in `%APPDATA%\MARLEM\settings.json`); otherwise `%LOCALAPPDATA%\MARLEM`. Inside: `library/` (experiment files), `store/` (run folders, 03 §6) and `exports/` (bundles). Presets stay in the repository, read-only.

[↑ Contents](#contents)
