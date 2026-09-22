# MARLEM paper-to-code architecture map

> Status: standalone paper-aligned refactoring and migration map
>
> Scope of this revision: original behavior has one standalone implementation
> under `src_thesis/`. Existing `src/` modules remain the comparison baseline;
> `src_thesis/` neither imports from them nor retains mirrored compatibility
> modules.

This document maps the current `src` tree to the three conceptual levels shown
in Figure 2 of the MARLEM paper. It is intentionally separate from the target
platform architecture in [architecture.md](architecture.md): this file answers
"where is the current behavior?" and "what boundary must change for SimBench?"
before files are moved or responsibilities are extracted.

The paper diagram is a logical architecture, not a one-to-one package layout.
The current repository already contains most of the named classes, but several
of them are grouped differently and the Level 0 components are tightly coupled.

## 1. Reference and worktree scope

- Paper figure: [Figure 2 in `docs/paper/marlem.pdf`](../paper/marlem.pdf), page 7.
- Production/refactoring worktree: `marlem-dev`, branch `dev`.
- Validation/results worktree: `marlem`, branch `validation`.
- Baseline worktree: `marlem-main`, branch `main`.

Production source changes belong in `marlem-dev`. Validation experiments and
generated results belong in `marlem` after a stable `dev` milestone is merged.
The baseline is kept unchanged.

## 2. Current source tree, grouped by paper level

```text
src/
├── environment/                 # Mostly Level 0; also contains Level 1 RL code
│   ├── lem.py                   # LocalEnergyMarket, the environment orchestrator
│   ├── action.py                # ActionHandler
│   ├── observation.py           # ObservationHandler
│   ├── reward.py                # RewardHandler
│   ├── base.py                  # RLAlgorithm, TrainingMode, RLProtection
│   ├── train.py                 # RLTrainer, GroupedLEM, RLlib callbacks
│   ├── inference.py             # RLInference
│   └── io.py                    # Environment serialization/restoration
├── agent/                       # Level 1 MARL actors
│   ├── der.py                   # DERAgent
│   └── battery.py               # Battery, BatteryState
├── market/                      # Level 0 market and settlement components
│   ├── matching.py              # MarketConfig, MatchingResult, MatchingHistory,
│   │                             # OrderMatcher
│   ├── order.py                 # Order, Trade
│   ├── mechanism.py             # ClearingMechanism and pricing implementations
│   ├── dso.py                   # DSOAgent, fallback, fees, grid checks
│   ├── reputation.py            # ReputationHandler
│   └── validation.py             # Validator, TransactionBlock
├── grid/                        # Level 0 physical-grid model
│   ├── base.py                  # GridTopology, Location
│   ├── config.py                # Hand-written topology configurations
│   └── network.py               # GridNetwork and NetworkX flow approximation
├── coordination/                # Level 2 implicit cooperation model
│   └── implicit_cooperation.py  # ImplicitCooperation
├── analytics/                  # Level 2 and outcome metrics
│   ├── coordination_metrics.py  # CoordinationMetricsHandler
│   ├── dso_metrics.py           # DSOMetricsHandler
│   ├── grid_metrics.py          # GridMetricsHandler
│   └── market_analytics.py      # MarketMetricsHandler
├── profile/                    # Shared profile inputs used by Level 0/1
│   ├── base.py                  # ProfileHandler
│   ├── der.py                   # DERProfileHandler
│   └── dso.py                   # DSOProfileHandler
└── visualization/              # Level 2 reporting/presentation
    └── plotter.py               # Plotter
```

The tree above is an inventory of the current code. It is not a proposal to
move files immediately.

## 2.1 Historical mirrored-copy pass (superseded)

The material in this subsection records the first refactoring pass. That pass
temporarily mirrored original filenames and is retained here only as migration
history. The duplicate paths and compatibility wrapper have now been removed;
Section 2.2 is authoritative for the current tree.

`src_thesis/` now contains a complete physical copy of every non-empty Python
implementation module in `src/`, grouped under names that match the paper's
levels. Class bodies and algorithms are copied unchanged; imports are rewired
within `src_thesis/`. The old `src/` packages remain intact as the comparison
baseline.

