# GitHub Issue Preview: Validation Fix Plan

Generated from [`docs/validation-fix-plan.md`](validation-fix-plan.md) on 2026-08-08.

This is a local preview only. No GitHub issues have been created. Labels below are suggestions and may need to be created in the repository first.

## P0-01 - Bought and sold energy have reversed signs in the DER balance

**Suggested labels:** `priority:P0`, `correctness`, `energy-settlement`

### Problem

The DER balance treats purchased energy as a subtraction and sold energy as an addition. This reverses the physical effect of trades and affects SOC, demand satisfaction, arbitrage, balances, and rewards.

### Proposed resolution

Use one explicit balance equation: generation + delivered purchases - demand - source sales. Record the per-agent settlement quantities used by the equation.

### Acceptance criteria

- [ ] Add golden tests for no trade, pure buy, pure sell, and balanced generation/demand.
- [ ] Energy conservation holds for each agent and timestep.
- [ ] Battery and reward calculations use the corrected signs.

## P0-02 - Action feasibility is derived from the requested action, not the physical state

**Suggested labels:** `priority:P0`, `correctness`, `action-space`

### Problem

Feasibility is calculated from the requested action instead of the agent's actual net deficit or surplus. Quantity clamping can also force a nonzero order when no order is physically appropriate.

### Proposed resolution

Separate requested, physically feasible, and settled quantities. Compute feasibility from generation, demand, battery state, and existing position, while allowing a zero/no-order result.

### Acceptance criteria

- [ ] A generator with 10 units of generation and 5 units of demand can sell at most 5.
- [ ] A load with zero generation and 5 units of demand can buy at most 5.
- [ ] No-order actions remain possible and are represented consistently.

## P0-03 - Direction and partner decisions do not match the policy's declared action space

**Suggested labels:** `priority:P0`, `correctness`, `action-space`

### Problem

The continuous action space is interpreted inconsistently: direction uses different thresholds, partner selection truncates floats, and endpoint values can select invalid or self partners. Discrete-like choices are also being produced by a Gaussian policy.

### Proposed resolution

Use a simple, documented action representation such as price plus signed quantity, and remove learned partner selection from the baseline unless it is implemented as a valid policy action.

### Acceptance criteria

- [ ] Zero quantity, positive quantity, and negative quantity have one documented meaning.
- [ ] Bounds and no-order behavior are tested.
- [ ] The action used for feasibility, matching, logging, and reward is the action sampled by the policy.

## P0-04 - Matching mutates submitted orders before reward calculation and destroys the audit trail

**Suggested labels:** `priority:P0`, `correctness`, `market-clearing`

### Problem

Matching mutates `Order.quantity` during partial fills and DSO handling. The same objects are later used for reward and reporting, so submitted quantities are lost and execution ratios can divide by zero.

### Proposed resolution

Keep submitted orders immutable, or copy them before matching. Track submitted, remaining, and filled quantities as separate settlement records.

### Acceptance criteria

- [ ] Submitted order quantities remain unchanged after matching.
- [ ] Submitted = filled + remaining + explicitly unserved/curtailed quantity.
- [ ] Execution ratios are calculated from the original submitted quantity.

## P0-05 - Two advertised pricing mechanisms receive the wrong arguments

**Suggested labels:** `priority:P0`, `correctness`, `pricing`

### Problem

The matcher calls every pricing strategy with the same positional arguments, but the seller-pricing and bid-ask implementations interpret those arguments differently. Some named strategies currently duplicate the same calculation.

### Proposed resolution

Define one typed, keyword-based pricing interface and make each strategy implement it explicitly. Remove duplicate names or document their intended differences.

### Acceptance criteria

- [ ] Known bid/ask fixtures produce documented prices.
- [ ] Buyer pricing, seller pricing, midpoint, and bid-ask spread behavior are independently tested.
- [ ] A strategy cannot silently reinterpret a positional argument.

## P0-06 - Battery boundary and efficiency equations are inconsistent

