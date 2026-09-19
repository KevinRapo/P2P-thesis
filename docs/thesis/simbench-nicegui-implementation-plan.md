# SimBench and NiceGUI implementation plan

> Status: implementation-ready plan; no production integration is claimed  
> Target worktree: `marlem-baseline`  
> Last updated: 2026-09-19

## 1. Outcome

The target is one reproducible MARLEM application in which the same versioned
scenario can be validated and run from a CLI or NiceGUI, using either:

- the restored legacy NetworkX transport backend for comparison; or
- a SimBench/pandapower AC assessment backend.

The first complete vertical slice is deliberately small:

```text
load a checked-in scenario JSON
-> validate schema, data, mapping, units, and resources
-> run four deterministic timesteps in a worker process
-> settle household energy and cash with the restored baseline
-> assess each settled operating point with SimBench/pandapower in shadow mode
-> persist manifest, status, raw settlement, and grid result files
-> inspect the same run through CLI and NiceGUI
```

Only after that slice is stable should the full Case 6 3 × 3 matrix be launched
through Studio. The matrix is a workflow test until independent evidence shows
learning and useful held-out performance.

## 2. Scope

### Included

- a technology-neutral physical-grid result contract;
- an explicit MARLEM-participant-to-SimBench mapping;
- correct kWh-to-kW conversion and background-profile handling;
- one pandapower solve per settled market timestep;
- raw physical result persistence and constraint findings;
- a versioned scenario/manifest/status model;
- filesystem experiment storage;
- an application-service layer shared by CLI and NiceGUI;
- a separate process for simulation/training;
- read-only run/result views, then scenario editing and training controls;
- tests from small contracts through one end-to-end Studio-equivalent run.

### Excluded from the first implementation

- claiming that an AC-converged operating point is optimal or market-feasible;
- per-trade AC power-flow solves;
- AC optimal power flow, redispatch, or topology control;
- automatic rejection/reclearing of trades after a grid violation;
- assigning system losses to individual P2P trades without a documented rule;
- changing RL observation or reward dimensions in the first SimBench slice;
- a public REST API, database, queue, authentication, or multi-user deployment;
- moving the restored runtime into `src_thesis` or a new top-level package;
- using the UI's browser session as authoritative experiment storage.

## 3. Non-negotiable design decisions

### 3.1 Economic transport and physical assessment are different contracts

The current `GridNetwork` participates inside `OrderMatcher`: it limits fills,
computes a delivery fraction, assigns a distance/loss to each trade, mutates
edge flows, and influences DSO fees. SimBench instead evaluates the aggregate
nodal operating point after all trades and battery actions have settled.

Therefore define two boundaries:

```text
OrderMatcher ---> TradeTransportPolicy
                     |-- LegacyGraphTransport
                     `-- LosslessMarketTransport (initial SimBench mode)

LocalEnergyMarket ---> PhysicalGridModel
                         |-- LegacyGridAssessment
                         `-- SimBenchGridAssessment
```

`TradeTransportPolicy` answers market-allocation questions such as maximum
source quantity and delivered quantity. `PhysicalGridModel` receives settled
participant injections and returns aggregate physical results. Pandapower must
not implement fake per-trade paths merely to match the legacy API.

The initial SimBench-native market policy is lossless at the trade record:
source quantity equals delivered quantity and no electrical loss is assigned
to an individual trade. Actual feeder losses are supplied through the external
grid and reported in `GridAssessment`. Any future loss-allocation/cost policy
must be separately named, versioned, and tested.

### 3.2 SimBench begins in shadow mode

The first integrated mode records power-flow outcomes but does not change:

- accepted orders or trades;
- cash settlement;
- reward;
- observation vectors; or
- episode termination, except that a solver exception makes the run fail
  clearly rather than returning fabricated values.

Shadow mode gives paired legacy/physical evidence without changing the learner's
problem. Later modes may add a physical penalty or truncate a non-convergent
episode, but only after their equations are reviewed. A mode that rejects or
reclears trades requires a separate constrained-clearing design and is not an
MVP toggle.

### 3.3 One solve per complete settled timestep

The call belongs after `DERAgent.settle_energy` has created all household
settlements and before cooperation KPIs, rewards, next observations, and the
returned `info` are constructed:

