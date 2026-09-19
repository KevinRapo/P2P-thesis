# MARLEM-restored baseline knowledge map

> Status: current-state synthesis and cross-worktree documentation review  
> Worktree: `marlem-baseline`  
> Last reviewed: 2026-09-19

## 1. Purpose

This document collects the durable information that was scattered across the
MARLEM worktrees and states which parts actually apply to the restored
baseline. It is deliberately shorter than the historical audit documents and
more conservative than the target-architecture documents.

The baseline can execute the Case 6 algorithm × training-mode matrix, but an
executable run is not evidence that an algorithm has learned a useful policy.
Learning claims still require independent seeds, held-out evaluation,
non-learning comparators, and outcome metrics that are supported by recorded
data.

## 2. Current baseline in one view

The live runtime remains the original `src/` package, with corrected behavior
layered into it:

```text
RLTrainer / RLInference
        |
        v
LocalEnergyMarket
  |-- DERAgent + Battery + EnergySettlement
  |-- OrderMatcher + DSOAgent + cash ledger
  |-- GridNetwork (abstract NetworkX transport graph)
  |-- ObservationHandler + RewardHandler
  `-- ImplicitCooperation + optional analytics/plots
```

The important current boundaries are:

- `src/scenario.py` is the canonical Case 6 construction path.
- `src/environment/lem.py` owns the timestep sequence.
- `src/agent/settlement.py` is the household physical-energy record.
- `src/market/matching.py` owns economic matching, but still calls the legacy
  graph directly for transfer limits and losses.
- `src/grid/network.py` is an abstract transport approximation. It is not an
  AC or DC power-flow implementation.
- `src/environment/train.py` owns RLlib configuration and long-running Ray
  execution. SimBench or NiceGUI logic does not belong there.

## 3. Current scientific and unit contract

The following statements are supported by the baseline source and methodology:

| Quantity | Baseline meaning |
|---|---|
| DER/grid power rating | kW |
| Profile, order, trade, and settlement quantity | kWh during one timestep |
| `time_step_hours` | Conversion between kW and per-step kWh; default `1.0` |
| Price | currency/kWh |
| Cash/profit | currency |
| Battery energy | internal kWh |
| Graph flow | abstract per-period transport flow, not electrical current |

Each household settlement satisfies:

```text
generation + imports + battery discharge
= served demand + exports + battery charge + curtailment
```

and demand is split into served and unserved demand. These records are the
correct source for a future physical-grid injection. A purchase must not be
added as a second load, and a sale must not be added as a second generator.

The post-settlement point-of-connection quantities should be derived as:

```text
consumption_kwh = served_demand + battery_charge
production_kwh  = generation - curtailed_generation + battery_discharge
net_injection_kwh = production_kwh - consumption_kwh
                  = exported - imported