```text
src_thesis/
├── marketplace/                # Level 0 copied implementation
│   ├── lem.py                  # LocalEnergyMarket
│   ├── action.py               # ActionHandler
│   ├── observation.py          # ObservationHandler
│   ├── reward.py               # RewardHandler
│   ├── io.py                    # Environment configuration I/O
│   ├── market/                 # Original six market modules mirrored 1:1
│   └── grid/                   # base.py, config.py, network.py mirrored 1:1
├── marl/                       # Level 1 copied implementation
│   ├── agent/                  # battery.py, der.py mirrored 1:1
│   ├── base.py                 # RLAlgorithm, TrainingMode, RLProtection
│   ├── ctce.py
│   ├── ctde.py
│   ├── train.py                # RLTrainer, GroupedLEM
│   └── inference.py            # RLInference
├── cooperation/                # Level 2 copied implementation
│   ├── coordination/           # implicit_cooperation.py
│   ├── analytics/              # Original four analytics modules mirrored 1:1
│   └── visualization/          # plotter.py
└── profile/                    # base.py, der.py, dso.py mirrored 1:1
```

Example structured imports are now available without invalidating old imports:

```python
from src_thesis.marketplace.lem import LocalEnergyMarket
from src_thesis.marketplace.market import MarketConfig, Order, Trade
from src_thesis.marl.agent import Battery, DERAgent
from src_thesis.cooperation.coordination import ImplicitCooperation
```

The copied tree does not solve the grid-coupling problem yet. It makes component
ownership and every concrete grid dependency visible while keeping inherited
behavior available for comparison.

### Copy progress

| Structured area | Status | Original area |
|---|---|---|
| `marketplace/` | Fully copied and internally wired | `environment/`, `market/`, grid-facing orchestration |
| `marl/` | Fully copied and internally wired | `agent/` and RL modules from `environment/` |
| `cooperation/` | Fully copied and internally wired | `coordination/`, `analytics/`, `visualization/` |
| `profile/` | Fully copied 1:1 | `profile/` |
| `marketplace/grid/` | Fully copied 1:1 | `grid/` |

This mirrored arrangement no longer exists in the working implementation.

## 2.2 Current standalone structure

