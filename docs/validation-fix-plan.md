# MARLEM Validation and Fix Plan

## Purpose

This document translates the code audit into an implementation plan. It describes what is currently unreliable, which experiments are affected, what should be changed, and how to verify each correction.

The goal is not merely to make the package run. The goal is to make its results physically coherent, economically interpretable, reproducible, and independently testable.

## Current assessment

MARLEM should currently be treated as an architectural research prototype. It should not yet be used to support strong claims about:

- battery dispatch or energy conservation;
- household profit or social welfare;
- grid congestion, voltage, or stability;
- CTDE learning performance;
- measured-household generalisation; or
- superiority of PPO, APPO, or SAC.

Some findings below are definite implementation defects. Others are simplified modelling choices that become problems when the paper or experiment presents them as realistic physical or economic behaviour.

## Priority levels

- **P0 — correctness:** fix before trusting any experiment.
- **P1 — model validity:** fix before making physical, economic, or grid claims.
- **P2 — reproducibility and learning validity:** fix before comparing algorithms or publishing learning curves.
- **P3 — quality and maintenance:** required for a reliable package and future development.

## Issue-by-issue remediation plan

### 1. Buy and sell energy have reversed battery signs — P0

**Problem.** In `src/agent/der.py`, `update_battery_from_trades` calculates the trade contribution as sold energy minus bought energy. Physically, buying should add energy to the household and selling should remove it.

**Affected scope.** Battery state of charge, storage arbitrage, self-consumption, reward values, and every experiment involving energy bought or sold.

**Solution.** Use one documented balance convention throughout the package:

```text
energy_balance = generation + energy_bought - demand - energy_sold
```

Define whether trade quantities are measured at the household meter, battery terminals, or grid side. Apply the same convention in the matcher, DER update, battery, reward, and metrics.

**Verification.** Add tests showing that:

- generation equal to demand with no trades leaves SOC unchanged;
- buying energy increases available energy or reduces a deficit;
- selling energy reduces available energy or increases a surplus;
- energy cannot be created by a buy/sell round trip.

Relevant code: `src/agent/der.py`, especially `update_battery_from_trades`, `update_energy_tracking`, and `adjust_action_for_battery`.

### 2. Battery units, efficiency, and limits are not sufficiently defined — P0/P1

**Problem.** The code mixes concepts expressed as kW, kWh, and Wh without an explicit timestep conversion. Oversized charge/discharge requests are rejected instead of partially clipped. Exact minimum and maximum SOC values are rejected. Discharge efficiency is ambiguous and may be applied on the wrong side of the energy boundary. There are no explicit charge/discharge power limits or terminal SOC value.

**Affected scope.** Battery realism, storage capacity, arbitrage results, end-of-episode behaviour, and comparisons between different profile resolutions.

**Solution.** Choose and document one convention, preferably:

```text
profiles: kW
timestep: hours
traded energy: kWh = kW × timestep
SOC: kWh stored inside the battery
```

Then:

- clip requests to available capacity rather than rejecting all oversized requests;
- allow valid transitions exactly to minimum and maximum SOC;
- define whether a discharge request is energy delivered externally or energy removed internally;
- apply charge and discharge efficiencies consistently;
- add maximum charge/discharge power per timestep;
- add a terminal SOC constraint or explicit residual-energy value.

**Verification.** Test zero, exact-boundary, oversized, and efficiency cases. For every operation, assert that stored-energy change, delivered energy, and losses satisfy the documented equations.

Relevant code: `src/agent/battery.py` (`charge`, `discharge`, `_can_charge`, `_can_discharge`) and `src/agent/der.py`.

### 3. Buy/sell direction is interpreted differently in different stages — P0

**Problem.** `adjust_action_for_battery` uses the raw continuous direction as a Python truth value, while `LocalEnergyMarket.step` later converts it using a 0.5 threshold. A value such as `0.2` can therefore be physically adjusted as one direction and submitted as the other.

**Affected scope.** All policies using continuous direction outputs, including PPO, APPO, SAC, CTDE, CTCE, and inference.

**Solution.** Convert the action direction exactly once at the action boundary. Pass a typed boolean or categorical direction into all later functions. Do not let battery feasibility code interpret raw policy floats independently.