net_injection_kw  = net_injection_kwh / time_step_hours
```

Positive net injection means export into the feeder. This identity is the
central handoff from MARLEM settlement to SimBench/pandapower.

## 4. What the current grid does and does not do

`GridNetwork` currently combines several concerns:

- graph topology and participant placement;
- shortest-path distance;
- per-trade delivery loss;
- partial transfer limits from abstract edge capacity;
- edge-flow mutation and congestion;
- inputs to DSO fees, observations, rewards, cooperation KPIs, analytics, and
  persistence.

This means replacing only `src/grid/network.py` would change market allocation,
settlement, reward, and observation semantics at the same time. SimBench must
enter behind a new boundary and first run in a non-authoritative shadow mode.

An AC solve answers whether one aggregate operating point converged and what
voltages, element loadings, losses, and upstream exchange resulted. It does
not naturally provide the legacy model's per-trade path, per-trade loss, or
trade-by-trade feasibility decision. Those concepts must not be faked by
projecting the pandapower network into a NetworkX graph.

## 5. Baseline validation status that matters to the extension

The restoration record reports broad unit, integration, checkpoint, and
notebook coverage. Those counts are historical evidence; the installed test
count should always be obtained from a fresh `pytest -q` run.

The extension must preserve these baseline properties:

- exact episode horizon;
- stable agent order in DTDE, CTDE, and CTCE;
- household energy and cash conservation;
- one battery dispatch per period;
- seeded reset behavior;
- source versus delivered trade quantities;
- checkpoint restoration through RLlib's supported action path;
- Case 6 scenario provenance and documented paper deviations.

Still-open baseline limitations include:

- no demonstrated learning quality from the current short or smoke runs;
- unverified claims in `src/analytics/`;
- incomplete multi-seed statistical reporting and comparator suite;
- the single-process hash chain is an audit log, not blockchain consensus;
- the current grid is intentionally abstract;
- a full experiment store and replayable per-step physical result stream do
  not yet exist.

## 6. Useful prototype evidence

The `marlem` worktree contains two prototypes that should be mined for patterns,
not copied as production modules.

### SimBench/pandapower prototype

The prototype proves that it can:

- load low-voltage SimBench feeders;
- expand the 15-minute load and generation profiles;
- map illustrative agents to load/static-generator elements;
- apply kW overrides;
- run a Newton-Raphson pandapower solve; and
- extract voltage extrema, line/transformer loading, losses, external-grid
  exchange, and serializable topology.

Its useful production patterns are defensive copies of a cached source net,
an explicit mapping file, a UI-independent service facade, and typed result
objects. Its NetworkX projection is for visualization only and must not become
an electrical-feasibility contract. The prototype also does not receive the
baseline's battery-aware settlement, so it is not yet an integration.

### NiceGUI prototype

The prototype proves that a multi-page NiceGUI shell, Plotly charts, SimBench
inspection, and a separate training child process are workable. Keep these
patterns:

- one module per page;
- shared page shell and navigation;
- UI callbacks calling services rather than pandapower or RLlib directly;
- Ray training in a child process;
- short polling callbacks that read progress and logs.

Do not carry over its in-memory run history, illustrative grid equations,
notebook-derived configuration discovery, or its second Case 6 builder. The
prototype builder differs from `src/scenario.py` in pricing, profiles, and
proof-of-work settings. Production Studio must use one scenario factory and a
persistent experiment store.

## 7. Cross-worktree documentation disposition

All files under each worktree's `docs/` directory were inventoried. The two
paper PDFs are byte-identical where duplicated, so only one copy of each is
kept here.

| Source | Useful material retained | What is not transferred as truth |
|---|---|---|
| `marlem-baseline/docs` | Baseline methodology, validation status, benchmarks, tests, and history | Historical pass counts are not treated as a fresh run |
| `marlem-dev/docs/thesis/architecture.md` | Service boundary, filesystem experiment store, separate worker, NiceGUI page rules | Its broad target layout is not an implemented baseline architecture |
| `marlem-dev/docs/thesis/architecture-code-map.md` | Grid coupling inventory and replaceable-backend principle | The broken/incomplete `src_thesis` relocation is not adopted |
| `marlem-dev/docs/thesis/grid-replacement-code-map.md` | Post-settlement assessment point, mapping/unit/open-decision list | File paths and behavior descriptions are adjusted to the restored baseline |
| `marlem-dev/docs/thesis/validation-plan-fix.md` | Severity vocabulary and validation-gate discipline | Its issue statuses describe a different branch |
| `marlem/docs/architecture.md` | Same application-service/worker/UI ideas, updated Conda assumption | It predates a production SimBench boundary |
| `marlem/docs/model-contract.md` | Explicit kW/kWh/timestep language | The validation branch's exact action/model variant is not substituted for this baseline |
| `marlem/docs/metric-contract.md` and `experiment-protocol.md` | Conservative metric naming, independent seeds, raw records, manifest hashes | Referenced modules such as `baselines.py` and `experiment.py` do not exist in this baseline |
| `marlem/docs/workspace-audit-2026-09-06.md` | Warning against double-counting trades as injections; prototype scope boundary | Its A01–A15 findings and statuses concern the validation worktree, not this restored baseline |
| `marlem/docs/repository-fix-history.md` | Portability lessons for Ray, Windows, notebooks, and result provenance | Superseded branch-specific implementation state |
| `marlem-astra/docs/restoration.md` | Physical-settlement equations, learning-validation discipline, honest scope language | Its later source changes and evidence are not silently imported |
| `marlem-astra/docs/tests.md` | Distinction between maintained tests and aspirational historical tests | The long historical test inventory is not a claim about files present here |
| `marlem-main/docs` | Original guidelines/test documentation provenance | No newer design information than the other sources |
| Paper text/PDFs | Paper component model, Case 6 parameters, and stated experiment intent | Underspecified paper details are not invented or called reproduced |
| Worktree setup, GitHub issue previews, JSON audit snapshots, probe script/results | Provenance and historical diagnostics | Device-specific setup and machine snapshots are not part of the target design |

## 8. Architectural decisions carried forward

The extension should use these decisions unless implementation evidence forces
a revision:

1. Keep the restored `src/` runtime and add narrow seams; do not begin with a
   package-wide move.
2. Keep the legacy NetworkX model as a named comparison backend.
3. Separate economic trade transport from aggregate physical-grid assessment.
4. Run one physical assessment after settlement and before KPI/reward/next
   observation construction.
5. Use versioned, serializable scenario specifications. Never put a live
   pandapower net in an RLlib environment configuration or persisted manifest.
6. Keep NiceGUI as presentation only. CLI and UI call the same services.
7. Run Ray in an owned worker process, not in the NiceGUI event loop.
8. Keep experiment directories as the portable source of truth before adding a
   database or message queue.
9. Introduce physical quantities into rewards or observations only after their
   definitions and fixed shapes are versioned and tested.
10. Describe SimBench as an AC assessment backend until a real constrained
    clearing/re-dispatch algorithm exists.

The concrete work sequence and acceptance gates are in
[the implementation plan](simbench-nicegui-implementation-plan.md).