```text
actions
-> validated orders
-> economic matching and cash settlement
-> household/battery energy settlement
-> participant injection construction
-> physical-grid assessment       <-- new
-> KPI/reward calculation
-> reputation and next observation
-> append raw step records
```

Do not solve after every bilateral trade. P2P trades are economic transfers;
the feeder sees their resulting nodal injections.

### 3.4 Persist specifications, not live objects

RLlib copies and serializes environment configurations. A pandapower net is
large, mutable, and unsuitable as a scenario or manifest field. Persist only a
`GridSpec` and mapping. Each environment process builds its own adapter and
receives a defensive copy of a process-local cached source network.

### 3.5 Preserve the legacy backend

Legacy mode remains available for:

- regression tests against the restored baseline;
- characterization of behavior changes;
- fast non-electrical training runs; and
- a clearly labelled abstract-grid comparator in the thesis.

It must be called `legacy` or `abstract`, not `IEEE power flow`.

## 4. Contracts

Use Pydantic models for versioned scenario/application contracts and frozen
dataclasses for hot-path step results. Pin the supported Pydantic major version
when dependencies are added.

### 4.1 Scenario models

```python
class ScenarioSpec(BaseModel):
    schema_version: Literal["1.0"]
    scenario_id: str
    name: str
    timestep_minutes: int
    horizon_steps: int
    seed: int
    agents: list[AgentSpec]
    market: MarketSpec
    grid: GridSpec
    learning: LearningSpec | None
    evaluation: EvaluationSpec | None

class GridSpec(BaseModel):
    physical_backend: Literal["legacy", "simbench"]
    transport_mode: Literal["legacy_graph", "lossless"]
    assessment_mode: Literal["shadow", "penalize"] = "shadow"
    simbench_code: str | None
    profile_mode: Literal["mapped_replacement", "no_background"]
    mappings: list[ParticipantGridMapping]
    min_voltage_pu: float = 0.95
    max_voltage_pu: float = 1.05
    max_line_loading_percent: float = 100.0
    max_transformer_loading_percent: float = 100.0

class ParticipantGridMapping(BaseModel):
    participant_id: str
    bus_id: int
    owned_load_id: int | None
    owned_sgen_id: int | None
    reactive_power_mode: Literal["profile_ratio", "fixed_power_factor"]
    fallback_power_factor: float = 0.95
```

`ScenarioSpec` becomes the only UI/CLI input. A factory converts it to the
current object-based `env_config`. Existing notebook helpers may call the same
factory; Studio must not introduce a second Case 6 builder.

The supported combinations are explicit:

| Mode | Transport | Physical assessment | Purpose |
|---|---|---|---|
| Restored baseline | `legacy_graph` | `legacy` | Preserve and characterize current behavior |
| Shadow comparison | `legacy_graph` | `simbench` | Add AC diagnostics without changing current market allocation |
| SimBench-native assessment | `lossless` | `simbench` | Avoid counting legacy per-trade loss as well as feeder loss |

The hybrid shadow comparison can contain both legacy delivery loss and measured
feeder loss. That is intentional diagnostic output, not one combined conserved
physical model. Only the SimBench-native mode is eligible for later physical
claims, after its upstream-loss and constraint policies are approved.

### 4.2 Participant injection

```python
@dataclass(frozen=True)
class ParticipantInjection:
    participant_id: str
    bus_id: int
    generation_kwh: float
    served_demand_kwh: float
    battery_charge_kwh: float
    battery_discharge_kwh: float
    curtailed_generation_kwh: float
    production_kw: float
    consumption_kw: float
    net_injection_kw: float
```

For timestep duration `h`:

```text
production_kw = (generation - curtailment + battery_discharge) / h
consumption_kw = (served_demand + battery_charge) / h
net_injection_kw = production_kw - consumption_kw
```

An invariant test must show `net_injection_kwh == exported - imported` within
tolerance for every participant. This prevents market purchases/sales from
being double-counted as additional load/generation.

### 4.3 Grid assessment

```python
@dataclass(frozen=True)
class GridViolation:
    code: str
    severity: Literal["warning", "error"]
    element_type: str
    element_id: str | None
    observed: float | None
    limit: float | None
    message: str

@dataclass(frozen=True)
class GridAssessment:
    backend: str
    step: int
    timestamp: str | None
    converged: bool
    min_voltage_pu: float | None
    max_voltage_pu: float | None
    max_line_loading_percent: float | None
    max_transformer_loading_percent: float | None
    line_losses_kw: float | None
    transformer_losses_kw: float | None
    total_losses_kw: float | None
    total_losses_kwh: float | None
    external_grid_p_kw: float | None
    external_grid_energy_kwh: float | None
    participant_injections: tuple[ParticipantInjection, ...]
    violations: tuple[GridViolation, ...]
```