**Verification.** For direction values `0`, `0.2`, `0.49`, `0.5`, `0.51`, and `1`, assert that adjustment, matching, logging, and reward all use the same direction.

Relevant code: `src/agent/der.py` (`adjust_action_for_battery`) and `src/environment/lem.py` (`step`).

### 4. Feasible quantity is calculated from the action instead of the physical state — P0

**Problem.** The DER feasibility logic uses the submitted quantity in calculations that should use actual demand, generation, SOC, battery limits, and existing market position. A large requested quantity can therefore create an artificial deficit or surplus.

**Affected scope.** Physical feasibility, order quantities, battery dispatch, market clearing, and learning signals.

**Solution.** Separate three concepts:

1. policy-requested quantity;
2. physically feasible quantity;
3. quantity accepted by the market.

Calculate feasible buying and selling independently from the physical state. If no quantity is feasible, return zero; do not force a nonzero configured minimum.

**Verification.** With no battery:

- generation 10 and demand 5 must allow at most 5 energy sold and no energy bought;
- generation 0 and demand 5 must allow at most 5 energy bought and no energy sold.

Repeat both cases with battery capacity and efficiency enabled.

Relevant code: `src/agent/der.py` (`adjust_action_for_battery`).

### 5. Discrete decisions are represented as Gaussian continuous actions — P0/P2

**Problem.** Price, quantity, buy/sell direction, and partner selection are represented as continuous Box values. The environment thresholds direction and truncates partner IDs. The policy distribution, log-probabilities, entropy, and executed action therefore describe different spaces.

**Affected scope.** Policy gradients, entropy regularisation, exploration, partner selection, and algorithm comparisons.

**Solution.** Use a hybrid action representation:

- continuous distributions for price and quantity;
- Bernoulli or categorical distribution for buy/sell;
- categorical or MultiDiscrete distribution for partner selection;
- action masks for unavailable partners and infeasible directions.

Alternatively, explicitly document this as a relaxed action formulation and prove that the gradient estimator remains valid.

**Verification.** Confirm that the log-probability of an action is the probability of the action actually executed. Add tests for invalid partner IDs, masked partners, and direction boundaries.

Relevant code: `src/environment/action.py`, `src/environment/lem.py`, `src/environment/ctde.py`, and `src/environment/ctce.py`.

### 6. CTDE trains a centralized actor but executes separate local actors — P0

**Problem.** The CTDE module trains centralized policy outputs in `_forward_train`, while exploration and inference use separate local policy heads. A direct gradient probe showed gradients on the centralized actor but none on the local heads.

**Affected scope.** Every CTDE experiment, including claims that decentralized agents learn from centralized training.

**Solution.** Select one valid design:

- train local actors directly using centralized critics;
- share the actor between centralized training and decentralized execution;
- add an explicit distillation or parameter-copy step; or
- remove CTDE until a correct implementation exists.

Ensure optimizer parameter groups, loss functions, checkpoint restoration, and execution paths all refer to the intended actor.

**Verification.** Record all local policy parameters before and after a real learner iteration. Require nonzero parameter changes and a change in the actions produced by local inference.

Relevant code: `src/environment/ctde.py` (`_forward_train`, `_forward_exploration`, `_forward_inference`, learner/target setup).

### 7. CTCE is described too strongly as a theoretical upper bound — P1/P3