```text
src_thesis/
|-- marketplace/
|   |-- lem.py
|   |-- action.py
|   |-- observation.py
|   |-- reward.py
|   |-- io.py
|   |-- market/       # matching.py, order.py, mechanism.py, etc.
|   |-- dso/          # DSO market role
|   `-- grid/         # grid-domain models and legacy topology config
|-- marl/
|   |-- agents/
|   |-- train.py
|   |-- inference.py
|   |-- base.py
|   |-- ctce.py
|   `-- ctde.py
|-- cooperation/
|   |-- implicit_cooperation.py
|   |-- metrics/
|   `-- visualization/
|-- adapters/
|   |-- grid/network.py
|   `-- profiles/
`-- root.py
```

Current imports use the structured API directly:

```python
from src_thesis.marketplace.lem import LocalEnergyMarket
from src_thesis.marketplace.market.matching import MarketConfig
from src_thesis.marketplace.market.order import Order, Trade
from src_thesis.marl.agents.battery import Battery
from src_thesis.marl.agents.der import DERAgent
from src_thesis.cooperation.implicit_cooperation import ImplicitCooperation
```

There is one implementation of each concept, and every inherited script keeps
the basename used in `src/`. Package `__init__.py` files are package markers,
not compatibility wrappers. The legacy NetworkX grid is already located in
`adapters/grid/`, although consumers still need a neutral grid contract before
the implementation can be replaced safely.

## 3. Figure 2 component map

### Level 0 - Platform Marketplace

| Paper component | Current implementation | Current responsibility | SimBench consequence |
|---|---|---|---|
| `LEM` / multi-agent environment | [`environment/lem.py`](../../src/environment/lem.py) | Owns agents, grid, DSO, matcher, handlers, profiles, reset, and step orchestration | Keep as the orchestration boundary; it should depend on a grid contract rather than `GridNetwork` directly |
| `ActionHandler` | [`environment/action.py`](../../src/environment/action.py) | Builds and validates action spaces and partner choices | Keep; only grid-dependent action checks need a new contract later |
| `ObservationHandler` | [`environment/observation.py`](../../src/environment/observation.py) | Builds observations from market, agent, DSO, and grid state | Keep the observation shape conceptually; replace legacy congestion/grid fields with named power-flow outputs when defined |
| `RewardHandler` | [`environment/reward.py`](../../src/environment/reward.py) | Combines trading, balance, economic, resource, stability, and cooperation rewards | Keep market/battery terms; defer or replace physical-grid terms after SimBench metrics are defined |
| `OrderMatcher` | [`market/matching.py`](../../src/market/matching.py) | Preference matching, price matching, DSO clearing, trade statistics, grid calls, settlement-related state, and audit logging | Main coupling hotspot. It must eventually consume a grid assessment instead of accessing paths, losses, or concrete grid state |
| `Order` | [`market/order.py`](../../src/market/order.py) | Submitted buy/sell order | Keep as an economic order. Location may remain participant metadata, but must not imply a shortest electrical path |
| `Trade` | [`market/order.py`](../../src/market/order.py) | Executed bilateral or DSO transaction, including `distance`, `transmission_loss`, and `fees` | Reconsider `distance` and per-trade `transmission_loss`; pandapower naturally produces system-level losses unless an allocation method is specified |
| `MatchingResult` | [`market/matching.py`](../../src/market/matching.py) | Market totals plus legacy grid fields `grid_balance` and `grid_congestion` | Split economic results from grid assessment or make the grid fields explicit derived outputs |
| `MatchingHistory` | [`market/matching.py`](../../src/market/matching.py) | Stores per-step matching results | Keep as a history contract, but record power-flow assessments separately or through a versioned result type |
| `MarketConfig` | [`market/matching.py`](../../src/market/matching.py) | Market bounds, pricing, preference, and blockchain settings | Extract later into market configuration; remove physical-grid assumptions from it |
| `ClearingMechanism` | [`market/mechanism.py`](../../src/market/mechanism.py) | Pricing mechanism implementations | Keep independent of NetworkX, pandapower, and SimBench |
| `DSOAgent` | [`market/dso.py`](../../src/market/dso.py) | Tariffs, residual clearing, DSO accounting, fees, congestion checks, and grid balance | Split market role from physical-grid policy. DSO should consume `GridAssessment`, not call grid methods |
| `ReputationHandler` | [`market/reputation.py`](../../src/market/reputation.py) | Reputation updates and partner ranking | Keep; its grid-impact term needs a later metric definition if it remains part of reputation |
| `Validator` / `TransactionBlock` | [`market/validation.py`](../../src/market/validation.py) | In-memory hash-chained trade log | Keep outside the physical-grid boundary; its scientific role should be revisited separately |
| `GridNetwork` | [`grid/network.py`](../../src/grid/network.py) | NetworkX topology, assignment, shortest paths, approximate losses, edge flow, and congestion | Replace the implementation behind a grid interface; do not let SimBench details enter market code |
| `GridTopology` / `Location` | [`grid/base.py`](../../src/grid/base.py) | Synthetic topology choices and coordinate/location data | Retain only as legacy/simplified-grid concepts; SimBench needs explicit bus identifiers and mapping metadata |

### Level 1 - MARL Agents

| Paper component | Current implementation | Current responsibility | Migration note |
|---|---|---|---|
| `DERAgent` | [`agent/der.py`](../../src/agent/der.py) | Generation/demand profiles, energy tracking, action adjustment, battery interaction, location | Keep the actor model; replace only the location/grid coupling when participant-to-bus mapping is introduced |
| `Battery` | [`agent/battery.py`](../../src/agent/battery.py) | SOC, charge/discharge limits, efficiency, and energy state | Keep; its energy boundary must be validated independently of the grid adapter |
| `RLAlgorithm` | [`environment/base.py`](../../src/environment/base.py) | Algorithm enum and RLlib module selection | Move later to a MARL package if useful; unrelated to SimBench |
| `TrainingMode` | [`environment/base.py`](../../src/environment/base.py) | CTCE, CTDE, and DTDE selection | Keep separate from grid implementation |
| `RLTrainer` | [`environment/train.py`](../../src/environment/train.py) | Ray/RLlib configuration, training, checkpoint selection, and persistence | Keep behind the simulation/environment boundary; do not add SimBench logic here |
| `RLInference` | [`environment/inference.py`](../../src/environment/inference.py) | Checkpoint restoration and action execution | Keep; power-flow outputs should arrive through the environment result/observation contract |
| `GroupedLEM` and callbacks | [`environment/train.py`](../../src/environment/train.py) | RLlib grouping and optimizer callbacks | Keep with training integration; validate agent ordering separately |

### Level 2 - Implicit Cooperation

| Paper component | Current implementation | Current responsibility | Migration note |
|---|---|---|---|
| `ImplicitCooperation` | [`coordination/implicit_cooperation.py`](../../src/coordination/implicit_cooperation.py) | Economic, grid-stability, coordination, and resource KPIs | Keep as a consumer of typed results; replace legacy congestion/imbalance inputs when physical metrics are defined |
| `CoordinationMetricsHandler` | [`analytics/coordination_metrics.py`](../../src/analytics/coordination_metrics.py) | Coordination signal and reward/outcome statistics | Keep, but audit formulas independently from the grid replacement |
| `DSOMetricsHandler` | [`analytics/dso_metrics.py`](../../src/analytics/dso_metrics.py) | DSO profit, avoided cost, local benefit, utilization, and fallback metrics | Keep market accounting metrics; distinguish DSO economics from physical grid metrics |
| `GridMetricsHandler` | [`analytics/grid_metrics.py`](../../src/analytics/grid_metrics.py) | Legacy congestion, distance-based loss, edge-flow, balance, and grid stability metrics | Replace its physical inputs with power-flow results; it is a deferred SimBench-dependent component |
| `MarketMetricsHandler` | [`analytics/market_analytics.py`](../../src/analytics/market_analytics.py) | Price, volume, liquidity, efficiency, and market trends | Keep independent of grid technology where possible |
| `Plotter` | [`visualization/plotter.py`](../../src/visualization/plotter.py) | Trading networks, distributions, grid/economic/DSO plots, and behavior plots | Keep as reporting; update plots after the metric contracts stabilize |

The paper figure shows `DSOMetricsHandler` twice. The repository's second
metrics component is `GridMetricsHandler`, which is the likely intended label
for the lower-right box in the figure.

## 4. Current dependency and coupling map

The important runtime path is currently:

```text
LocalEnergyMarket
  ├── DERAgent[] and Battery
  ├── GridNetwork
  ├── DSOAgent ───────────────┐
  ├── OrderMatcher ───────────┼── direct GridNetwork access
  ├── ActionHandler            │
  ├── ObservationHandler       │
  ├── RewardHandler            │
  └── ImplicitCooperation      │
                               ▼
                         NetworkX approximation
