# Code structure

> The repository folder by folder, down to each script: what it is for and how far
> it is built. Keep this page current when files are added, moved or built.

Three layers. `core/` is the MARLEM functionality: `core/grid/` models the
network, `core/market/` the market on it (its `LocalEnergyMarket` runs both, step by
step), `core/config/` describes a scenario. `notebooks/` call `core/` directly to
validate it. `studio/` is the user interface: its pages and components call
`studio/adapters/`, a thin layer over `core/`. `core/` never imports `studio/` or
`notebooks/`, so anything that looks wrong in the Studio can be reproduced in a
notebook to tell a core problem from a UI one.

```mermaid
flowchart LR
  root(["marlem-clean"])

  root --> core["core/"]

  core --> config["config/"]
  config --> c1["scenario.py"]:::data
  config --> c2["store.py"]:::done
  config --> c3["placement.py"]:::done

  core --> grid["grid/"]
  grid --> g1["contract.py"]:::done
  grid --> g2["simbench.py"]:::done
  grid --> g3["powerflow.py"]:::done

  core --> market["market/"]
  market --> m1["lem.py"]:::done
  market --> m7["clearing.py"]:::done
  market --> m8["bidding.py"]:::done
  market --> m4["clearing_price.py"]:::done
  market --> m2["order.py"]:::done
  market --> m5["reputation.py"]:::orig
  market --> m6["validation.py"]:::orig
  market --> agent["agent/"]
  agent --> a1["der.py"]:::done
  agent --> a2["battery.py"]:::done
  market --> dso["dso/"]
  dso --> d1["dso.py"]:::done
  market --> profile["profile/"]
  profile --> p1["base.py · der.py · dso.py"]:::orig

  root --> notebooks["notebooks/"]
  notebooks --> n1["validate_market.ipynb"]:::done
  notebooks --> n2["scenarios/validate_market.json"]:::done

  root --> tests["tests/"]
  tests --> x1["test_studio_matches_core.py"]:::done

  root --> studio["studio/"]
  studio --> t1["app.py · layout.py · navigation.py<br/>state.py · theme.py · static/"]:::done
  studio --> pages["pages/"]
  pages --> pg1["inspect.py · settings.py"]:::done
  pages --> pg2["grid_participants.py · market_dso.py<br/>summary.py · step.py"]:::done
  studio --> comps["components/"]
  comps --> k1["network.py · profiles.py · charts.py · cards.py<br/>tables.py · labels.py · day_profiles.py"]:::done
  studio --> adapters["adapters/"]
  adapters --> v1["container.py · workspace.py · models.py"]:::done
  adapters --> v2["grid_catalog_service.py · profile_service.py<br/>profile_classes.py"]:::done
  adapters --> v3["scenario_service.py · market_service.py"]:::done

  classDef done fill:#dcfce7,stroke:#15803d,color:#111
  classDef data fill:#dbeafe,stroke:#1d4ed8,color:#111
  classDef stub fill:#fef3c7,stroke:#b45309,color:#111
  classDef orig fill:#e5e7eb,stroke:#6b7280,color:#111
```

Green: works. Blue: data definitions only. Amber: stub, methods raise
`NotImplementedError` or the page shows a placeholder. Grey: original MARLEM code,
copied unchanged, kept as the reference; most of it is **not importable** (its
imports point to the old layout).

## core/config/: the scenario

Everything the user sets before stepping the market, as plain data.

| Script | What it does | State |
|---|---|---|
| `scenario.py` | `Scenario`: the network (`GridSetup`), the participants with their batteries, the market rules and the DSO tariffs and fees; each setup lists its own problems (`problems()`), shown on the Summary page | data and its checks |
| `store.py` | Save and load a scenario as JSON | done |
| `placement.py` | Placing participants on the scenario's network: one on a bus, or one per load or prosumer bus; imports `core/grid/` | done |

## core/grid/: the SimBench network

The only place that imports pandapower and simbench. It hands out plain records,
never pandapower objects.

| Script | What it does | State |
|---|---|---|
| `contract.py` | The plain records that cross the grid seam: networks, topology, elements, profiles, power-flow results | done |
| `simbench.py` | Lists, loads and caches networks; topology, elements, profiles, the profile catalogue; a one-hour power flow | done |
| `powerflow.py` | `SimBenchGrid`: one power flow per market step; owned elements switched off, each participant's net injection at its bus; distances along the lines | done |

## core/market/: the MARLEM market

The market of the paper ([methodology](marlem/methodology.md)). `lem.py` is the
one class that runs it (`LocalEnergyMarket`, as in the original); `clearing.py`, `bidding.py`
and `clearing_price.py` are its rebuilt pieces, and the remaining original files
are the reference for what is still to rebuild (reputation, fees).

| Script | What it does | State |
|---|---|---|
| `lem.py` | `LocalEnergyMarket`: the participants (`Participant`) and the DSO (`Dso`), one step in the paper's phases (validate, orders, the three stages, settle, power flow, advance), one stage at a time or all at once; the history of the day | done |
| `clearing.py` | The three clearing stages as separate functions: preferences, double auction, DSO | done |
| `bidding.py` | The rule that writes orders: battery first, then sell the surplus or buy the deficit between the DSO's tariffs | done |
| `clearing_price.py` | Pricing mechanisms with one fixed signature (fixes the seller price) | done |
| `order.py` | `Order` and `Trade` (with the stage that made it) | done |
| `reputation.py` | Reputation update after each period (eq. 12); its types are type-only now, so it imports | original, to rebuild on `StepRecord` |
| `validation.py` | Hash-chained trade ledger with proof of work; `seal_block` closes a market period's block | original, public `seal_block` added |
| `agent/der.py` | `Participant`: profiles from its elements, feasibility (eq. 15a-b), partner choice, settlement (eq. 13, 14, battery eq. 16), its bus injection; `ParticipantOutcome` | done |
| `agent/battery.py` | `Battery`: its energy, what it can still take or give (eq. 15c-d), charging and discharging (eq. 16); the market only calls it | done |
| `dso/dso.py` | `Dso`: tariffs, market price (their midpoint), stage 3 clearing (§3.3.2); `DSO_ID`. Fees (eq. 8) and balance (eq. 7) not built | done |
| `profile/` | Synthetic or CSV generation, demand and tariff profiles | original, imports |