The summary object is safe for environment `info` and status snapshots. Full
per-bus voltage, line/transformer loading, and pandapower diagnostic tables go
to raw artifact files; they do not enlarge RL observations or expose the net.

### 4.4 Adapter surface

```python
class PhysicalGridModel(Protocol):
    def validate(self, participant_ids: Sequence[str], timestep_hours: float) -> list[GridViolation]: ...
    def reset(self, *, episode_seed: int | None = None) -> None: ...
    def assess(self, step: int, injections: Sequence[ParticipantInjection]) -> GridAssessment: ...
    def network_summary(self) -> NetworkSummary: ...
    def topology_view(self) -> TopologyView: ...
```

The domain layer may import these contracts. Only the SimBench adapter module
may import `simbench` or `pandapower`.

## 5. SimBench adapter behavior

### 5.1 Network loading and isolation

- Load with `simbench.get_simbench_net(simbench_code)`.
- Cache only the parsed, immutable source net per process.
- Give each environment/episode its own defensive working copy.
- Apply one explicit profile row before participant overrides.
- Never share a mutated net between RLlib environments.
- Validate that profile row counts and timestamps agree across load, reactive
  load, and static generation profiles.

### 5.2 Mapping and background elements

The MVP uses `mapped_replacement`:

1. Every participant maps to one SimBench bus and explicitly declares the
   existing load/static-generator elements it owns, if any.
2. Apply the selected SimBench profile row to all elements.
3. Replace each owned load's active/reactive value with participant consumption.
4. Replace an owned static generator with participant production; if none is
   owned, create one deterministic controllable static generator at that bus
   during adapter construction.
5. Leave unmapped elements as background demand/generation.

This avoids counting both the original mapped element and the MARLEM
participant. `no_background` is a small deterministic test mode that zeros
unmapped loads/generators and is not the default research feeder.

Mapping validation rejects:

- unknown participant, bus, load, or generator IDs;
- the same owned element assigned twice;
- owned load/generator elements on a different bus from the mapping;
- missing mappings for active MARLEM participants;
- invalid power factor or constraint bounds;
- timestep/profile resolutions that have no declared alignment rule.

Use two checked-in mappings rather than a random assignment:

- integration fixture: `1-LV-rural1--0-sw`, three synthetic participants
  owning loads `0`, `1`, and `2`; participant 1 may also own static generator
  `2` after the adapter verifies that it is on the same bus;
- eight-participant candidate: `1-LV-semiurb4--0-sw`, chosen because the
  prototype already treats it as the representative feeder and it has enough
  loads for Case 6. Its final eight mappings must be selected and documented
  from feeder metadata/profile roles, then committed as scenario data. Do not
  assign the paper's IEEE-34 node labels directly to unrelated SimBench bus IDs.

### 5.3 Time alignment

The first integrated SimBench fixture uses `timestep_minutes=15` and
`time_step_hours=0.25`, matching the native SimBench profiles. This exercises
the restored timestep propagation directly.

Attaching the current hourly Case 6 profiles requires an explicit policy:

- preferred: build a separate 15-minute scenario from mapped SimBench data; or
- aggregate four consecutive SimBench rows into one hourly background point
  using energy-consistent averaging and record the row range.

Do not silently select every fourth row or reuse a 15-minute power value as an
hourly energy quantity.

### 5.4 Reactive power

For consumption, preserve the mapped load profile's `q/p` ratio after replacing
active power. If the profile active power is zero, use the mapping's fixed
lagging power factor. Participant generation and battery effects are unity
power factor in the MVP. These assumptions belong in the manifest and can be
expanded later.

### 5.5 Solve and constraints

Run `pandapower.runpp` once using Newton-Raphson, with deterministic options
recorded in the manifest. Extract:

- min/max bus voltage;
- maximum line and transformer loading;
- line, transformer, and total active-power loss;
- external-grid active power;
- full bus/line/transformer result rows for raw artifacts.

