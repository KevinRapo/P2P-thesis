# 01. Paper-to-code map

> Where each component of [P1] Fig. 2 lives in `src_thesis/`, which validation step covers it, and what changes when SimBench and the platform are added.
> Master: [README.md](README.md). Validation steps: [../validation/plan.md](../validation/plan.md).

`src_thesis/` holds the original MARLEM code, relocated into paper levels with the **same file names** (see [`src_thesis/README.md`](../../../src_thesis/README.md) for the full original → new path table). `src/` is kept unchanged as the historical comparison. `src_thesis_reference/` is a frozen snapshot of `src_thesis/` (2026-09-27, with the issue markers) for on-disk comparison. The SimBench edition is built **in `src_thesis/` itself**, keeping file names and class responsibilities while files may be rewritten (D-04, D-14), and the NetworkX grid leaves the tool.

**Change legend:** **—** unchanged · **Adapt** small additive edit in the same file · **Rewrite** same file and responsibility, new implementation (D-04) · **New** new module · **Replace** implementation swapped behind a contract. The verdict per function is in the [keep / replace audit](../validation/marlem-keep-replace-audit.md).

## 1. Level 0: Platform Marketplace

| Fig. 2 class | File | Role | Validation | SimBench / platform change |
|---|---|---|---|---|
| `LEM` | [marketplace/lem.py](../../../src_thesis/marketplace/lem.py) | Episode orchestration: reset, step | A1 | **Rewrite**: same phase order; receives the grid model from the factory and is its **only holder** (D-13); builds injections after settlement, calls `assess`, passes the assessment to KPIs, reward, observation and info, and `GridTopologyInfo` / `GridSignals[t−1]` to the market (02 §5.1, §7) |
| `ActionHandler` | [marketplace/action.py](../../../src_thesis/marketplace/action.py) | Action space, partner index | A3 | — |
| `ObservationHandler` | [marketplace/observation.py](../../../src_thesis/marketplace/observation.py) | 42-dim observation | C1 | **Rewrite**: versioned schema, same Table 2 layout; grid block sourced from `GridAssessment` (R5) |
| `RewardHandler` | [marketplace/reward.py](../../../src_thesis/marketplace/reward.py) | Reward eq. 3–6 | C2 | **Rewrite**: versioned reward, same eq. 3–6 structure and weights; physical-violation term in feedback mode (R5) |
| `ReputationHandler` | [marketplace/market/reputation.py](../../../src_thesis/marketplace/market/reputation.py) | Reputation eq. 12 | A9 | Adapt: grid term from assessment or dropped (**Decision** in 02 §8) |
| `OrderMatcher`, `MatchingResult` | [marketplace/market/matching.py](../../../src_thesis/marketplace/market/matching.py) | Stages 1–3, clearing | A5 | **Rewrite**: same three stages; NetworkX calls removed; lossless matching; holds no grid, receives `GridTopologyInfo` and `GridSignals` as arguments (D-13) |
| `MarketConfig`, `ClearingMechanism` | [marketplace/market/matching.py](../../../src_thesis/marketplace/market/matching.py), [mechanism.py](../../../src_thesis/marketplace/market/mechanism.py) | Bounds, pricing | A4 | — |
| `Order`, `Trade` | [marketplace/market/order.py](../../../src_thesis/marketplace/market/order.py) | Economic records | A5 | Adapt: `transmission_loss` removed (lossless market); `distance` = electrical distance |
| `DSOAgent` | [marketplace/dso/dso.py](../../../src_thesis/marketplace/dso/dso.py) | Tariffs, residual clearing, fees | A6 | **Adapt**: holds no grid; fee inputs come from `GridSignals[t−1]` and `GridTopologyInfo` passed in by the loop (D-13), not graph queries |
| `Validator`, `TransactionBlock` | [marketplace/market/validation.py](../../../src_thesis/marketplace/market/validation.py) | Hash-chained trade log | A10 | — |
| `GridNetwork` | [adapters/grid/network.py](../../../src_thesis/adapters/grid/network.py) | NetworkX grid (abstract) | A7 | **Removed from the tool** (frozen in `src_thesis_reference/`); replaced by the pandapower adapter behind `GridModel` |
| `GridTopology`, `Location` | [marketplace/grid/base.py](../../../src_thesis/marketplace/grid/base.py), [config.py](../../../src_thesis/marketplace/grid/config.py) | Synthetic topologies, coordinates | A7 | **Removed from the tool**; locations are bus IDs from the network |
| *(not in Fig. 2)* profile handlers | [adapters/profiles/](../../../src_thesis/adapters/profiles/) | Generation, demand, tariffs | A2 | **New** `simbench` profile source beside the existing ones (02 §3) |
| *(not in Fig. 2)* config I/O | [marketplace/io.py](../../../src_thesis/marketplace/io.py) | env_config save/load | D3 | **Superseded** by the experiment file (03) |

## 2. Level 1: MARL Agents