```

The direct grid-dependent calls that must be isolated are:

- `OrderMatcher` calculates shortest-path distance and transmission loss,
  checks a global capacity value, and updates DSO congestion state.
- `DSOAgent` calculates path congestion, distance-based voltage/thermal fees,
  and legacy grid-constraint decisions.
- `RewardHandler` receives a concrete `GridNetwork` and uses grid state in the
  reward calculation.
- `ObservationHandler` receives a concrete `GridNetwork` and exposes legacy
  congestion/grid values.
- `GridMetricsHandler` reads `edge_flows`, `edge_capacities`, and per-trade
  transmission-loss fields.
- `DERAgent`, `Location`, and partner-selection code can use the NetworkX graph
  for distance or preferred-partner behavior.
- `visualization/plotter.py` imports NetworkX for the trading-network view.

This is why a package-only move cannot by itself make SimBench replaceable.
The physical model is currently part of the market algorithm's behavior.

## 5. Proposed replacement boundary

The first new abstraction should be small and implementation-neutral:

```text
marketplace/environment orchestration
              |
              v
          GridModel
           /     \
          /       \
legacy NetworkX   SimBench + pandapower
```

The target contract should be introduced only after the current behavior is
characterized. A conceptual version is:

```python
class GridModel(Protocol):
    def reset(self, step: int | None = None) -> None: ...

    def map_participants(self, participant_bus: dict[str, str]) -> None: ...

    def assess(
        self,
        trades: list[Trade],
        timestep_hours: float,
    ) -> GridAssessment: ...

    def commit(self, assessment: GridAssessment) -> None: ...
```

The result should carry physical outputs without exposing a solver:

```python
@dataclass(frozen=True)
class GridAssessment:
    feasible: bool
    total_losses_kwh: float
    bus_voltages_pu: dict[str, float]
    line_loading_percent: dict[str, float]
    transformer_loading_percent: dict[str, float]
    congestion_score: float
    violations: tuple[GridViolation, ...]
