# MARLEM platform architecture (master)

> Status: target architecture, agreed direction, details open where marked **Decision**.
> Written: 2026-09-23 · Branch: `dev`
> Scope: the SimBench edition of MARLEM: the grid, experiment configuration, services, CLI and the NiceGUI Studio.
> The validation against the papers ([../validation/plan.md](../validation/plan.md)) runs alongside: a component is accepted when its issue demos pass.
> Code: `src_thesis/` is the live code; `src_thesis_reference/` is the frozen original for comparison (D-14).
> Roadmap phases are called R1–R9 (they were P1–P9 until 2026-09-27; P now always means a paper).

## 1. Goal

1. **Rebuild and validate** MARLEM's method faithfully to the papers in `src_thesis/` (a paper-faithful reimplementation). Every issue in the validation register is closed by the new code (its issue demo passes) or by a recorded decision. The original stays frozen in `src_thesis_reference/` for comparison; no separate NetworkX release is published (retired 2026-09-27).
2. **Build the tool on SimBench + pandapower only.** The grid is a realistic AC power flow on real distribution feeders, with far more (and more realistic) load and generation profiles. The NetworkX grid is removed from the tool.
3. **Run all original experiments on the SimBench grid.** That means the 3 × 3 paradigm × algorithm matrix (Case 6) and the other case studies (Cases 1–7). They are compared with the figures published in [P1] and [P2], qualitatively; the original NetworkX grid is not rerun.
4. **Make experiments shareable and reproducible** through one versioned JSON experiment file, executable identically from the CLI, notebooks and the NiceGUI Studio.

## 2. System at a glance

```mermaid
flowchart TB
  subgraph Presentation
    Studio["NiceGUI Studio<br/>05-studio-ui"]
    CLI["CLI<br/>04-services"]
    NB["Case notebooks"]
  end
  subgraph Application["Application services, 04-services"]
    SVC["Config · Grid catalog · Profiles · Validation · Experiment · Result"]
  end
  subgraph Experiments["Experiment layer, 03-experiment-config / 04-services"]
    SPEC["Experiment file (one JSON)"]
    FACT["Environment factory"]
    WORK["Worker process"]
    STORE[("Experiment store")]
  end
  subgraph MARLEM["MARLEM domain, 01-paper-to-code-map"]
    L0["Level 0: market, DSO, settlement, handlers"]
    L1["Level 1: agents, RLlib training"]
    L2["Level 2: cooperation KPIs, metrics"]
  end
  subgraph Adapters["Adapters, 02-simbench-grid"]
    GRID["pandapower grid: SimBench, built-in or file networks"]
    PROF["Profile sources: SimBench, CSV, synthetic"]
  end
  Studio --> SVC
  CLI --> SVC
  NB --> SVC
  SVC --> SPEC
  SVC --> STORE
  SVC --> WORK
  WORK --> FACT
  FACT --> MARLEM
  FACT --> Adapters
  L0 --> GRID
  L0 --> PROF
  WORK --> STORE
```

**Rules of the whole system:**

1. **One way in.** UI, CLI and notebooks all go through the application services and one environment factory. Nothing builds a `LocalEnergyMarket` on its own.
2. **Files, not objects.** Only the versioned experiment JSON is persisted or shared. Live pandapower nets, agents and environments are built inside the process that uses them.
3. **The grid assesses; the market does not ask the grid.** The market clears economically. After settlement, one power flow per timestep assesses the resulting injections. Violations are fed back to the agents as observations and reward.
4. **One owner of the grid (D-13).** `LocalEnergyMarket` stays the central orchestrator and is the only holder of the grid model. Market components receive plain grid data as arguments (`GridTopologyInfo`, and `GridSignals` from step t−1) and never read or write the grid themselves (02 §5.1).
5. **One grid technology.** Every network (SimBench, pandapower built-in such as IEEE 33-bus or CIGRE, or a pandapower JSON file) goes through the same pandapower adapter.
6. **Heavy work runs in a worker process.** Ray/RLlib never runs inside the UI process.