**Suggested labels:** `priority:P0`, `correctness`, `battery`

### Problem

Battery SOC limits, efficiency equations, timestep semantics, and quantity units are inconsistent. Exact boundary requests and oversized requests are not handled as one coherent policy.

### Proposed resolution

Use internal SOC in kWh, define grid-side versus battery-side quantities, apply charge/discharge efficiency in one place, include `delta_t` and power limits, and clip or reject requests according to a documented rule.

### Acceptance criteria

- [ ] Zero, exact-boundary, and oversized requests are tested.
- [ ] Charge and discharge efficiencies produce expected SOC changes.
- [ ] Round-trip losses and timestep/power limits are correct.

## P0-07 - Episode termination executes `N-1` transitions and never reaches the intended terminal reward

**Suggested labels:** `priority:P0`, `correctness`, `episode-lifecycle`

### Problem

The terminal flag and timestep increment occur in an order that skips the final transition. A 24-step probe executes only 23 transitions and misses the intended terminal reward.

### Proposed resolution

Define `max_steps` as the number of transitions, process indices consistently, and emit the terminal reward and a valid terminal observation on the final transition.

### Acceptance criteria

- [ ] Horizons 1, 2, 4, and 24 execute exactly the requested number of transitions.
- [ ] Every profile interval is used exactly once.
- [ ] Terminal penalties/rewards are applied exactly once.

## P0-08 - Reset reseeding makes agents identical and overwrites configured profiles

**Suggested labels:** `priority:P0`, `correctness`, `reproducibility`

### Problem

Global random seeding is repeated across environment components, which can make agents identical. Reset also overwrites explicitly configured profiles, making replay scenarios unreliable.

### Proposed resolution

Use one master random generator with deterministic child generators per component and agent. Distinguish explicit replay data from generated profiles and preserve replay data on reset.

### Acceptance criteria

- [ ] Same seed reproduces the same scenario.
- [ ] Agents are not accidentally identical because of repeated global seeding.
- [ ] Different seeds change generated scenarios.
- [ ] Explicit profiles are reproduced exactly after reset.

## P0-09 - CTDE trains one actor and executes different, untrained actors

**Suggested labels:** `priority:P0`, `correctness`, `multi-agent-learning`

### Problem

The CTDE learner trains a centralized policy path while rollout and inference use independent policy heads that are not updated by the actor loss. Training and execution therefore use different actors.

### Proposed resolution

Implement a valid centralized-training/decentralized-execution design with local actors and a centralized critic, or disable the CTDE mode until it is corrected.

### Acceptance criteria

- [ ] Actor parameters used during rollout are updated by the learner.
- [ ] The critic may use centralized information, but execution does not.
- [ ] A small cooperative test demonstrates learning or at least parameter/output updates.

## P0-10 - Grouped observations/actions can be assigned to the wrong agents

**Suggested labels:** `priority:P0`, `correctness`, `multi-agent-learning`

### Problem

Agent ordering differs between active-agent sets, grouped environments, tuple spaces, and CTDE heads. Sorting or using sets can silently map one agent's observation or action to another agent.

### Proposed resolution

Define one immutable `agent_order` and use it for grouping, packing, unpacking, model heads, and inference. Never derive ordering from an unordered set.

### Acceptance criteria

- [ ] Non-lexicographic IDs such as `agent_2` and `agent_10` are tested.
- [ ] Observation/action round trips preserve agent identity.
- [ ] Sentinel values make swapped-agent mappings detectable.

## P0-11 - There is no conserved cash ledger, and household profit is never updated

**Suggested labels:** `priority:P0`, `correctness`, `economic-settlement`

### Problem

Trades do not create buyer debits and seller credits in a conserved cash ledger. DSO fees are not assigned consistently, and household profit remains zero or stale.

### Proposed resolution

Create an explicit settlement ledger for buyer payments, seller receipts, DSO payments, fees, and per-agent cash. Derive profit from that ledger.

### Acceptance criteria