Convergence is necessary but not sufficient. Add violations for voltage below
or above the configured bounds and loading above 100% or the configured limit.

In shadow mode:

- a converged but violated point is recorded and the environment continues;
- a solver exception/nonconvergence fails the deterministic simulation run;
- for later RL robustness, a separately designed policy may truncate the
  episode with a fixed penalty, but it must never substitute zeros or stale
  results.

## 6. Baseline code changes

The intended source layout is additive:

```text
src/
|-- grid/
|   |-- contracts.py          # injections, assessment, violations, summaries
|   |-- transport.py          # TradeTransportPolicy and implementations
|   |-- legacy_adapter.py     # wraps current GridNetwork behavior
|   |-- simbench_adapter.py   # only production SimBench/pandapower imports
|   `-- network.py            # retained legacy implementation
|-- application/
|   |-- models.py             # scenario, validation, manifest, status models
|   |-- scenario_service.py
|   |-- validation_service.py
|   |-- experiment_service.py
|   `-- result_service.py
|-- experiments/
|   |-- factory.py            # ScenarioSpec -> current env_config
|   |-- store.py
|   |-- runner.py
|   |-- worker.py
|   `-- cli.py
`-- studio/
    |-- app.py
    |-- layout.py
    |-- state.py
    |-- pages/
    |   |-- dashboard.py
    |   |-- scenarios.py
    |   |-- grid.py
    |   |-- runs.py
    |   |-- results.py
    |   `-- training.py
    `-- components/
        |-- findings.py
        |-- status.py
        `-- charts.py
```

Specific current files change as follows:

| File | Planned change |
|---|---|
| `src/environment/lem.py` | Accept constructed transport/assessment backends; build injections after settlement; assess before KPIs/rewards; expose assessment summary in `info` |
| `src/market/matching.py` | Depend on `TradeTransportPolicy`, not `GridNetwork`; keep economic matching and cash ledger here |
| `src/market/dso.py` | Split tariff/residual market behavior from legacy graph fee/constraint queries; physical status becomes an input, not live graph access |
| `src/market/order.py` | Keep economic trade fields; retain legacy distance/loss only for legacy transport and mark their provenance |
| `src/environment/observation.py` | No shape change in shadow mode; later consume a versioned fixed-size physical summary |
| `src/environment/reward.py` | No change in shadow mode; later use a named physical penalty configuration |
| `src/coordination/implicit_cooperation.py` | Continue current baseline inputs first; later distinguish legacy congestion from AC violations |
| `src/environment/io.py` | Add versioned grid spec/mapping serialization; never serialize a pandapower net |
| `src/scenario.py` | Keep canonical Case 6 builder; add adapters from versioned specs and a separate SimBench smoke scenario |
| `src/analytics/grid_metrics.py` | Rebuild only after raw `GridAssessment` history is stable; do not mix legacy congestion and AC loading under one unlabeled metric |
| `environment.yml` | Add compatible, pinned NiceGUI, SimBench, pandapower, and Pydantic constraints after an isolated dependency compatibility check |

## 7. Experiment and application layer

### 7.1 Experiment store

Use a configurable directory outside OneDrive for heavy run data when possible.
Each run is immutable except for documented status/progress streams:

```text
experiments/<run_id>/
|-- scenario.json
|-- manifest.json
|-- validation.json
|-- status.json
|-- artifacts.json
|-- cancellation.request
|-- logs/
|   |-- worker.log
|   `-- ray/
|-- raw/
|   |-- settlements.jsonl
|   |-- trades.jsonl
|   |-- grid_assessments.jsonl
|   |-- bus_results.parquet
|   |-- line_results.parquet
|   `-- transformer_results.parquet
|-- metrics/
|   |-- training.csv
|   |-- evaluation.json
|   `-- per_episode.jsonl
|-- checkpoints/
`-- figures/
```

Use JSON/JSONL initially for contracts and streams. Parquet is appropriate for
dense physical tables only if its dependency is deliberately added; otherwise
use CSV. Small state files are written to a sibling temporary file and replaced
atomically. `manifest.json` includes hashes of the scenario, mapping, datasets,
code revision/dirty-state evidence, dependencies, solver configuration, seed
schedule, and final artifacts.

Run states are controlled by `ExperimentService`:

```text
DRAFT -> VALIDATING -> INVALID
                    -> READY -> RUNNING -> COMPLETED
                                        -> FAILED
                                        -> CANCELLING -> CANCELLED