## studio/: the user interface

NiceGUI, port 8090. A page is one file in `pages/`; code goes to `components/`
only when more than one place uses it.

| Script | What it does | State |
|---|---|---|
| `app.py` | Registers the pages and starts the server | done |
| `layout.py`, `navigation.py`, `theme.py`, `static/` | Page frame, left navigation, colours and styles; the header names the current scenario and opens another from a scenario file (`notebooks/scenarios/` or an upload) | done |
| `state.py` | The adapters (`services()`), built once | done |
| `pages/inspect.py` | Inspect: any network in depth, all SimBench profiles, two networks compared | done |
| `pages/settings.py` | Workspace folder, network cache and its coverage, dark mode | done |
| `pages/grid_participants.py` | Network, day, step length, background, limits; participants placed by clicking buses or per load or prosumer bus; batteries | done |
| `pages/market_dso.py` | Pricing mechanism, bounds, preferred partners, ledger; the bidding rule; the DSO's tariffs | done |
| `pages/summary.py` | Summary before running: readiness checks; tab Settings (every grid, market, DSO and battery setting once, the participants' day, the network) and tab Day profiles | done |
| `pages/step.py` | One click per part of a step (orders, the three stages, settle and power flow): order book, network with trades and voltages, trades, participants, the day so far | done |
| `components/network.py` | Network picker with filters, summary, topology plot, element table, profile inspector | done |
| `components/profiles.py`, `charts.py`, `cards.py`, `tables.py` | Profile class tiles, Plotly figures (also the day's curves), cards, tables | done |
| `components/day_profiles.py` | The Summary's Day profiles tab: every element on the scenario's day, participants (they trade) apart from the background; summed curves, single curves by row selection | done |
| `components/labels.py` | The names shown for mechanisms, background modes and step lengths, shared by the settings and summary pages | done |

## notebooks/: the core without the Studio

Notebooks import `core/` only. Run them with the `marlem` conda env as kernel.

| Notebook | What it does | State |
|---|---|---|
| `validate_market.ipynb` | Scenario, inputs per step, one step part by part, the whole day, rule checks, experiments side by side | done |
| `scenarios/validate_market.json` | The notebook's scenario, saved by it in the Studio's format: open it from the Studio's header (Scenario: … → Open) to play the same scenario there | done |

## tests/: the Studio against the core

Run with `python -m pytest tests` in the `marlem` conda env.

| Test | What it checks | State |
|---|---|---|
| `test_studio_matches_core.py` | `validate_market.json` read by `ScenarioService` and stepped part by part by `MarketService` gives the same `StepRecord`s as `LocalEnergyMarket.run_to_end` | done |

## studio/adapters/: what the pages call

Translates between the Studio and the layers below, so pages never touch the
market or pandapower directly.

| Script | What it does | State |
|---|---|---|
| `container.py` | Builds the adapters once | done |
| `workspace.py` | Where the Studio keeps its data: the network cache, the scenario file, per-browser state (`C:\MARLEM` here) | done |
| `grid_catalog_service.py` | Networks, their facts, topology, elements as the grid contract's records; the network cache and its background warming | done |
| `profile_service.py` | A network's profiles and SimBench's whole catalogue; every element's power on the scenario's day (`day_profiles`) | done |
| `profile_classes.py` | SimBench's profile classes and how a profile name is classified | done |
| `models.py` | The data types only the Studio needs: profile classes, profile types, chart series, a day's element profiles | done |
| `scenario_service.py` | The scenario being edited, saved on every change; calls `core/config/placement.py` to place participants; lists, reads and opens scenario files | done |
| `market_service.py` | Builds and holds the `LocalEnergyMarket` the Step page plays; build, next part, step, run to the end, clear (when another scenario is opened) | done |

## Around the code

| Path | What it is |
|---|---|
| `docs/` | This documentation (Markdown); `docs/networks.py` generates the network catalogue |
| `docs_site/` | The MkDocs site built from `docs/`: config, build hooks, diagram assets |
| `run_studio.py` | Starts the Studio with auto-reload |
| `run_all.py` | Starts the dev servers (both branches' docs and Studios) in their own windows |
| `AGENTS.md` | Rules for working in this repository |
| `.vscode/` | Launch entries and the Python interpreter |

## Choices in the rebuilt market step

Where the rebuilt step differs from the paper or the original code, for now:

| Topic | Here |
|---|---|
| Orders | Written by the bidding rule (`core/market/bidding.py`); no learning |
| Orders preferring the DSO | Skip stages 1 and 2 and are cleared in stage 3 (the original cleared them first) |
| Losses | The market is lossless; losses show in the power flow |
| Grid fees (eq. 8) | Not charged yet |
| Reputation (eq. 12) | Stays at 0.5 for everyone; only the auction's tie-break |
| Tariffs | Constant over the day |
| Submitted orders | Never changed by the clearing (the original changed them in place) |
| Batteries (eq. 15–16) | Efficiencies and the power limit included; partial charges allowed |