- [ ] P2P trades conserve cash.
- [ ] DSO transactions and fees reconcile between counterparties.
- [ ] Per-agent balances and reported profit agree with settlement records.

## P0-12 - The repository has no functioning correctness test gate

**Suggested labels:** `priority:P0`, `correctness`, `testing`

### Problem

The existing tests are largely manual or incomplete and do not provide an assertion-based correctness gate. The current test run reports failures and errors rather than a clean invariant suite.

### Proposed resolution

Convert manual checks into assertion-based tests and add a small regression harness for energy, settlement, battery, matching, lifecycle, and multi-agent invariants.

### Acceptance criteria

- [ ] `pytest` passes in a clean environment.
- [ ] P0 regression tests fail when known sign, accounting, or lifecycle defects are reintroduced.
- [ ] The test gate runs automatically in the project workflow.

## P1-01 - Source energy, delivered energy, and losses are not conserved in settlement

**Suggested labels:** `priority:P1`, `model-validity`, `energy-settlement`

### Problem

Trades, DSO settlement, and battery quantities use inconsistent energy boundaries, so source energy, delivered energy, exports/imports, and losses cannot be reconciled.

### Proposed resolution

Define an explicit energy ledger distinguishing source-side energy, delivered energy, losses, imports/exports, and battery charge/discharge energy.

### Acceptance criteria

- [ ] Per-trade, per-step, and per-episode energy conservation checks pass.
- [ ] Buyer delivery equals the settled delivered quantity.
- [ ] DSO and battery ledgers reconcile with the system ledger.

## P1-02 - Ordinary price matches bypass the network flow model and do not test projected constraints

**Suggested labels:** `priority:P1`, `model-validity`, `grid`

### Problem

Ordinary matches can be accepted without running the network-flow or projected-constraint model. Grid constraints are applied only on special paths or after matching.

### Proposed resolution

Run path feasibility before accepting ordinary matches, or explicitly label the current behavior as a market-only baseline. Record rejected and congested flows.

### Acceptance criteria

- [ ] Topology and capacity changes can alter matching outcomes.
- [ ] The same grid-feasibility rule applies to all matching paths.
- [ ] Rejected, curtailed, and congested quantities are reported.

## P1-03 - Grid flows are random, cumulative across time, unsigned, and silently clipped

**Suggested labels:** `priority:P1`, `model-validity`, `grid`

### Problem

Grid flows are not derived from settled trades in a physically meaningful way. They can accumulate across timesteps, lack direction, and be clipped without exposing capacity violations.

### Proposed resolution

Compute signed, per-step flows from settled trades, reset or recompute them each timestep, and choose an explicit hard-feasibility or overload-handling policy.

### Acceptance criteria

- [ ] Flow direction follows the net settled energy.
- [ ] Flows reset correctly between timesteps and episodes.
- [ ] Capacity violations are rejected or explicitly reported, never silently clipped.

## P1-04 - The IEEE34 representation is disconnected and its impedances are unused

**Suggested labels:** `priority:P1`, `model-validity`, `grid`

### Problem

The IEEE34 network representation is not connected as a usable feeder graph, and branch impedances do not affect flow or loss calculations.

### Proposed resolution

Use a canonical connected feeder/branch representation, or rename the model as an abstract network. Make impedances part of the flow and loss calculation.

### Acceptance criteria

- [ ] The graph is connected from source to every modeled node.
- [ ] Branch data has a documented unit and direction.
- [ ] Known branch-distance or impedance fixtures produce expected flow/loss results.

## P1-05 - DSO fallback bypasses grid feasibility and makes unmatched-order metrics degenerate

**Suggested labels:** `priority:P1`, `model-validity`, `market-clearing`

### Problem

The DSO fallback can satisfy residual orders without applying network limits. It also mutates or clears unmatched quantities, making unmatched-order metrics misleading.

### Proposed resolution

Implement residual allocation with explicit DSO limits and preserve submitted, remaining, unserved, and curtailed quantities as separate records.

### Acceptance criteria