```

### 7.2 Services

| Service | Required first methods |
|---|---|
| `ScenarioService` | `create`, `load`, `save`, `clone`, `list`, `canonical_hash` |
| `ValidationService` | `validate_schema`, `validate_data`, `validate_grid`, `validate_resources`, `validate_protocol` |
| `ExperimentService` | `create_run`, `start`, `request_cancel`, `snapshot`, `list_runs`, `reconcile_stale_run` |
| `ResultService` | `summary`, `grid_series`, `training_series`, `artifact_index`, `compare_runs` |

Services return typed values and plain serializable chart data. They never
return NiceGUI elements, Ray result objects, or pandapower nets.

### 7.3 Worker process

Start a run with:

```text
python -m src.experiments.worker --run-dir <absolute-run-directory>
```

The worker:

1. reads the frozen scenario/manifest;
2. verifies their hashes;
3. updates status to `RUNNING` atomically;
4. constructs the environment inside the child;
5. owns Ray initialization/shutdown if training is selected;
6. appends progress, logs, settlements, and assessments;
7. checks `cancellation.request` at safe iteration/episode boundaries;
8. writes the artifact index and terminal status in `finally` handling.

On Windows create a new process group so cancellation reaches only the owned
worker. Never use a broad process-name kill. A forced kill is a timed fallback
after graceful cancellation and is recorded in status.

## 8. NiceGUI layer

### 8.1 Page sequence

Build pages in this order:

1. **Dashboard (`/`)** — repository/environment warning, recent persistent
   runs, and links to scenarios/results.
2. **Runs (`/runs`)** — read-only filesystem-backed run table, status, logs,
   and cancellation request.
3. **Results (`/results/{run_id}`)** — persisted market, settlement, physical,
   and training series. Clearly separate RL reward from research outcomes.
4. **Grid inspector (`/grid`)** — calls the production grid service for network
   summary, topology, mapping, profile row, and one non-training solve.
5. **Scenarios (`/scenarios`)** — typed editor/import/export and validation
   findings; it edits `ScenarioSpec`, not live agents/nets.
6. **Training (`/training`)** — creates a run through `ExperimentService` and
   starts the worker. It does not construct `RLTrainer` in a callback.

### 8.2 UI rules

- One shared shell controls navigation, page width, theme, and error display.
- Form-level validation only handles required/parseable input. Scientific and
  protocol validation comes from `ValidationService` with stable finding codes.
- Poll snapshots every 1–2 seconds; do not assume the browser received every
  transition.
- Browser refresh/close does not affect a worker.
- Show logs and failure details with the run ID and artifact paths.
- Use Plotly for interactive previews. Raw persisted data, not downsampled
  browser series, is the evidence source.
- Default resources conservatively to CPU and one job. Do not default to a GPU
  merely because the prototype did.
- Disable unvalidated algorithms, grid modes, and reward options rather than
  presenting a working-looking control.

## 9. Implementation slices and gates

### Slice 0 — Freeze the baseline

Work:

- run and record the complete current test suite;
- run one bounded Case 6 combination and one short 3 × 3 workflow check;
- save current scenario/config hashes and one deterministic episode trace;
- confirm the working tree's unrelated notebook/training changes are preserved.

Gate:

- existing tests pass from a cleared Python process;
- the trace includes orders, trades, household settlements, cash, rewards,
  observations, and legacy grid state;
- no SimBench/NiceGUI dependency or behavior change yet.

### Slice 1 — Contracts and injection builder

Work:

- add frozen grid result/injection types;
- implement the settlement-to-injection formula;
- add `GridSpec` and mapping validation;
- add JSON round-trip and canonical hashing.

Tests:

- hand-computed import, export, charge, discharge, curtailment, and 15-minute
  cases;
- injection identity against `EnergySettlement`;
- invalid mapping and schema migrations;
- no pandapower import required for contract tests.

Gate:

- two-agent, two-step fixtures conserve energy and produce exact expected kW;
- spec JSON round-trips byte-stably after canonical formatting.

### Slice 2 — Extract the legacy seam without behavior change

Work:

- introduce `TradeTransportPolicy`;
- wrap all current `GridNetwork` path/loss/capacity calls;
- add `LegacyGridAssessment` over existing state;
- remove concrete `GridNetwork` type checks from consumers one at a time.

Tests:

- characterization tests compare old and wrapped trades, losses, cash,
  congestion, rewards, and observations with fixed actions/seeds;
- all baseline tests and the deterministic trace remain equal.

Gate:

- legacy outputs match within declared numeric tolerance;
- `OrderMatcher` and DSO no longer need a concrete `GridNetwork` import for
  transport operations.

### Slice 3 — Production SimBench adapter, still standalone

Work:

- port the useful prototype logic into `src/grid/simbench_adapter.py`;
- remove UI state and illustrative-agent assumptions;
- implement mapping, background replacement, reactive assumptions, thresholds,
  raw result extraction, and topology/summary views.

Tests:

- smallest feeder smoke solve;
- recommended feeder mapping and profile row;
- duplicate/invalid mapping rejection;
- active and reactive override behavior;
- voltage/loading/loss/ext-grid extraction;
- repeated reset/solve isolation;
- nonconvergence/error propagation;
- 15-minute energy conversion.

Gate:

- the adapter has no imports from environment, market, RL, application, or UI;
- every public return value is typed and serializable;
- a fresh solve never depends on a previous solve's mutation.

### Slice 4 — Integrated shadow assessment

Work:

- add the post-settlement call in `LocalEnergyMarket.step`;
- store the assessment summary in `matching`/`info` without changing observation
  or reward shape;
- append raw settlement and grid result records;
- add a deterministic four-step SimBench scenario.

Tests:

- one solve occurs per completed period;
- mapped net injection equals export minus import;
- buying/selling is not double-counted;
- background mapped elements are replaced, not added;
- raw records reconstruct every summary;
- legacy-only tests run without SimBench installed when optional dependency
  boundaries are used, if that packaging choice is retained.

Gate:

- the four-step scenario converges and produces finite, physically labelled
  results;
- shadow mode leaves economic trades, cash, rewards, and observations identical
  to a run using the same selected transport policy without AC assessment;
- violations are recorded with stable codes.

### Slice 5 — Scientific reconciliation

Work:

- decide and document the physical-grid research mode;
- define whether voltage/loading violations are outcome metrics, reward
  penalties, episode truncations, or inputs to a constrained clearing method;
- rebuild grid metrics from raw assessments;
- add fixed-size observation/reward fields only behind a schema version.

Required decisions:

- loss cost and allocation;
- upstream import/export cash treatment;
- treatment of nonconvergence during training;
- physical penalty weights and bounds;
- what information is public to agents and at what causal time;
- participant mapping for the thesis scenario;
- hourly Case 6 versus native 15-minute scenario.

Gate:

- every reported physical metric has a formula, unit, raw source, and test;
- legacy congestion and AC loading are never plotted under the same unlabeled
  metric;
- reward/observation changes have explicit versioned baselines and ablations.

### Slice 6 — Experiment store, CLI, and worker

Work:

- implement application models/services and atomic filesystem store;
- implement deterministic simulation worker first, then RL training;
- implement cancellation and stale-run recovery;
- expose the same commands through `python -m src.experiments.cli`.

Tests:

- legal/illegal status transitions;
- atomic state writes and corrupt/incomplete run handling;
- manifest/data/artifact hashes;
- child completion, failure, and cancellation;
- one tiny end-to-end run in a temporary store;
- worker restart does not depend on browser state.

Gate:

- a CLI-created run is fully inspectable from files alone;
- a failed run preserves its manifest, log, partial raw records, and error;
- the worker owns and shuts down only its Ray runtime.

### Slice 7 — Read-only Studio and grid inspector

Work:

- add NiceGUI dependency and app shell;
- implement dashboard, runs, results, and grid inspector;
- use service fakes for UI tests and the real services for one smoke path.

Gate:

- Studio can be closed/reopened while a worker continues;
- its result values equal CLI/`ResultService` values for the same run;
- no page imports pandapower, SimBench, `LocalEnergyMarket`, or `RLTrainer`.

### Slice 8 — Scenario editor and training controls

Work:

- add typed scenario editor/import/export;
- display validation findings and block invalid runs;
- create/start/cancel training runs through `ExperimentService`;
- expose the baseline 3 × 3 selection with resource/runtime warnings.

Gate:

- JSON created by Studio is identical to the CLI canonical form;
- Case 6 uses `src/scenario.py` through the common factory;
- one bounded 3 × 3 workflow run produces nine independent manifests/statuses;
- UI labels the run as an execution/learning check, not demonstrated learning.

### Slice 9 — Evidence run

Work:

- benchmark complete environment steps with and without AC assessment;
- choose feasible training budgets using measured solver + market + Ray cost;
- run independent seeds, held-out evaluation, and non-learning comparators;
- export thesis figures from persisted raw records.

Gate:

- source, data, mapping, dependencies, seeds, solver options, and checkpoints
  are verifiable from manifests;
- reported intervals come from raw seed-level records;
- learning claims require changed policy parameters and better held-out outcomes
  than named comparators, not merely a completed training loop.

## 10. Test layout

Add tests alongside the existing suite:

```text
tests/
|-- test_grid_contracts.py
|-- test_grid_injections.py
|-- test_grid_transport_compatibility.py
|-- test_simbench_adapter.py
|-- test_simbench_environment_integration.py
|-- test_scenario_models.py
|-- test_validation_service.py
|-- test_experiment_store.py
|-- test_experiment_worker.py
|-- test_result_service.py
|-- test_studio_pages.py
`-- test_studio_end_to_end.py
```

