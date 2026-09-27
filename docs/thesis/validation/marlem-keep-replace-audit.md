# MARLEM keep / replace audit for a SimBench edition

> **Question:** if the thesis builds its own SimBench edition with the papers as the *methodology* baseline, instead of repairing the original code first, which parts of the original MARLEM are worth keeping, which are rewritten from the paper, and which are replaced or dropped?
> **Stance taken here:** the papers ([P1], [P2]) define the method. The original code is a source of reusable parts, not a reference implementation. Every non-RL layer (agents, market, DSO, grid, KPIs, observation, reward) is rebuilt and validated first, with scripted policies; the RL layer is parked until the environment is correct.
> Written: 2026-09-27 · Branch: `dev` · Code links point at the frozen original, `src_thesis_reference/` (identical to `src_thesis/` on 2026-09-27).
> Issue IDs link to the register in [issues.md](issues.md#2-register). Target design: [architecture/01-simbench-grid.md](../architecture/01-simbench-grid.md).

<!-- BEGIN toc (python docs/toc.py) -->
## Contents

- [0. Verdicts](#0-verdicts)
- [1. Bottom line](#1-bottom-line)
- [2. Where the original is coupled to its grid](#2-where-the-original-is-coupled-to-its-grid)
- [3. Module by module](#3-module-by-module)
  - [3.1 Market: pricing, orders, trades, ledger](#31-market-pricing-orders-trades-ledger)
  - [3.2 Market: matching](#32-market-matching)
  - [3.3 DSO](#33-dso)
  - [3.4 Agents and battery](#34-agents-and-battery)
  - [3.5 Grid and profiles](#35-grid-and-profiles)
  - [3.6 Episode loop, observation, reward](#36-episode-loop-observation-reward)
  - [3.7 Cooperation KPIs, analytics, plots](#37-cooperation-kpis-analytics-plots)
  - [3.8 RL layer (parked)](#38-rl-layer-parked)
- [4. What happens to the 80 issues](#4-what-happens-to-the-80-issues)
- [5. What the original never had (the new build needs it)](#5-what-the-original-never-had-the-new-build-needs-it)
- [6. Proposed build order (RL isolated)](#6-proposed-build-order-rl-isolated)
- [7. Consequences for the existing plans](#7-consequences-for-the-existing-plans)

<!-- END toc -->

## 0. Verdicts

| Verdict | Meaning |
|---|---|
| **Keep** | Reuse the code as it is (tidy only) |
| **Keep + fix** | The code is the paper's method; reuse it and fix the listed issues |
| **Rewrite** | The paper concept stays; write new code from the paper and the recorded decisions. The original is at most a sketch. |
| **Replace** | Superseded by SimBench / pandapower or by the experiment layer (02, 03) |
| **Drop** | Not needed for the thesis |
| **Later (RL)** | The learning layer: park it unchanged until the environment is validated |

[↑ Contents](#contents)

## 1. Bottom line

| Layer | Original code | Verdict | Share of its lines kept |
|---|---|---|---|
| Pricing, orders, trades | [mechanism.py](../../../src_thesis_reference/marketplace/market/mechanism.py), [order.py](../../../src_thesis_reference/marketplace/market/order.py) | Keep + fix | ~95 % |
| Battery | [battery.py](../../../src_thesis_reference/marl/agents/battery.py) | Keep + fix | ~85 % |
| Action space | [action.py](../../../src_thesis_reference/marketplace/action.py) | Keep + fix | ~80 % |
| DSO tariffs and residual clearing | [dso.py](../../../src_thesis_reference/marketplace/dso/dso.py), [profiles/dso.py](../../../src_thesis_reference/adapters/profiles/dso.py) | Keep + fix (tariffs, clearing) · Rewrite (fees) · Drop (grid check) | ~60 % |
| DER agent | [der.py](../../../src_thesis_reference/marl/agents/der.py) | Keep the data holder, rewrite feasibility, settlement and partner choice | ~40 % |
| Reputation | [reputation.py](../../../src_thesis_reference/marketplace/market/reputation.py) | Keep + fix; grid term replaced | ~60 % |
| Cooperation KPIs | [implicit_cooperation.py](../../../src_thesis_reference/cooperation/implicit_cooperation.py) | Keep + fix (6 of 10 KPIs); grid KPIs re-sourced from the power flow | ~60 % |
| Matching | [matching.py](../../../src_thesis_reference/marketplace/market/matching.py) | Rewrite (same three stages, lossless, no grid calls) | ~25 % |
| Episode loop | [lem.py](../../../src_thesis_reference/marketplace/lem.py) | Rewrite (same phase order, new settlement and grid step) | ~20 % |
| Observation | [observation.py](../../../src_thesis_reference/marketplace/observation.py) | Rewrite (same Table 2 layout, versioned, grid block from the assessment) | ~40 % |
| Reward | [reward.py](../../../src_thesis_reference/marketplace/reward.py) | Rewrite inputs, keep the eq. 3–6 structure and weights | ~40 % |
| NetworkX grid | [network.py](../../../src_thesis_reference/adapters/grid/network.py), [grid/config.py](../../../src_thesis_reference/marketplace/grid/config.py), [grid/base.py](../../../src_thesis_reference/marketplace/grid/base.py) | Replace (pandapower adapter) | 0 % |
| DER profiles | [profiles/der.py](../../../src_thesis_reference/adapters/profiles/der.py), [profiles/base.py](../../../src_thesis_reference/adapters/profiles/base.py) | Replace (SimBench profiles); keep the synthetic generator for tests | ~30 % |
| Config I/O | [io.py](../../../src_thesis_reference/marketplace/io.py) | Replace (experiment file, 02) | 0 % |
| Blockchain ledger | [validation.py](../../../src_thesis_reference/marketplace/market/validation.py) | Keep as an optional, off-by-default audit log | ~90 % |
| Analytics and plots | [metrics/](../../../src_thesis_reference/cooperation/metrics/), [plotter.py](../../../src_thesis_reference/cooperation/visualization/plotter.py) | Drop; salvage 3–4 functions | ~10 % |
| RL | [train.py](../../../src_thesis_reference/marl/train.py), [ctce.py](../../../src_thesis_reference/marl/ctce.py), [ctde.py](../../../src_thesis_reference/marl/ctde.py), [inference.py](../../../src_thesis_reference/marl/inference.py), [base.py](../../../src_thesis_reference/marl/base.py) | Later (RL) | parked |

**In numbers:** the non-RL environment is about 5 800 lines (without analytics and plots). Roughly **1 600 lines (~27 %) can be kept** with fixes; about 2 100 are rewritten from the paper using the original as a sketch; about 1 600 are replaced by SimBench, pandapower and the experiment layer. Analytics and plotting (about 4 000 lines, mostly unaudited) are dropped.

**Decided 2026-09-27 (D-04, D-14):** the rebuild happens in place in `src_thesis/`, keeping file names and class responsibilities (files may be rewritten); `src_thesis/`'s original state is frozen in `src_thesis_reference/`. *Original recommendation:* build the SimBench edition as a new environment package that *imports* the kept pieces (pricing, orders, battery, tariffs, KPIs, reputation) and rewrites the orchestration (loop, matching, settlement, observation, reward). Repairing the original loop first buys little: two of its three most coupled parts (grid flows and losses in matching, the NetworkX grid) are thrown away anyway, and the third (the episode loop) needs a new settlement and grid step regardless.

[↑ Contents](#contents)

## 2. Where the original is coupled to its grid

Every place the original reaches into the NetworkX grid, and what replaces it in the SimBench edition (01 §5–§6).

| Coupling point | Original code | SimBench edition |
|---|---|---|
| Agents placed on graph nodes | [lem.py:84](../../../src_thesis_reference/marketplace/lem.py#L84), [network.py:228-281](../../../src_thesis_reference/adapters/grid/network.py#L228-L281) | Participant mapping to bus IDs (01 §3.1), resolved from the experiment file |
| Grid reset per episode (random initial flows) | [lem.py:309](../../../src_thesis_reference/marketplace/lem.py#L309), [network.py:55-87](../../../src_thesis_reference/adapters/grid/network.py#L55-L87) | `GridModel.reset(day)`; no flow state carried between steps |
| Partner choice by graph distance | [lem.py:372-375](../../../src_thesis_reference/marketplace/lem.py#L372-L375), [der.py:140-163](../../../src_thesis_reference/marl/agents/der.py#L140-L163) | `electrical_distance(bus_a, bus_b)` along lines |
| Per-trade distance and loss in Stage 2 | [matching.py:334-336](../../../src_thesis_reference/marketplace/market/matching.py#L334-L336) | Lossless matching (D-05); losses appear once, in the power flow |
| Flow update from trades (Stage 1 only) | [matching.py:560-603](../../../src_thesis_reference/marketplace/market/matching.py#L560-L603), [network.py:283-334](../../../src_thesis_reference/adapters/grid/network.py#L283-L334) | Removed; one power flow after settlement from participant injections |
| Stage-2 capacity check | [matching.py:316-326](../../../src_thesis_reference/marketplace/market/matching.py#L316-L326) | Removed from matching; violations come from the assessment |
| Congestion level for KPIs and fees | [matching.py:399](../../../src_thesis_reference/marketplace/market/matching.py#L399), [network.py:412-431](../../../src_thesis_reference/adapters/grid/network.py#L412-L431) | Max line / trafo loading from `assessment[t−1]` |
| DSO fee inputs (path congestion, distance) | [dso.py:305-318](../../../src_thesis_reference/marketplace/dso/dso.py#L305-L318) | `assessment[t−1]` loading and electrical distance |
| DSO trade feasibility check | [dso.py:356-401](../../../src_thesis_reference/marketplace/dso/dso.py#L356-L401) | Dropped (feasibility is judged after settlement by the power flow) |
| Imbalance and congestion KPIs normalised by one "grid capacity" | [lem.py:104](../../../src_thesis_reference/marketplace/lem.py#L104), [implicit_cooperation.py:115-134](../../../src_thesis_reference/cooperation/implicit_cooperation.py#L115-L134) | Imbalance = external-grid exchange; congestion = loading (01 §8) |
| Observation bounds and grid-balance signal | [observation.py:64-176](../../../src_thesis_reference/marketplace/observation.py#L64-L176), [observation.py:287](../../../src_thesis_reference/marketplace/observation.py#L287) | Fixed-size grid block from the assessment (01 §6) |
| Reward normalised by grid capacity, driven by `dso.balance` | [reward.py:209](../../../src_thesis_reference/marketplace/reward.py#L209), [reward.py:265-321](../../../src_thesis_reference/marketplace/reward.py#L265-L321) | Decided per reward version; violation term in feedback mode (D-11) |
| Reputation grid term from the trade-based balance | [reputation.py:165-213](../../../src_thesis_reference/marketplace/market/reputation.py#L165-L213) | Bus-attributed violations, or drop the term (01 §8) |
| Config serialises the `GridNetwork` | [io.py:81-169](../../../src_thesis_reference/marketplace/io.py#L81-L169) | The experiment file's `grid` section |

The coupling is wide (13 places in 8 files) but shallow: almost every point reads one number (a distance, a congestion level, a capacity or `dso.balance`). That is why the market code can be kept or rewritten independently of the grid. The target design for this seam is agreed as D-13 ([01 §5.1](../architecture/01-simbench-grid.md#51-ownership-and-data-flow-d-13-the-target-architecture)): `LocalEnergyMarket` stays the orchestrator and the only holder of the grid, and the market receives `GridTopologyInfo` and last step's `GridSignals` as arguments instead of holding a grid reference.

[↑ Contents](#contents)

## 3. Module by module

### 3.1 Market: pricing, orders, trades, ledger

| Code | Verdict | Why / what changes | Issues |
|---|---|---|---|
| [Order](../../../src_thesis_reference/marketplace/market/order.py#L12-L22), [Trade](../../../src_thesis_reference/marketplace/market/order.py#L25-L34) | Keep + fix | Add a separate `submitted_quantity` (or keep a residual outside the order); drop `transmission_loss` (lossless market); add fee payer. `Location` becomes a bus ID. | [I-12](issues.md#I-12), [I-28](issues.md#I-28) |
| [AveragePricing](../../../src_thesis_reference/marketplace/market/mechanism.py#L31-L48), [BuyerPricing](../../../src_thesis_reference/marketplace/market/mechanism.py#L51-L66), [NashBargainingPricing](../../../src_thesis_reference/marketplace/market/mechanism.py#L116-L150), [ProportionalSurplusPricing](../../../src_thesis_reference/marketplace/market/mechanism.py#L153-L193), [ClearingMechanism](../../../src_thesis_reference/marketplace/market/mechanism.py#L196-L215) | Keep | Match eq. 9–11 | — |
| [SellerPricing](../../../src_thesis_reference/marketplace/market/mechanism.py#L70-L85), [BidAskSpreadPricing](../../../src_thesis_reference/marketplace/market/mechanism.py#L89-L113) | Keep + fix | Call with keyword arguments; `factor` becomes a market setting | [I-13](issues.md#I-13), [I-17](issues.md#I-17) |
| [Validator](../../../src_thesis_reference/marketplace/market/validation.py#L42-L181), [TransactionBlock](../../../src_thesis_reference/marketplace/market/validation.py#L17-L39) | Keep, optional | Audit log only, no effect on outcomes; the largest cost of `env.step`. Off by default; include loss and fees in the hash when on. | [I-66](issues.md#I-66) |

### 3.2 Market: matching

| Code | Verdict | Why / what changes | Issues |
|---|---|---|---|
| [MarketConfig](../../../src_thesis_reference/marketplace/market/matching.py#L22-L83) | Keep + fix | Bounds, mechanism, flags. Units and Δt become explicit. | [I-56](issues.md#I-56) |
| [MatchingResult](../../../src_thesis_reference/marketplace/market/matching.py#L87-L112), [MatchingHistory](../../../src_thesis_reference/marketplace/market/matching.py#L115-L143) | Keep + fix | Drop `grid_balance` / `grid_congestion` (they belong to the assessment); report unmatched P2P volume | [I-38](issues.md#I-38) |
| [match_orders](../../../src_thesis_reference/marketplace/market/matching.py#L240-L450) | Rewrite | Keep the algorithm (Stage 1 preferences → Stage 2 double auction with reputation tie-break → Stage 3 DSO residual). Remove losses, flow updates and the capacity check; do not mutate submitted orders; decide Stage 1 DSO handling and the clearing price. | [I-12](issues.md#I-12), [I-14](issues.md#I-14), [I-15](issues.md#I-15), [I-16](issues.md#I-16), [I-24](issues.md#I-24), [I-32](issues.md#I-32), [I-55](issues.md#I-55) |
| [_match_preferred_partners](../../../src_thesis_reference/marketplace/market/matching.py#L607-L752) | Rewrite | Mutual-preference pairing and its ranking are reusable ideas; the DSO-first sub-stage and the discarded balance update are not | [I-15](issues.md#I-15), [I-25](issues.md#I-25) |
| [_create_trade](../../../src_thesis_reference/marketplace/market/matching.py#L531-L605) | Replace | Exists only to add losses and flows; a lossless trade constructor is a few lines | [I-32](issues.md#I-32) |
| [calculate_market_statistics](../../../src_thesis_reference/marketplace/market/matching.py#L474-L529) | Keep + fix | P2P / DSO volumes and prices feed the observation's market block | — |
| [get_agent_position](../../../src_thesis_reference/marketplace/market/matching.py#L453-L472) | Replace | Superseded by a settlement ledger per agent (energy and cash) | [I-26](issues.md#I-26) |

### 3.3 DSO

| Code | Verdict | Why / what changes | Issues |
|---|---|---|---|
| [DSOAgent tariffs](../../../src_thesis_reference/marketplace/dso/dso.py#L134-L189) (`get_feed_in_tariff`, `get_utility_price`, `get_market_price`) | Keep | SimBench has no prices, so tariffs stay MARLEM's (01 §3.4) | — |
| [clear_unmatched_orders](../../../src_thesis_reference/marketplace/dso/dso.py#L192-L275) | Keep + fix | Stage 3 as in the paper; stop zeroing the caller's orders; record DSO volumes for `B_DSO` | [I-12](issues.md#I-12), [I-24](issues.md#I-24), [I-54](issues.md#I-54) |
| [calculate_fees](../../../src_thesis_reference/marketplace/dso/dso.py#L277-L353) | Rewrite | Keep the eq. 8 term structure and constants; inputs from `assessment[t−1]` and electrical distance; decide `F_trans` and the caps; **charge** the fees to someone | [I-28](issues.md#I-28), [I-29](issues.md#I-29), [I-30](issues.md#I-30), [I-31](issues.md#I-31), [I-74](issues.md#I-74) |
| [validate_grid_constraints](../../../src_thesis_reference/marketplace/dso/dso.py#L356-L401) | Drop | A pre-trade grid check on the NetworkX state; the power flow judges feasibility | [I-54](issues.md#I-54) |
| [_calculate_balance_impact](../../../src_thesis_reference/marketplace/dso/dso.py#L403-L451) | Keep + fix | eq. 8h; its `B_grid` input becomes the external-grid exchange | [I-23](issues.md#I-23) |
| [DSOProfileHandler](../../../src_thesis_reference/adapters/profiles/dso.py#L16-L350) | Keep | Tariff profiles from CSV or synthetic, with `p_utility > p_FiT` enforced; align them to the SimBench day | — |

### 3.4 Agents and battery

| Code | Verdict | Why / what changes | Issues |
|---|---|---|---|
| [DERAgent state](../../../src_thesis_reference/marl/agents/der.py#L24-L129) (`__init__`, `reset`, getters) | Keep + fix | Profiles, capacity, battery, counters. Profiles are passed in, not regenerated; no random balance; `location` becomes a bus ID. | [I-05](issues.md#I-05), [I-27](issues.md#I-27) |
| [adjust_action_for_battery](../../../src_thesis_reference/marl/agents/der.py#L165-L241) | Rewrite | Implement eq. 15 directly; one direction rule; allow "no order" | [I-08](issues.md#I-08), [I-09](issues.md#I-09), [I-11](issues.md#I-11) |
| [update_energy_tracking](../../../src_thesis_reference/marl/agents/der.py#L243-L281), [update_battery_from_trades](../../../src_thesis_reference/marl/agents/der.py#L283-L317) | Rewrite | Replace with one settlement step per agent: energy identity (G + imports + discharge = served D + exports + charge + curtailment), battery dispatch with the correct sign, cash with fees. Its output is also the `ParticipantInjection` for the power flow. | [I-18](issues.md#I-18), [I-21](issues.md#I-21), [I-22](issues.md#I-22), [I-26](issues.md#I-26), [I-27](issues.md#I-27) |
| [select_preferred_partner](../../../src_thesis_reference/marl/agents/der.py#L140-L163) | Rewrite | A weighted score of reputation and electrical distance, as the paper says | [I-77](issues.md#I-77) |
| [get_remaining_demand / supply](../../../src_thesis_reference/marl/agents/der.py#L347-L373) | Keep + fix | Used by the observation; apply the forecast error | [I-39](issues.md#I-39) |
| [Battery](../../../src_thesis_reference/marl/agents/battery.py#L22-L219) | Keep + fix | Partial fill at the SoC limits, `E_out/η` on discharge, a power limit parameter, no random initial SoC unless configured | [I-19](issues.md#I-19), [I-20](issues.md#I-20), [I-71](issues.md#I-71) |
| [ActionHandler](../../../src_thesis_reference/marketplace/action.py#L15-L91) | Keep + fix | The ⟨p, q, α, β⟩ box; make "no preference" reachable (or a discrete β) | [I-10](issues.md#I-10) |

### 3.5 Grid and profiles

| Code | Verdict | Why / what changes | Issues |
|---|---|---|---|
| [GridNetwork](../../../src_thesis_reference/adapters/grid/network.py#L20-L525) (all methods) | Replace | The pandapower adapter ([simbench_new.py](../../../src_thesis/adapters/grid/simbench_new.py)); its catalog part already powers the Studio's Grid page | [I-32](issues.md#I-32), [I-33](issues.md#I-33), [I-34](issues.md#I-34), [I-53](issues.md#I-53), [I-57](issues.md#I-57), [I-70](issues.md#I-70) |
| [get_predefined_config](../../../src_thesis_reference/marketplace/grid/config.py#L10-L97), [GridTopology](../../../src_thesis_reference/marketplace/grid/base.py#L16-L25) | Replace | IEEE-13/34 and procedural graphs; pandapower has real feeders (`case33bw`, CIGRE, Kerber) and SimBench | [I-57](issues.md#I-57) |
| [Location](../../../src_thesis_reference/marketplace/grid/base.py#L27-L71) | Replace | Shrinks to participant ID + bus ID | [I-53](issues.md#I-53) |
| [DERProfileHandler](../../../src_thesis_reference/adapters/profiles/der.py#L16-L250) | Replace; keep the synthetic part | SimBench profiles (`native` / `catalog`, 01 §3.3) replace CSV columns; keep `_random_*_profile` as the `synthetic` source for small tests | [I-05](issues.md#I-05), [I-06](issues.md#I-06), [I-51](issues.md#I-51) |
| [ProfileHandler](../../../src_thesis_reference/adapters/profiles/base.py#L14-L64) | Replace | CSV loading with a random column per reset | [I-06](issues.md#I-06) |

### 3.6 Episode loop, observation, reward

| Code | Verdict | Why / what changes | Issues |
|---|---|---|---|
| [LocalEnergyMarket.__init__ / _check_* / _set_default_values](../../../src_thesis_reference/marketplace/lem.py#L45-L258) | Rewrite | Built by the environment factory from the experiment file (05 §3.7); no hidden defaults | [I-04](issues.md#I-04), [I-39](issues.md#I-39) |
| [reset](../../../src_thesis_reference/marketplace/lem.py#L260-L318) | Rewrite | Episode day from the sampler; one seeded RNG passed down instead of reseeding `np.random` everywhere | [I-03](issues.md#I-03), [I-05](issues.md#I-05), [I-07](issues.md#I-07) |
| [step](../../../src_thesis_reference/marketplace/lem.py#L320-L506) | Rewrite | Same phase order as [P1] §3.9, plus settlement → injections → power flow (01 §6); correct horizon and terminal flag; invalid orders dropped | [I-01](issues.md#I-01), [I-02](issues.md#I-02), [I-12](issues.md#I-12), [I-78](issues.md#I-78) |
| [ObservationHandler](../../../src_thesis_reference/marketplace/observation.py#L23-L378) | Rewrite | Keep the Table 2 layout (16 + 16 + 10); forecasts with error; a real reset observation; scaling decided; grid block from the assessment | [I-39](issues.md#I-39), [I-40](issues.md#I-40), [I-58](issues.md#I-58) |
| [RewardHandler weights and log compression](../../../src_thesis_reference/marketplace/reward.py#L36-L95) | Keep + fix | Weights (10 / 1.5 / 5 / 2 / 3; Σ f = 56) and eq. 3 are the paper's; fix the overwritten `_w_local` | [I-45](issues.md#I-45) |
| [calculate_reward and its components](../../../src_thesis_reference/marketplace/reward.py#L105-L514) | Rewrite | Versioned reward from the recorded decisions: submitted quantities, normalised `f_coop`, one boost form, terminal penalty that fires, no-trade rule decided | [I-41](issues.md#I-41)–[I-47](issues.md#I-47), [I-75](issues.md#I-75), [I-76](issues.md#I-76), [I-79](issues.md#I-79) |
| [ReputationHandler](../../../src_thesis_reference/marketplace/market/reputation.py#L16-L163) | Keep + fix | eq. 12 structure; independent initial draws; reliability from unmatched P2P volume; decide the decay | [I-07](issues.md#I-07), [I-38](issues.md#I-38) |
| [_calculate_grid_impact](../../../src_thesis_reference/marketplace/market/reputation.py#L165-L213) | Replace | From bus-attributed violations, or drop the term | [I-38](issues.md#I-38) |
| [EnvConfigHandler](../../../src_thesis_reference/marketplace/io.py#L24-L261) | Replace | The experiment file (02) is the saved configuration | [I-63](issues.md#I-63) |

### 3.7 Cooperation KPIs, analytics, plots

| Code | Verdict | Why / what changes | Issues |
|---|---|---|---|
| [_get_economic_efficiency_metrics](../../../src_thesis_reference/cooperation/implicit_cooperation.py#L82-L113) | Keep + fix | Liquidity and spread as is; social welfare and volatility after the decisions; add normalisation ranges | [I-36](issues.md#I-36), [I-37](issues.md#I-37), [I-75](issues.md#I-75) |
| [_get_grid_stability_metrics](../../../src_thesis_reference/cooperation/implicit_cooperation.py#L115-L134) | Rewrite | Imbalance from the external-grid exchange, congestion from loading | [I-35](issues.md#I-35), [I-68](issues.md#I-68) |
| [_get_coordination_effectiveness_metrics](../../../src_thesis_reference/cooperation/implicit_cooperation.py#L136-L160) | Keep + fix | Convergence as is; coordination score follows the new imbalance | [I-35](issues.md#I-35) |
| [_get_resource_coordination_metrics](../../../src_thesis_reference/cooperation/implicit_cooperation.py#L162-L233) | Keep | P2P share and flexibility utilisation match eq. 25–26 (rename "self-consumption") | [I-69](issues.md#I-69) |
| [CoordinationMetricsHandler](../../../src_thesis_reference/cooperation/metrics/coordination_metrics.py#L54-L607), [DSOMetricsHandler](../../../src_thesis_reference/cooperation/metrics/dso_metrics.py#L49-L226), [GridMetricsHandler](../../../src_thesis_reference/cooperation/metrics/grid_metrics.py#L49-L298), [MarketMetricsHandler](../../../src_thesis_reference/cooperation/metrics/market_analytics.py#L61-L437) | Drop; salvage | Unaudited reporting code that nothing in the environment calls. Salvage: `_calculate_agent_responsiveness` ([P2] §4.3), `_calculate_surpluses` (real welfare), `_calculate_welfare_gini`. Grid metrics come from the assessment history instead. | [I-65](issues.md#I-65), [I-80](issues.md#I-80) |
| [Plotter](../../../src_thesis_reference/cooperation/visualization/plotter.py#L26-L2389) | Drop | 2 400 lines of figures for the old data; the Studio and the results service replace them. Rebuild only the figures the thesis needs. | — |

### 3.8 RL layer (parked)

| Code | Verdict | Why |
|---|---|---|
| [RLTrainer](../../../src_thesis_reference/marl/train.py#L39-L630), [GroupedLEM](../../../src_thesis_reference/marl/train.py#L633-L722), callbacks | Later (RL) | Useful RLlib plumbing (algorithm configs match [P2] Table 8, PBT, checkpoints). Fix when the environment is validated; hard-coded blocks move to the experiment file (02 §4). Known: [I-49](issues.md#I-49), [I-50](issues.md#I-50), [I-59](issues.md#I-59), [I-60](issues.md#I-60), [I-62](issues.md#I-62), [I-64](issues.md#I-64), [I-72](issues.md#I-72), [I-73](issues.md#I-73). |
| [CTCEModule](../../../src_thesis_reference/marl/ctce.py#L22-L375) | Later (RL) | Matches the paper's CTCE |
| [CTDEModule](../../../src_thesis_reference/marl/ctde.py#L22-L386) | Later (RL), then fix | The acting actor is never trained ([I-48](issues.md#I-48)) |
| [RLInference](../../../src_thesis_reference/marl/inference.py#L22-L321) | Later (RL) | Should use RLlib's action path ([I-61](issues.md#I-61)) |
| [RLProtection, RLAlgorithm, TrainingMode](../../../src_thesis_reference/marl/base.py#L13-L58) | Keep | Small enums and a clip helper |

The environment only has to honour RLlib's `MultiAgentEnv` interface (reset / step / spaces). As long as the rebuilt environment keeps that interface and the Table 2 observation and the ⟨p, q, α, β⟩ action, the parked trainer plugs in unchanged.

[↑ Contents](#contents)

## 4. What happens to the 80 issues

| Group | Issues | In the SimBench edition |
|---|---|---|
| **Resolved by replacement** (the code they live in is not carried over) | [I-06](issues.md#I-06), [I-14](issues.md#I-14), [I-32](issues.md#I-32), [I-33](issues.md#I-33), [I-34](issues.md#I-34), [I-53](issues.md#I-53), [I-54](issues.md#I-54), [I-55](issues.md#I-55), [I-57](issues.md#I-57), [I-63](issues.md#I-63), [I-65](issues.md#I-65) | Close as `wontfix (replaced)` with a pointer to the replacement |
| **Answered by the SimBench design** (a paper question the new grid settles) | [I-23](issues.md#I-23), [I-68](issues.md#I-68), [I-70](issues.md#I-70) | `B_grid` and imbalance from the external-grid exchange; AC power flow instead of linear losses (01 §8) |
| **Carried over: defects in kept or rewritten logic** | [I-01](issues.md#I-01)–[I-05](issues.md#I-05), [I-07](issues.md#I-07)–[I-10](issues.md#I-10), [I-12](issues.md#I-12), [I-13](issues.md#I-13), [I-17](issues.md#I-17)–[I-21](issues.md#I-21), [I-24](issues.md#I-24), [I-26](issues.md#I-26)–[I-28](issues.md#I-28), [I-35](issues.md#I-35), [I-37](issues.md#I-37), [I-38](issues.md#I-38), [I-39](issues.md#I-39), [I-41](issues.md#I-41), [I-43](issues.md#I-43)–[I-46](issues.md#I-46), [I-58](issues.md#I-58), [I-66](issues.md#I-66), [I-69](issues.md#I-69), [I-77](issues.md#I-77)–[I-79](issues.md#I-79) | The rebuilt code must not repeat them. Their issue demos become the new code's acceptance tests. |
| **Carried over: paper decisions** (independent of any codebase) | [I-11](issues.md#I-11), [I-15](issues.md#I-15), [I-16](issues.md#I-16), [I-22](issues.md#I-22), [I-25](issues.md#I-25), [I-29](issues.md#I-29)–[I-31](issues.md#I-31), [I-36](issues.md#I-36), [I-40](issues.md#I-40), [I-42](issues.md#I-42), [I-47](issues.md#I-47), [I-56](issues.md#I-56), [I-71](issues.md#I-71), [I-74](issues.md#I-74)–[I-76](issues.md#I-76), [I-80](issues.md#I-80) | Still need a recorded rule before the component is written |
| **Parked with RL** | [I-48](issues.md#I-48)–[I-50](issues.md#I-50), [I-59](issues.md#I-59)–[I-62](issues.md#I-62), [I-64](issues.md#I-64), [I-72](issues.md#I-72), [I-73](issues.md#I-73) | Stage D, after the environment is validated |
| **Process / data** | [I-51](issues.md#I-51), [I-52](issues.md#I-52), [I-67](issues.md#I-67) | A test gate for the new code; the Case 6 mapping stays unpublished; docs for the new package |

So the rebuild removes 14 issues outright, but 53 describe logic or decisions that apply to any faithful implementation of the paper. **The issue register and the paper decisions are the real asset of the validation work, not the original code.**

[↑ Contents](#contents)

## 5. What the original never had (the new build needs it)

- A **settlement ledger** per agent and step (energy identity, battery dispatch, cash with fees) as the single source for KPIs, observation, reward and grid injections.
- **Submitted vs executed** order quantities kept apart.
- A **participant → bus mapping** and **injection builder** (01 §3, §5).
- One **seeded RNG** threaded through the environment instead of `np.random.seed` in eight places.
- **Scripted baseline policies** (no order, zero-intelligence random, rule-based) to test the environment without RL, and to report next to RL results.
- An **experiment file** that rebuilds any run exactly (02).

[↑ Contents](#contents)

## 6. Proposed build order (RL isolated)

| Step | Build | Reuses | Accepted when |
|---|---|---|---|
| 1 | Units, time step, seeded RNG; `Order`, `Trade`, pricing, `MarketConfig` | §3.1 | Pricing demos I-13, I-17 pass |
| 2 | Battery and DER agent with eq. 15 feasibility and the settlement ledger | §3.4 | Battery and settlement demos (I-08, I-09, I-18–I-21, I-26, I-27) pass; energy identity holds every step |
| 3 | Matching (Stages 1–3, lossless) and DSO residual clearing, tariffs, `B_DSO` | §3.2, §3.3 | Matching demos (I-12, I-15, I-16, I-24, I-38) pass |
| 4 | Grid: participant mapping, injections, one power flow per step (shadow mode) | the adapter | A SimBench episode runs; assessment recorded; `env.step` cost measured (01 §9) |
| 5 | Fees from `assessment[t−1]`, reputation, KPIs re-sourced from the power flow | §3.3, §3.6, §3.7 | Fee, KPI and reputation demos pass; KPIs in their decided ranges |
| 6 | Observation and reward (versioned), episode loop with the right horizon | §3.6 | Loop, observation and reward demos pass (I-01, I-02, I-39, I-41, I-43 …) |
| 7 | Scripted baselines over many days; results in the store | §5 | Baseline results are reproducible from the experiment file |
| 8 | RL: DTDE first, then CTCE, then CTDE (fix I-48) | §3.8 | Stage D acceptance tests of the validation plan |

Steps 1–7 need no Ray at all, so every environment bug is found and fixed before learning is involved.

[↑ Contents](#contents)

## 7. Consequences for the existing plans

- **Validation plan (Stages A–D):** the steps stay as the checklist, but each is satisfied by the *new* code. "Port the fix into the original" becomes "build the component, run its issue demos".
- **Architecture roadmap (decided 2026-09-27):** R1 (was P1) is now "rebuild and validate", and the NetworkX validated release (old P2) is retired. The thesis claim becomes a **paper-faithful reimplementation on SimBench** (already the framing in [issues.md §4](issues.md#4-impact-on-the-published-results)); comparison with the published numbers is qualitative, since the original grid is not reproduced.
- **What you give up:** a like-for-like rerun of the paper's cases on the paper's grid. Given the grid defects ([I-32](issues.md#I-32), [I-33](issues.md#I-33), [I-57](issues.md#I-57)), such a rerun would not reproduce the published figures anyway.

**Decisions:**
1. ~~Adopt the rebuild route and retire the NetworkX validated release?~~ **Yes** (2026-09-27, D-02).
2. ~~New package or rewrite in place?~~ **In place in `src_thesis/`**, same file names; frozen original in `src_thesis_reference/` (2026-09-27, D-04, D-14).
3. Keep the blockchain ledger at all (optional, off by default), or drop it? **Open.**

[↑ Contents](#contents)