- [ ] Constrained DSO scenarios produce constrained allocations.
- [ ] There is no free unlimited fallback.
- [ ] Submitted and unserved quantities reconcile after DSO processing.

## P1-06 - Reward calculation contains bypasses, stale state, duplicated weights, and unnormalised terms

**Suggested labels:** `priority:P1`, `model-validity`, `reinforcement-learning`

### Problem

Reward components can use stale or bypassed state, duplicated weights, and incompatible scales. This makes the optimization target difficult to interpret and reproduce.

### Proposed resolution

Build rewards from auditable settlement, energy, and grid ledgers. Give every term one named normalizer and one documented weight.

### Acceptance criteria

- [ ] Component-level reward fixtures produce expected values.
- [ ] No-trade and penalty cases are covered.
- [ ] Reward scales and weights are documented and stable across scenarios.

## P1-07 - Core coordination KPIs do not implement the quantities named

**Suggested labels:** `priority:P1`, `model-validity`, `metrics`

### Problem

Several coordination KPIs use proxies, zeros, or missing inputs instead of calculating the quantities their names imply.

### Proposed resolution

Define each KPI mathematically, collect its required raw variables, and mark a metric unavailable when its inputs do not exist.

### Acceptance criteria

- [ ] KPI formulas and units are documented.
- [ ] Hand-crafted fixtures verify each formula.
- [ ] Unsupported metrics are not reported as valid zero values.

## P1-08 - Analytics report economic, grid, and coordination concepts without the required inputs

**Suggested labels:** `priority:P1`, `model-validity`, `metrics`

### Problem

Analytics claim to report economic, grid, and coordination concepts without receiving the raw ledger and state inputs needed to calculate them reliably.

### Proposed resolution

Define an analytics data contract sourced from raw settlement, energy, grid, and reputation records. Distinguish unavailable metrics from zero metrics.

### Acceptance criteria

- [ ] Synthetic fixtures produce exact expected analytics values.
- [ ] Missing input data produces an explicit unavailable result.
- [ ] Reported metrics can be traced back to raw records.

## P1-09 - Observations mix a false initial state, exact future information, and global/private information

**Suggested labels:** `priority:P1`, `model-validity`, `observations`

### Problem

Observations may contain an incorrect initial state, exact future profile information, and a mixture of global and private data that is not defined by the intended information structure.

### Proposed resolution

Specify an observation contract covering current/past information, public/private visibility, and causality. Remove future leakage unless it is an intentional declared setting.

### Acceptance criteria

- [ ] The first reset observation reflects the actual initial state.
- [ ] Future-only changes cannot alter an observation before they become observable.
- [ ] Public and private fields are documented and tested.

## P1-10 - Reputation scores are structurally degenerate and time weighting freezes updates

**Suggested labels:** `priority:P1`, `model-validity`, `reputation`

### Problem

Reputation updates do not respond meaningfully to outcomes, and time weighting can freeze or collapse scores into identical values.

### Proposed resolution

Define reputation events, update timing, cold-start behavior, scale, decay, and fairness properties. Apply time weighting without preventing future updates.

### Acceptance criteria

- [ ] Successful and unsuccessful outcomes change reputation predictably.
- [ ] Time weighting changes influence without freezing the score.
- [ ] Cold-start and identical-agent cases are covered.

## P1-11 - Units and timestep semantics are inconsistent across the system

**Suggested labels:** `priority:P1`, `model-validity`, `units`

### Problem

Energy, price, fee, capacity, and timestep values mix units such as kWh and Wh or 15-minute and 60-minute intervals without a single contract.

### Proposed resolution

Document one internal unit contract, convert only at clear boundaries, and use `delta_t` consistently in dynamics, power, energy, and cash calculations.

### Acceptance criteria

- [ ] Unit conversions are tested at every external boundary.
- [ ] 15-minute and 60-minute scenarios obey equivalent physical semantics.
- [ ] One-hour energy and cash fixtures are dimensionally correct.