Keep expensive markers explicit:

- fast contract/domain tests on every change;
- SimBench solves in the normal integration gate if runtime remains small;
- real RL checkpoint tests in the existing slower gate;
- browser interaction only where it proves wiring not covered by service tests;
- full matrices and multi-seed evidence as scheduled/manual research runs, not
  ordinary unit tests.

## 11. Performance plan

Measure before selecting training scale:

1. cached net construction and defensive-copy time;
2. first/cold power flow;
3. warm median and p95 solve time per feeder;
4. complete `env.step` time with market, settlement, and assessment;
5. memory per environment runner;
6. Ray throughput for 1, 2, 4, and 6 environment runners;
7. total runtime for each algorithm/training mode, since the existing baseline
   already shows substantial differences.

Do not assume more runners improve throughput: each runner owns a mutable net,
and serialization/memory can dominate. Keep the legacy backend for fast
learning experiments when physical assessment is not part of the question.

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| SimBench changes several model semantics at once | Shadow mode, legacy characterization, and separate transport/assessment contracts |
| Purchase/sale double-counting | Build injections only from `EnergySettlement`; assert export-minus-import identity |
| Background profile double-counting | Explicit ownership and `mapped_replacement` validation |
| 15-minute versus hourly unit error | Native 15-minute first fixture; explicit aggregation metadata for hourly use |
| Mutable net leaks between envs/episodes | Process-local cached source plus defensive working copy and reset isolation tests |
| Large RLlib config or serialization failure | Persist `GridSpec`; construct adapters inside each worker environment |
| AC convergence mistaken for valid operation | Separate convergence from voltage/loading violations |
| Post-settlement violation called “constraint enforcement” | Label as assessment/penalty until a reclearing or OPF method exists |
| UI diverges from notebooks/CLI | One scenario factory and shared application services |
| NiceGUI or browser failure kills training | Owned worker process and filesystem status source of truth |
| Cancellation kills unrelated work | Per-run process group, cancellation file, targeted PID, timed fallback |
| Dependency upgrade breaks Ray/NumPy stack | Isolated environment compatibility slice before committing pins |
| Results look like learning without learning | Separate workflow, parameter-update, and held-out-performance gates |

## 13. First implementation ticket set

The next development pass should create these small tickets in order:

1. Record baseline tests and deterministic episode fixture.
2. Add `ParticipantInjection`, `GridAssessment`, and violation contracts.
3. Add the settlement-to-injection builder with 1-hour and 15-minute tests.
4. Add versioned `GridSpec` and mapping validation.
5. Extract `TradeTransportPolicy` and prove legacy parity.
6. Port the standalone SimBench adapter with no environment imports.
7. Add the four-step shadow-mode environment integration.
8. Persist raw settlement/grid records for that fixture.
9. Add filesystem run models/store and CLI execution.
10. Build the read-only NiceGUI run/result slice.

Finishing ticket 10 produces a meaningful end-to-end platform without yet
placing long Ray training or unvalidated physical penalties behind a polished
UI. That is the correct point to review the architecture before implementing
the full scenario editor and 3 × 3 launcher.