## 3. Documents

Read in this order:

| # | Document | Answers |
|---|---|---|
| 01 | [01-paper-to-code-map.md](01-paper-to-code-map.md) | Where each [P1] Fig. 2 component lives in `src_thesis/`, and what changes for SimBench and the platform |
| 02 | [02-simbench-grid.md](02-simbench-grid.md) | Network sources, loading, assigning profiles to agents, the grid contract, and the file-by-file changes to MARLEM's step |
| 03 | [03-experiment-config.md](03-experiment-config.md) | The single experiment JSON: every section and field, including RL algorithms, training modes and hyperparameters; presets; sharing |
| 04 | [04-services.md](04-services.md) | Application services, environment factory, worker, experiment store and CLI commands |
| 05 | [05-studio-ui.md](05-studio-ui.md) | NiceGUI shell, every page, what it shows, which services it calls and how pages connect |

## 4. Roadmap

Each phase has an exit criterion.

| Phase | Content | Exit criterion | Doc |
|---|---|---|---|
| **R1 Rebuild and validate** | Steps A0–D3 of the validation plan, built in `src_thesis/` | All 80 issues `fixed` / `decided` / `wontfix`; the demo of every fixed issue passes (its strict-xfail test is moved to `FIXED`) | [validation](../validation/plan.md) |
| ~~R2 Validated release~~ | **Retired 2026-09-27** (D-02): no NetworkX release and no NetworkX reference results. The frozen original is `src_thesis_reference/`. | — | — |
| **R3 Grid seam + pandapower adapter** | Grid contracts, the settlement → injection builder, lossless market, SimBench / built-in / file network loading, profile catalogue, participant mapping, power flow → `GridAssessment`. The NetworkX grid is removed from the tool. | Adapter tests pass: mapping validation, 15-min/hourly alignment, injection signs, convergence, violations | 02 §2–§5 |
| **R4 SimBench, shadow mode** | Assessment runs inside the step and is recorded; rewards and observations unchanged | A full episode runs on SimBench; `env.step` cost measured | 02 §6 |
| **R5 SimBench in the loop** | Versioned observation and reward consume the assessment (violation feedback); KPIs re-sourced from power-flow results | Short training runs reduce violations versus no-order and random baselines | 02 §6–§7 |
| **R6 Experiment file** (can start with R3) | JSON schema, environment factory, presets for Cases 1–7 and the 3 × 3 matrix | Each preset validates and runs 1 episode from its JSON | 03 |
| **R7 Services, CLI, worker** | Application services, filesystem store, worker process, CLI | `marlem run <file>` executes a 3 × 3 smoke matrix end to end | 04 |
| **R8 Studio** | Read-only (Runs, Results, Grid) → editors → launch | An experiment built in the Studio produces a run identical to its CLI equivalent | 05 |
| **R9 Evidence runs** | Original experiments on SimBench; qualitative comparison with the papers' published figures; thesis figures | Results reproducible from the stored manifests | 03 §7 |

## 5. Decision log