| Fig. 2 class | File | Role | Validation | SimBench / platform change |
|---|---|---|---|---|
| `DERAgent` | [marl/agents/der.py](../../../src_thesis/marl/agents/der.py) | Action feasibility, settlement, partner choice | A3, A8 | **Rewrite** feasibility (eq. 15), settlement (into the settlement ledger) and partner choice; `node_id` becomes a bus ID from the mapping; partner distance from `GridTopologyInfo` passed in (D-13) |
| `Battery` | [marl/agents/battery.py](../../../src_thesis/marl/agents/battery.py) | Storage dynamics | A8 | — (a battery can be sized from a SimBench storage element; 02 §3) |
| `RLTrainer`, `GroupedLEM` | [marl/train.py](../../../src_thesis/marl/train.py) | RLlib config, PBT, grouping | D1 | Adapt: `learning` section of the experiment file replaces its arguments; the environment is built by the factory inside each runner |
| `RLInference` | [marl/inference.py](../../../src_thesis/marl/inference.py) | Checkpoint rollout | D2 | Adapt: called by the worker |
| `RLAlgorithm`, `TrainingMode` | [marl/base.py](../../../src_thesis/marl/base.py), [ctce.py](../../../src_thesis/marl/ctce.py), [ctde.py](../../../src_thesis/marl/ctde.py) | Algorithms, paradigms | D1 | — |

## 3. Level 2: Implicit Cooperation

| Fig. 2 class | File | Role | Validation | SimBench / platform change |
|---|---|---|---|---|
| `ImplicitCooperation` | [cooperation/implicit_cooperation.py](../../../src_thesis/cooperation/implicit_cooperation.py) | 10 KPIs | B1 | **Adapt**: `grid_congestion` from line and transformer loading; supply-demand imbalance from external-grid exchange (the physical `B_grid`) |
| Metrics handlers | [cooperation/metrics/](../../../src_thesis/cooperation/metrics/) | Reporting | B2 | **Replace** `grid_metrics.py` inputs with the assessment history |
| `Plotter` | [cooperation/visualization/plotter.py](../../../src_thesis/cooperation/visualization/plotter.py) | Figures | B2 | Adapt: network plots from the grid backend's topology view |

The paper's Fig. 2 shows `DSOMetricsHandler` twice. The second box is `GridMetricsHandler` in the code.

## 4. Platform additions (not in the paper)

| Component | Location | Status | Doc |
|---|---|---|---|
| Grid contracts (`GridModel`, `GridAssessment`, `ParticipantInjection`, `GridViolation`) | [marketplace/grid/contract_new.py](../../../src_thesis/marketplace/grid/contract_new.py) | Extended to 02 §5, plus the catalog records (`NetworkRef`, `NetworkInfo`, `NetworkSummary`, `TopologyView`, `ElementRecord`); `GridModel` not yet implemented | 02 §5 |
| Settlement ledger (energy identity, battery, cash with fees) | `marketplace/settlement.py` | New | 02 §5.1, [audit §5](../validation/marlem-keep-replace-audit.md) |
| Settlement → injection builder | `marketplace/grid/injection.py` | New | 02 §7 |
| Scripted baseline policies (no order, random, rule-based) | `marl/baselines.py` | New | 03 §3.10 |
| pandapower grid adapter (SimBench, built-in, file) | [adapters/grid/simbench_new.py](../../../src_thesis/adapters/grid/simbench_new.py) | Catalog part done (2026-09-25): list, load, summary, topology, elements, one-hour power-flow preview for SimBench and built-in networks. Step-time `SimBenchGrid` still a stub. | 02 §1–§5 |
| SimBench profile source | `adapters/profiles/simbench.py` | New | 02 §3 |
| Experiment layer: file handling, expansion, resolution, manifest, store, recorder, worker, pool | [experiments/](../../../src_thesis/experiments/) | Implemented (2026-09-27); environment factory and RLlib configuration are interfaces until R1 / R4 and stage D | 03, 06 |
| Frozen reference copy | [src_thesis_reference/](../../../src_thesis_reference/) | Snapshot 2026-09-27, never edited | D-14 |
| Application services | [application/](../../../src_thesis/application/) | Demo services; the real `GridCatalogService` is [grid_catalog.py](../../../src_thesis/application/grid_catalog.py) | 04 |
| CLI | `src_thesis/cli.py` | New | 04 §6 |
| NiceGUI Studio | `studio/` (separate presentation package) | New | 05 |

## 5. Dependency direction (target)

```text
studio/ , cli.py , notebooks
        │
        ▼
application/  ──►  experiments/ (experiment file, factory, store, worker)
                          │
                          ▼
     marketplace/ ◄─── marl/          cooperation/
        │   (Level 0)     (Level 1)       (Level 2)
        ▼
   grid/contract (+ injection builder)
        ▲
        │ implements
   adapters/grid/simbench (pandapower)             adapters/profiles/{csv, synthetic, simbench}
```

- Only `adapters/` may import `simbench` or `pandapower`. Nothing imports NetworkX grid code any more.
- `marketplace/`, `marl/` and `cooperation/` never import `application/`, `experiments/` or `studio/`.
- `studio/` never imports `marketplace/`, `marl/` or `adapters/` directly.