## P1-12 - CTCE is a centralized-information baseline, not a theoretical upper bound

**Suggested labels:** `priority:P1`, `model-validity`, `multi-agent-learning`

### Problem

CTCE has access to centralized information, but that does not make its learned result a theoretical optimum or upper bound.

### Proposed resolution

Rename and document CTCE as a centralized-information baseline. Define its observation scope and limitations, and reserve “upper bound” for a separately solved optimization problem.

### Acceptance criteria

- [ ] Documentation no longer presents CTCE as an optimal upper bound.
- [ ] CTCE and decentralized modes use identical scenarios and evaluation protocols.
- [ ] Any optimizer-based bound is labeled separately and only used where feasible.

## P1-13 - Preference matching and “clearing price” do not define one coherent market design

**Suggested labels:** `priority:P1`, `model-validity`, `market-clearing`

### Problem

Preference matching is applied before a clear price-time priority rule, and bilateral prices plus DSO tariffs are aggregated under a misleading `clearing_price` name.

### Proposed resolution

Define a price-time baseline with explicit tie-breaking and partial-fill rules. Rename aggregate values as volume-weighted settlement prices unless a true single clearing price is implemented.

### Acceptance criteria

- [ ] Golden order books verify priority, partial fills, and tie-breaking.
- [ ] Preference/reputation priority is optional and explicitly documented.
- [ ] Bilateral and DSO prices are reported separately from any aggregate.

## P2-01 - Training evaluation is not a held-out, independently seeded protocol

**Suggested labels:** `priority:P2`, `reproducibility`, `evaluation`

### Problem

Evaluation reuses training environments or seeds and does not provide disjoint train, validation, and test scenarios.

### Proposed resolution

Create disjoint scenario manifests and seed lists. Select checkpoints on validation data and evaluate once on held-out test data, with multiple training seeds.

### Acceptance criteria

- [ ] Train, validation, and test manifests have no overlap.
- [ ] Checkpoint selection cannot read test results.
- [ ] Per-episode records include scenario and seed identifiers.

## P2-02 - Standalone inference does not reproduce RLlib's action or information path

**Suggested labels:** `priority:P2`, `reproducibility`, `inference`

### Problem

Standalone inference manually restores modules, splits normalization, and clips actions instead of using the same RLlib action connectors and information path as evaluation. Some metrics also read the wrong info level.

### Proposed resolution

Evaluate through the RLlib `Algorithm`, or create a tested adapter that exactly reproduces action transformation, agent order, normalization, and info extraction.

### Acceptance criteria

- [ ] Fixed-checkpoint RLlib and standalone actions/distributions agree.
- [ ] Observation/action ordering and normalization are identical.
- [ ] Metrics are read from the correct per-agent and episode-level records.

## P2-03 - CSV “measured profiles” are arbitrary, transformed samples rather than replayed data

**Suggested labels:** `priority:P2`, `reproducibility`, `data`

### Problem

CSV profile handling selects arbitrary columns and applies random transforms, noise, and clipping without a timestamp/frequency contract. The resulting data is not faithful measured-data replay.

### Proposed resolution

Implement deterministic replay with named columns, timestamps, frequency, and interval handling. Keep augmentation as a separate, seeded synthetic-data mode.

### Acceptance criteria

- [ ] Valid measured profiles replay values exactly.
- [ ] Invalid timestamps, lengths, and columns fail clearly.
- [ ] Synthetic augmentation is reproducible and not labeled as measured replay.

## P2-04 - Saved environment configuration cannot reconstruct the original scenario

**Suggested labels:** `priority:P2`, `reproducibility`, `configuration`

### Problem

Saved configuration rounds profiles, omits seeds and data provenance, and does not reliably restore nested grid or replay settings.

### Proposed resolution

Create a versioned scenario schema containing scalar parameters, units, seeds, agent order, source paths/hashes, split information, and augmentation settings. Make it lossless or explicitly regenerable.

### Acceptance criteria

