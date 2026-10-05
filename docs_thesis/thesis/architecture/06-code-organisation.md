# 06. Code organisation: one page, one place

> How `src_thesis/` is laid out so a person (or an AI agent) reading or changing one page opens as few files as possible. Principle from [The Vertical Codebase](https://tkdodo.eu/blog/the-vertical-codebase): code that changes together lives together; features talk through small public surfaces; shared code is its own named place.
> Master: [README.md](README.md) · Rules enforced by [test_package_boundaries.py](../../../tests/test_package_boundaries.py) and [test_studio_boundaries.py](../../../tests/test_studio_boundaries.py) · State: [implementation-status.md](implementation-status.md).

<!-- BEGIN toc (python docs_thesis/toc.py) -->
## Contents

- [1. Why](#1-why)
- [2. The layout](#2-the-layout)
- [3. Pragmatism rules](#3-pragmatism-rules)
- [4. Boundary rules](#4-boundary-rules)
- [5. The five typical changes](#5-the-five-typical-changes)
- [6. What was deliberately not moved](#6-what-was-deliberately-not-moved)
- [7. Rules for future projects](#7-rules-for-future-projects)

<!-- END toc -->

## 1. Why

The first layout grouped files by technical layer (`services/`, `studio/`, `experiments/`). It enforced the important boundaries, but one page's behaviour ended up spread over many packages. An audit of the git history (53 commits touching `src_thesis/` or `tests/`) found that 38 touched three or more packages and only 5 touched one. The Simulate page alone was about 20 files in 9 packages.

The goal is a structure where following or changing one page costs the least thinking: open one folder per layer, read one README, and the flow is clear.

[↑ Contents](#contents)

## 2. The layout

Layers stay at the top, so it stays visible where code runs. Inside each layer, files are grouped by the UI page they serve.

```
src_thesis/
  marlem/                  the simulator; original packages unchanged
    simulation/            all of "play a day": engine seam, controllers,
                           settlement, injections, checks, scenarios, loop
  platform/
    studio/                the host of the UI
      components/          UI parts used by two or more pages
      pages/<page>/        page.py (may register several routes) and parts only that page uses
    services/<page>/       service.py and models.py of that page; shared/ for helpers of two or more pages
    kernel/                experiment file model, store, worker, pool, factory
      <page>/              runner.py or probe.py of pages that start work
```

A page is the same-named folder in each layer. `studio/pages/<page>/README.md` is its flow map: page, service, runner, engine, one line per file, with links to the shared components it uses.

[↑ Contents](#contents)

## 3. Pragmatism rules

Verticality is a tool, never forced.

1. Code used by one page lives in that page's folder. No premature sharing.
2. Code used by two or more pages is promoted once to a named shared place (`studio/components/`, `services/shared/`, `kernel/`) with a clear name and docstring. Promote, do not copy: copies drift. Only a few trivial lines without logic may be duplicated.
3. Moving back is allowed: a shared piece that is again used by one page goes home.
4. Leave it alone where the layer is the natural unit: the experiment file model, store and worker, the SimBench adapter, MARLEM's original packages, the page shell.
5. A small page stays small. No empty `service.py` or `models.py` for symmetry.
6. Judge by the count: a split stays only if it lowers the number of files touched for the page's typical changes (section 5).
7. Every step records what it deliberately did not move (section 6).

[↑ Contents](#contents)

## 4. Boundary rules

Checked by tests, keyed on the role of a file, not its folder.

- `studio/**` imports only nicegui, plotly, the standard library, the services' `service.py` and `models.py`, and `studio/components/`. A page never imports another page.
- `services/**` never imports pandapower, Ray, torch, networkx or MARLEM's runtime. It may import the plain-data modules `marlem/simulation/{spec,policy,checks,catalog}.py` and `marlem/grid/contract.py`.
- `kernel/**/runner.py`, `probe.py` and the factory run in a worker or subprocess and may import anything.
- The kernel imports neither services nor studio. MARLEM never imports the platform.

[↑ Contents](#contents)

## 5. The five typical changes

Files touched before the move (traced by hand from the simulation work) and after (counted at the checkpoint of the trial).

| Change | Before | After (Simulate and Validate moved) |
|---|---|---|
| Add a controller | 2 + test, in `policies/` | 2 + test, both in `marlem/simulation/` (`controllers.py`, `catalog.py`) |
| Add a check | 1 + test | 1 + test (`marlem/simulation/checks.py`) |
| Add a sanity scenario | 3 in two packages | 2 + test in one folder (`scenarios.py`, `catalog.py` text) |
| Show a new field in the replay | 5–6 across 6 packages | 5 in three folders (`marlem/simulation/{spec,settlement,lem_engine}.py`, `kernel/simulate/runner.py`, `studio/components/replay.py`) |
| Add an option to the Simulate page | 4 across 4 packages | 4, named for the page (`pages/simulate/page.py`, `services/simulate/service.py`, `kernel/models/records.py`, `kernel/simulate/runner.py`) |

Reading the table honestly: the number of files barely drops, because data really does cross three layers (record it, serve it, show it). What drops is the hunt: every file of a page is in a folder with the page's name in each layer, the simulator side is one folder instead of five packages, and the page README lists the files and the typical changes. The scenario and controller changes, which were scattered inside MARLEM, now stay in one folder.

[↑ Contents](#contents)

## 6. What was deliberately not moved

Step 2 (`marlem/simulation/`):

- MARLEM's original packages (`agents`, `market`, `dso`, `cooperation`, `environment`, `marl`, `core`, `grid`, `profiles`) are untouched: the AST comparison, golden episodes and issue links depend on them.
- `grid/contract.py`, `grid/simbench.py` (`SimBenchGrid`) and `grid/view.py` stay in `grid/`: they are the grid's own code, used by the Grid page, the preview and the simulation.

Steps 3 and 4 (kernel, Simulate, Validate):

- `ExperimentService` (start, cancel, list, snapshot) and `ResultService` (replay, checks, summary) stay where they are: Simulate, Runs and Results all use them. They are grouped with the Runs and Results pages in the next step.
- `studio/components/replay.py` and `checks_panel.py` stay shared: Simulate and Results both use them.
- `kernel/models`, `store`, `worker`, `factory` stay as they are: the layer is their natural unit.
- Shared data types stay in `services/models.py` (series, topology, run records, check results); only types a single page uses moved into `services/<page>/models.py`.

[↑ Contents](#contents)

## 7. Rules for future projects

- Decide structure from evidence: list five typical changes and count the files each touches; mine the git history for files that change together.
- Group by what changes together (a page, a feature), keep the layers that protect real invariants, and enforce the boundaries with tests from day one.
- Share on the second use, not the first, and promote rather than copy.
- Give every feature a short flow map next to its code; keep it current as part of the change.
- Keep tests, documentation and the status row next to the feature.
- Name things with the user's words, so searching for the page name finds the code.

[↑ Contents](#contents)