**Problem.** A centralized policy is easier to inform than a decentralized policy, but it is not automatically the global optimum. It can still suffer from poor reward design, optimization failure, and function-approximation error. The paper describes CTCE as a theoretical upper bound while also deferring full MARL training to future work. [Paper](https://arxiv.org/html/2602.16063v1)

**Affected scope.** CTCE-versus-DTDE/CTDE comparisons and scalability claims.

**Solution.** Rename it as a centralized-information baseline or empirical reference. Normalize grouped reward by agent count when comparing community sizes.

**Verification.** On a small environment with an exact solver or exhaustive enumeration, compare CTCE with the true optimum. Report raw and per-agent-normalized returns.

Relevant code: `src/environment/ctce.py` and `src/environment/train.py` (`GroupedLEM.step`).

### 8. Standard RLlib algorithms are not the primary defect — P2

**Problem.** The DTDE configuration maps to standard RLlib PPO, APPO, and SAC modules. The evidence does not show that RLlib itself is broken. The risk comes from MARLEM’s action space, environment transitions, reward, metrics, and inference integration.

**Affected scope.** Interpretation of algorithm comparisons and debugging priorities.

**Solution.** Keep standard RLlib algorithms, but validate them first on a known toy environment and then against a corrected MARLEM environment.

**Verification.** Run PPO/APPO/SAC on a deterministic toy task with a known solution. Separately verify that MARLEM’s environment obeys the RLlib multi-agent API and action-space contract.

Relevant code: `src/environment/base.py` and `src/environment/train.py`.

### 9. Coordination KPIs do not consistently represent their names — P1

**Problem.** In the KPI path used by observations and rewards:

- “social welfare” is transaction turnover, not surplus;
- “supply-demand imbalance” is based on positive trade volume rather than net physical mismatch;
- `1 - imbalance` can make no trading look maximally coordinated;
- “self-consumption” is P2P volume divided by market volume, not local renewable consumption;
- sellable and buyable flexibility are combined despite being directional alternatives;
- buyer and seller bid/ask terminology is reversed.

**Affected scope.** Reward optimisation, observations, dashboards, reported coordination, welfare, liquidity, and self-consumption conclusions.

**Solution.** Define each metric mathematically before coding it. Keep separate metrics for turnover, consumer surplus, producer surplus, net imbalance, renewable self-consumption, flexibility capacity, and flexibility utilisation.

**Verification.** Create hand-calculated golden cases for no trade, one P2P trade, one DSO trade, balanced trades, and a pure import/export case. Verify values in direct analytics, observations, rewards, and saved histories.

Relevant code: `src/coordination/implicit_cooperation.py`, `src/environment/reward.py`, and `src/environment/observation.py`.

### 10. The reward is not an independent economic or physical objective — P0/P1

**Problem.** The reward combines manually weighted and differently scaled terms. One local weight is overwritten. A no-trade early return bypasses other penalties. Some values are transformed with `1 - x` despite being unbounded or dimensionful. Grid credit assignment uses stale balances. The economic term is not a cash-profit ledger.

**Affected scope.** Every learned policy, checkpoint comparison, hyperparameter search, and conclusion about welfare, cost, profit, or balance.

**Solution.** Design the reward from explicit objectives and constraints:

- normalize all terms to known ranges;
- use physically meaningful penalties rather than arbitrary inversions;
- remove early returns that bypass required constraints;
- use current-step state for credit assignment;
- calculate profit from actual settled cash and energy;
- report reward and independent objectives separately.

**Verification.** Test reward monotonicity for more unmet demand, more loss, higher profit, and better balance. Verify that changing €/kWh to €/MWh does not silently change learning behaviour.

Relevant code: `src/environment/reward.py`.

### 11. Observations expose exact future information — P1

**Problem.** Agents receive exact sums of their remaining demand and generation. They also receive broad system information such as market price, volume, grid balance, DSO activity, P2P volume, coordination KPIs, and sometimes all agent reputations.

**Affected scope.** Partial-observability, privacy, decentralization, and out-of-sample generalisation claims.

**Solution.** Decide whether the intended environment is causal or an oracle-planning benchmark. For causal learning, replace exact future sums with past observations, forecasts, or forecast distributions. Explicitly document which global signals are available.

**Verification.** Keep current state fixed and modify future profile values. A causal observation must remain unchanged. Add separate oracle and partial-observation benchmarks if both are useful.

Relevant code: `src/agent/der.py` (`get_remaining_demand`, `get_remaining_supply`) and `src/environment/observation.py`.

### 12. The grid is a capacity-flow proxy, not an electrical network — P1

**Problem.** The grid uses NetworkX shortest paths and heuristic losses. It does not solve voltage, reactive power, impedance, Kirchhoff, transformer, or nodal power-flow constraints. Flows are clipped rather than causing a rejected or curtailed trade. Opposing flows can add on an undirected edge. Ordinary price-based trades may not update network flows.

**Affected scope.** Grid stability, voltage, congestion, losses, and electrical feasibility conclusions.

**Solution.** Either integrate a validated DC/AC power-flow model or explicitly restrict claims to abstract network-capacity and heuristic-loss experiments. Ensure every settled trade is included in the network model.

**Verification.** Test proposed capacity before settlement, opposing directional trades, nodal balance, conservation of losses, and flow updates for every matching path.

Relevant code: `src/grid/network.py`, `src/grid/config.py`, `src/market/matching.py`, and `src/market/dso.py`.

### 13. Matching and settlement are not fully conserved — P1

**Problem.** The ordinary branch has basic price sorting, but preference matching can override price priority. Losses are subtracted from buyer delivery but trade quantities still represent source quantities in some metrics. There is no complete agent cash/profit ledger. DSO settlement and the BidAsk mechanism require correction. Midpoint and symmetric Nash are mathematically identical under current defaults.

**Affected scope.** Market-mechanism comparisons, welfare, cash conservation, individual rationality, losses, fees, and DSO profitability.

**Solution.** Implement a single settlement record containing:

```text
source quantity, delivered quantity, loss, buyer payment,
seller receipt, fees, DSO settlement, and agent cash balance
```

Validate grid constraints before accepting a trade. Decide explicitly whether preferences override price priority.

**Verification.** For every test market, assert energy conservation, cash conservation, loss conservation, individual rationality, price priority, and correct DSO prices. Test all advertised price mechanisms with asymmetric bids and asks.

Relevant code: `src/market/matching.py`, `src/market/mechanism.py`, and `src/market/dso.py`.

### 14. Episode termination skips one profile step — P0

**Problem.** With `max_steps=N`, the current implementation executes `N-1` transitions. The final profile point is not used in a market transition, and terminal penalties can be evaluated at the wrong time.

**Affected scope.** Horizon length, demand fulfilment, terminal penalties, profile replay, and all episode-return comparisons.

**Solution.** Choose whether `max_steps` means transitions or observations, implement that convention consistently, and include an explicit terminal observation if needed.

**Verification.** Assert exact transition counts for `max_steps=1`, `2`, and `4`; assert the final profile index is consumed exactly once.

Relevant code: `src/environment/lem.py` (`step`, termination, and current-step updates).

### 15. Training and evaluation configuration is not a reliable experiment protocol — P2

**Problem.** Positive integer evaluation durations are rejected. Evaluation uses the same environment/data configuration as training. There is no built-in chronological or household holdout. PBT is enabled even with one sample. Checkpoints are selected using shaped reward, and CPU allocation can oversubscribe the machine. The paper does not provide evidence of improvement over simple baselines. [Paper](https://arxiv.org/html/2602.16063v1)

**Affected scope.** Reproducibility, generalisation, checkpoint selection, resource usage, and algorithm comparisons.

**Solution.** Add explicit train/validation/test configuration, correct evaluation validation, disable PBT when unnecessary, select checkpoints using independent metrics, and record resource settings. Include random, rule-based, and optimisation baselines.

**Verification.** Test the configuration parser, confirm training and evaluation use disjoint data, and run at least three independent seeds per algorithm.

Relevant code: `src/environment/train.py`.

### 16. Measured profiles are randomly transformed — P2

**Problem.** The CSV loader randomly selects a column, rescales the profile, adds noise, multiplies by capacity, and smooths it. This may be useful augmentation, but it is not exact household-data replay.

**Affected scope.** Claims involving measured data, household identity, temporal realism, and generalisation.

**Solution.** Provide two explicit modes:

- deterministic measured-data replay: fixed agent → household → date/time series;
- synthetic augmentation: random scaling/noise/smoothing, fully seeded and separately reported.

**Verification.** A fixed replay configuration must produce byte-for-byte identical profile values across runs and must identify the source household/date.

Relevant code: `src/profile/base.py` and `src/profile/der.py`.

### 17. Global reseeding creates artificial agent correlations — P2

**Problem.** Multiple component reset methods repeatedly call global `np.random.seed`. This makes similarly configured agents receive identical or correlated random profiles, SOCs, reputations, and balances.

**Affected scope.** Multi-agent diversity, statistical significance, scenario generation, and reproducibility.

**Solution.** Pass independent `numpy.random.Generator` objects or derived seeds to each environment, agent, profile, battery, grid, and market component. Do not reseed global state in reset methods.

**Verification.** Require exact same-seed episode reproducibility, different-seed variation, and distinct per-agent random streams within the same episode.

Relevant code: `src/environment/lem.py`, `src/agent/battery.py`, `src/profile/base.py`, `src/grid/network.py`, `src/market/dso.py`, and `src/coordination/reputation.py`.

### 18. Inference does not reproduce training-time action handling — P2

**Problem.** Inference restores only the RLModule and manually reconstructs Gaussian actions. Grouped action splitting is order-sensitive. CTDE inference uses local heads that are not trained. Metrics read outer-level info keys while grouped environments place them inside nested dictionaries, causing zero/default metrics.

**Affected scope.** Evaluation, deployment, saved-policy comparisons, and reported inference metrics.

**Solution.** Restore the full RLlib Algorithm where possible, or exactly reproduce its connectors, preprocessing, action distributions, clipping, ordering, and exploration settings. Normalize the info schema before metrics collection.

**Verification.** For the same checkpoint and observation, compare actions from RLlib and the custom inference path. Compare direct environment histories with all inference-reported metrics.

Relevant code: `src/environment/inference.py` and `src/environment/train.py` (`GroupedLEM`).

### 19. Existing tests are smoke tests, not correctness tests — P3, blocking release

**Problem.** Many tests print values instead of asserting them. Exceptions are caught and printed, so failures may still look successful. The reward test uses an outdated constructor signature, and the active environments lack `pytest`.

**Affected scope.** All claims: battery, market, grid, reward, episode length, seeding, CTDE, and learning.

**Solution.** Rewrite the suite with assertions and property tests. Do not swallow exceptions. Add CI that installs the declared dependencies and runs `python -m pytest tests`.

**Verification.** Deliberately introduce an energy-conservation failure and confirm the test command exits nonzero. Add regression tests for every P0/P1 issue above.

Relevant code: `tests/test_battery.py`, `tests/test_matching.py`, `tests/test_grid_network.py`, `tests/test_environment.py`, `tests/test_reward.py`, and `tests/test_inference.py`.

## Recommended implementation order

### Phase 1 — make environment transitions correct

1. Define units, timestep, meter boundary, and trade-sign conventions.
2. Fix battery signs, efficiency, clipping, boundaries, and feasible quantity logic.
3. Normalize buy/sell action handling and replace the hybrid Gaussian mismatch.
4. Fix episode termination.
5. Add P0 invariant tests before changing learning code.

### Phase 2 — make market and grid results defensible

1. Implement conserved settlement and cash accounting.
2. Correct losses, fees, DSO settlement, price mechanisms, and priority rules.
3. Ensure every accepted trade updates network state and is checked against proposed capacity.
4. Either integrate a power-flow solver or narrow the grid claims to an abstract network model.
5. Replace misleading KPI definitions and build golden metric cases.

### Phase 3 — make learning experiments valid

1. Repair CTDE or remove it from comparisons.
2. Separate train, validation, and test households/time periods.
3. Replace global reseeding with independent generators.
4. Restore inference through the same action/distribution path used during training.
5. Add random, rule-based, optimisation, and standard-algorithm baselines.
6. Run multiple seeds and report confidence intervals.

### Phase 4 — package and release quality

1. Convert smoke tests to assertion-based unit, property, and integration tests.
2. Add CI and a pinned environment.
3. Document all observation, action, reward, unit, and settlement contracts.
4. Update the paper and README claims to match the validated model.

## Release gate

MARLEM should not be presented as a validated package until:

- all P0 tests pass;
- market energy and cash conservation pass;
- grid claims match the implemented model;
- CTDE local policies demonstrably update if CTDE is retained;
- inference matches training-time policy execution;
- deterministic data and seed protocols are documented;
- baseline and multi-seed results are available; and
- the complete test suite fails loudly when an invariant is violated.