| ID | Decision | Status | Where |
|---|---|---|---|
| D-01 | Grid assessment happens **after settlement**: one power flow per timestep, market not constrained. Agents learn from violation feedback (reward and observation) rather than being blocked. | **Agreed** (2026-09-23) | 02 §5–§6 |
| D-02 | The tool is **SimBench/pandapower only**. The original with its NetworkX grid stays frozen in `src_thesis_reference/` for comparison; it is not a runnable backend, and no validated NetworkX release is published (the old P2 is retired). | **Agreed** (2026-09-23, revised 2026-09-27) | 02 §1 |
| D-03 | Integration goes in two stages: **shadow** (record only, R4) → **feedback** (observation and reward consume the assessment, R5). Each is a versioned mode. | Proposed | 02 §6 |
| D-04 | Keep MARLEM's file names and [P1] Fig. 2 class responsibilities, so the diff against `src_thesis_reference/` stays readable; a file may be **rewritten**. New parts (contracts, injection builder, settlement ledger, adapters, scripted baselines) get new modules. | **Agreed** (revised 2026-09-27) | 01, 02 §7 |
| D-05 | The market is **lossless per trade**. Feeder losses are reported system-wide by the power flow and supplied via the external grid. | Proposed | 02 §5 |
| D-06 | Profile assignment defaults to `mapped_replacement`: agents replace the SimBench elements they own, and all other elements run as background with their own profiles. | Proposed | 02 §3 |
| D-07 | Paper-parity presets use **hourly aggregation** (24 steps), energy-consistent. Native 15-min (96 steps) is an extension. | Proposed | 02 §4, 03 §7 |
| D-08 | **One JSON file per experiment**. It contains the world (time, grid, participants, market, DSO, environment), the learning plan (algorithms, paradigms, hyperparameters, tuning, budget, seeds), evaluation, baselines and the sweep. Runs get a system-written manifest. | **Agreed** (2026-09-23) | 03 |
| D-09 | Services run in-process for UI and CLI. Ray runs only in a worker subprocess. The filesystem experiment store is the source of truth. | Proposed | 04 |
| D-10 | The canonical environment is the conda `marlem` env (`environment.yml`). pandapower 3.5.4 and simbench 1.6.2 are already installed. `pydantic` and `nicegui` are added after a compatibility check. | Proposed | 04 §7 |
| D-11 | Violation feedback reward: shared vs bus-attributed vs marginal credit assignment | **Open** | 02 §6 |
| D-12 | Non-convergent power flow during training: truncate with a fixed penalty vs fail the run | **Open** | 02 §6 |
| D-13 | **Grid ownership and data flow.** `LocalEnergyMarket` is the only holder of the `GridModel`. `OrderMatcher`, `DSOAgent` and `DERAgent` get `GridTopologyInfo` (static distances and zones) and `GridSignals` (step t−1) as arguments and never call the grid; KPIs, reward and observation use `GridAssessment[t]`. A read-only view is the accepted fallback. | **Agreed** (2026-09-27) | 02 §5.1 |
| D-14 | **Code home.** `src_thesis/` is the live code (domain, adapters, services, Studio, tests and launch configuration unchanged). `src_thesis_reference/` is a frozen snapshot of the original with its issue markers, never edited. | **Agreed** (2026-09-27) | 01 |
| D-15 | **Voltage limits.** `grid.limits` in the experiment file overrides every bus when set; when unset, each bus uses the network's own `min_vm_pu` / `max_vm_pu`, with 0.95–1.05 pu as the fallback. The Studio preview follows the same rule. | **Agreed** (2026-09-27) | 02 §2, 03 §3.3 |

## 6. Glossary

| Term | Meaning |
|---|---|
| **Settlement** | Per agent and step: served demand, generation, curtailment, battery charge and discharge, imports, exports and cash. The output of the market step. |
| **Injection** | An agent's net active power at its bus, derived from settlement: production − consumption, in kW. It is **not** trades counted as loads. |
| **Assessment** | One power-flow result for one timestep: voltages, loadings, losses, external-grid exchange and violations |
| **Grid signals** | The few numbers the market may use from the previous step's assessment (max line loading, external-grid exchange); passed as an argument (02 §5.1) |
| **Topology info** | Static per network: electrical distance between buses and bus zones, computed once at reset and passed to the market (02 §5.1) |
| **Background** | Network loads and generators not owned by an agent. They follow their own profiles. |
| **Reference copy** | `src_thesis_reference/`: the frozen original MARLEM (relocated, with issue markers). Never edited; compare it with `src_thesis/` on disk (D-14). |
| **Experiment file** | The single JSON describing one study (03) |
| **Preset** | A checked-in experiment file reproducing an original MARLEM case on SimBench |