- [ ] Serialize/restore/serialize produces equivalent configuration.
- [ ] Restored scenarios use the same data manifest and seeds.
- [ ] Configuration files identify their schema version and units.

## P2-05 - Training configuration contains validation, scheduling, and resource defects

**Suggested labels:** `priority:P2`, `reproducibility`, `training-infrastructure`

### Problem

Training configuration has defects involving evaluation duration validation, CPU allocation, unconditional PBT, run naming, cleanup, and checkpoint selection.

### Proposed resolution

Validate configuration boundaries, make resource budgets explicit, enable schedulers only when requested, use unique manifest-based run IDs, clean up with `try/finally`, and select checkpoints using a predeclared objective.

### Acceptance criteria

- [ ] Boundary values for evaluation and resources are tested.
- [ ] A one-iteration CPU smoke run succeeds without double allocation.
- [ ] Failed runs clean up resources and retain useful diagnostics.
- [ ] Run IDs remain unique across runs.

## P2-06 - Experiments lack immutable manifests, baselines, and statistical reporting

**Suggested labels:** `priority:P2`, `reproducibility`, `experiments`

### Problem

Experiments do not preserve an immutable pre-run manifest containing code state, dependency state, data hashes, units, splits, seeds, and metrics. Baselines and uncertainty reporting are also missing.

### Proposed resolution

Write a manifest before each run, keep append-only raw results, add random/rule/self-consumption/optimizer baselines where appropriate, and report multi-seed uncertainty.

### Acceptance criteria

- [ ] A clean checkout plus a manifest identifies the exact run inputs.
- [ ] Interrupted runs retain raw results.
- [ ] Results can be regenerated into tables and figures.
- [ ] Baseline comparisons include multiple seeds and uncertainty where applicable.

## P3-01 - The “blockchain validator” is incomplete for settlement integrity and is unnecessary in the critical path

**Suggested labels:** `priority:P3`, `architecture`, `settlement`

### Problem

The validator hash omits settlement fields such as distance, losses, and fees. The matcher calls a private validator method each step, while the in-memory proof-of-work is not a decentralized blockchain.

### Proposed resolution

Remove proof-of-work from the default critical path. If integrity logging is needed, implement an optional append-only hash-chained settlement log with complete records and call it tamper-evident logging.

### Acceptance criteria

- [ ] Changing any settlement field invalidates the integrity chain.
- [ ] Matching does not depend on a private validator method.
- [ ] Disabling the optional log does not change market outcomes.

## P3-02 - Defensive validation hides bad state or is internally ineffective

**Suggested labels:** `priority:P3`, `maintenance`, `validation`

### Problem

Validation sometimes clamps invalid state before checking it, compares topology enums incorrectly, catches too broadly, uses mutable list defaults, or rejects valid integer-like values through overly strict float checks.

### Proposed resolution

Validate before normalization, use explicit topology sets, narrow exception handling, use `None` for mutable defaults, and perform boundary enum/type conversion deliberately.

### Acceptance criteria

- [ ] Invalid state raises a clear error before it is modified.
- [ ] Valid enum and integer-like inputs are accepted where intended.
- [ ] Mutable defaults are not shared between instances.
- [ ] Tests cover each validation boundary and exception path.

## P3-03 - Documentation, notebooks, and packaging describe a different repository state

**Suggested labels:** `priority:P3`, `documentation`, `maintenance`

### Problem

README files, notebooks, package metadata, and commands refer to missing cases, mismatched topology names, outdated case counts, absent modules, and inconsistent CPU/GPU or UV installation guidance.

### Proposed resolution

Regenerate documentation from the actual repository state, restore or remove documented commands, list supported notebooks, define one packaging/UV workflow, and document CPU/GPU policies.

### Acceptance criteria

- [ ] Every documented command works in a clean checkout or is removed.
- [ ] Notebook paths and links are valid, and notebooks are cleared of machine-local output.
- [ ] Package metadata and dependency instructions match the supported environment.
- [ ] CPU and GPU setup guidance is explicit and tested.