```

These names are design targets, not code added by this mapping pass. The
contract still needs decisions about sign conventions, units, timestep, failed
power-flow behavior, and trade acceptance policy.

## 6. SimBench integration map

SimBench should replace the physical-grid implementation, not the economic
market mechanism.

| Existing concern | Current location | Target owner | SimBench treatment |
|---|---|---|---|
| Synthetic topology construction | `grid/network.py`, `grid/config.py` | Legacy grid adapter | Preserve temporarily for characterization; later retire or keep as a test backend |
| Participant placement | `GridNetwork.assign_agents_to_graph` and `DERAgent.node_id` | Grid mapping adapter | Map stable participant IDs to pandapower bus indices/names explicitly |
| Bilateral shortest path | `OrderMatcher`, `Location.distance_to` | No direct market equivalent | Remove from physical feasibility; power flow determines network response |
| Distance-based loss | `GridNetwork.transmission_loss`, `Trade.transmission_loss` | Pandapower result extraction plus explicit allocation policy | Do not silently reuse shortest-path loss; define whether losses are system-level or allocated |
| Edge flow/congestion | `GridNetwork.edge_flows`, `get_path_congestion` | Power-flow result adapter | Use line and transformer loading percentages and a documented aggregate congestion score |
| Global capacity check | `OrderMatcher`, `DSOAgent` | Grid constraint policy | Replace with voltage, thermal, transformer, and any feeder/import constraints |
| Grid-related fees | `DSOAgent.calculate_fees` | Grid fee policy | Consume `GridAssessment`; define which fees are economic policy versus physical penalty |
| Grid reward terms | `RewardHandler` | Reward policy over typed assessment | Rebuild from validated physical metrics; do not preserve legacy formulas automatically |
| Grid observation fields | `ObservationHandler` | Observation projection | Add only values available at the observation time and document public/private scope |
| Grid metrics | `analytics/grid_metrics.py` | Power-flow metrics handler | Replace legacy edge-flow and distance-loss calculations with auditable formulas |

The intended step sequence is:

```text
actions
  -> orders
  -> economic matching
  -> provisional trades
  -> aggregate participant injections by bus
  -> pandapower power flow
  -> explicit accept / curtail / reject policy
  -> settlement
  -> rewards, observations, and recorded metrics
```

The accept/curtail/reject rule is part of the research model. It must be
decided and documented before the SimBench adapter is used for thesis claims.

## 7. Recommended non-destructive development sequence

### A. Map and freeze the boundary

This document is the output of this step. No source relocation is needed yet.

### B. Add characterization coverage

Record current outputs around `OrderMatcher`, `DSOAgent`, environment stepping,
and grid metrics. These tests preserve migration safety; they are not claims
that the legacy grid is physically correct.

### C. Add a grid contract and an unconstrained test double

Introduce `GridModel`, `GridAssessment`, and an `UnconstrainedGrid` in a small,
stable module. Use the unconstrained implementation to test market behavior
without physical constraints.

### D. Wrap the current grid

Add a `LegacyNetworkXGrid` adapter that delegates to `GridNetwork`. Change the
market/environment boundary to depend on the adapter contract while preserving
the old implementation and old import paths.

### E. Remove concrete-grid access from market logic

Only after the adapter is characterized should `market/` stop importing
`GridNetwork`, reading `.graph`, calculating shortest paths, or deriving
distance-based losses. This is the key SimBench-readiness gate.

### F. Add and test the SimBench adapter

Test loading, bus mapping, injection signs, units, timestep conversion,
convergence, voltage limits, line/transformer limits, losses, reset behavior,
and non-convergence handling independently from RL training.

### G. Replace grid-dependent metrics and rewards

Define each physical metric's meaning, formula, unit, input source, interval,
range, and failed-power-flow behavior. Then update rewards, observations, and
coordination KPIs deliberately.

### H. Preserve the standalone boundary during extraction

Keep `src/` unchanged as the historical comparison baseline. Implement and test
new boundaries only in `src_thesis/`; do not add fallback imports or forwarding
wrappers to the original package.

## 8. Decisions deferred on purpose

- Whether `Trade` keeps per-trade distance, loss, and fee fields.
- Whether grid assessment happens once per clearing or once per accepted trade.
- Whether violations cause whole-market rejection, proportional curtailment,
  selective curtailment, rematching, or redispatch.
- How system losses are allocated to trades, agents, or the DSO.
- Whether congestion is a maximum loading, mean loading, percentile, or another
  aggregate score.
- Which power-flow outputs are public observation signals.
- Whether the legacy NetworkX grid remains as a baseline backend after SimBench.
- The final package names for `marketplace`, `marl`, and infrastructure adapters.

These are model decisions, not file-organization details, and should not be
hidden inside a refactor.

## 9. Immediate acceptance criteria for this map

- Every class visible in Figure 2 has a current code location or an explicit
  paper/repository mismatch note.
- The current NetworkX coupling points are listed.
- The SimBench replacement boundary is stated independently of package names.
- No existing `src/` implementation module was moved or rewritten.
- Every inherited behavior has one implementation home under `src_thesis/`.
- Imports resolve within `src_thesis/`; no module imports or delegates to
  `src/`.
- The inherited NetworkX implementation is isolated in
  `src_thesis/adapters/grid/network.py`.
- Future packaging work can be reviewed separately from physical-model changes.
