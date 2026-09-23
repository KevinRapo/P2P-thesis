# MARLEM validation plan by level

> Status: **live work plan and issue tracker** for validating MARLEM in `src_thesis/`.
> Written: 2026-09-23 · Branch: `dev`
> The detail behind each issue (paper text, code behaviour, evidence) is in [marlem-paper-vs-code.md](paper-vs-code.md) under the same ID. Status is tracked **here only**.

## 1. How this plan is organised

The plan follows the three levels of [P1] Fig. 2 (the high-level class diagram), in the order **Level 0 → Level 2 → Level 1**:

| Fig. 2 level | Classes in Fig. 2 | `src_thesis/` location |
|---|---|---|
| **Level 0: Platform Marketplace** | `LEM`, `ObservationHandler`, `ActionHandler`, `RewardHandler`, `ReputationHandler`, `OrderMatcher`, `MarketConfig`, `ClearingMechanism`, `MatchingResult`, `Order`, `Trade`, `DSOAgent`, `GridNetwork`, `GridTopology`, `Location`, `Validator`, `TransactionBlock` | `marketplace/` (`lem.py`, `observation.py`, `action.py`, `reward.py`, `market/`, `dso/`, `grid/`), `adapters/grid/network.py` |
| **Level 1: MARL Agents** | `DERAgent`, `Battery`, `RLTrainer`, `RLInference`, `RLAlgorithm`, `TrainingMode` | `marl/` (`agents/`, `train.py`, `inference.py`, `base.py`, `ctce.py`, `ctde.py`) |
| **Level 2: Implicit Cooperation** | `ImplicitCooperation`, `CoordinationMetricsHandler`, `DSOMetricsHandler`, grid and market metrics handlers, `Plotter` | `cooperation/` (`implicit_cooperation.py`, `metrics/`, `visualization/`) |
| *Not in Fig. 2* | Profile handlers, CTCE/CTDE modules, `GroupedLEM`, config I/O | `adapters/profiles/`, `marl/`, `marketplace/io.py` |

**Two classes cross levels, so the plan moves them.** This keeps your Level 0 → 2 → 1 order while respecting what calls what:

- **`DERAgent` and `Battery` are Level 1 in Fig. 2 but are validated in Stage A.** `LEM.step` calls them to turn actions into orders and to settle energy. A market cannot be validated while its participants' energy and cash accounting is wrong. Only the *learning* part of Level 1 is left for last.
- **`ObservationHandler` and `RewardHandler` are Level 0 in Fig. 2 but are validated in Stage C, after Level 2.** Both consume the Level 2 KPIs.

```mermaid
flowchart LR
  subgraph L0[Level 0: Platform Marketplace]
    LEM[LEM step] --> ACT[Action to Order]
    ACT --> MATCH[OrderMatcher + Pricing]
    MATCH --> DSO[DSOAgent fees and balance]
    MATCH --> GRID[GridNetwork flows]
    MATCH --> SET[Settlement: DERAgent + Battery]
    MATCH --> REP[Reputation]
    OBS[ObservationHandler]
    REW[RewardHandler]
  end
  subgraph L2[Level 2: Implicit Cooperation]
    KPI[ImplicitCooperation KPIs]
    MET[Metrics + Plotter]
  end
  subgraph L1[Level 1: MARL learning]
    TRAIN[RLTrainer: DTDE / CTDE / CTCE]
    INF[RLInference]
  end
  SET --> KPI
  GRID --> KPI
  MATCH --> KPI
  KPI --> OBS
  KPI --> REW
  SET --> REW
  DSO --> REW
  KPI --> MET
  OBS --> TRAIN
  REW --> TRAIN
  TRAIN --> LEM
  TRAIN --> INF
```

**Stage order:** A (Level 0 core) → B (Level 2) → C (Level 0 observation and reward) → D (Level 1 learning).

**Rules for every step:**

1. Take the step's **decisions** first. These are Paper-origin issues the paper cannot settle; record each as a one-line rule plus reason, with status `decided`.
2. Write the step's **acceptance test** on a hand-sized case (2–3 agents, 1–3 periods). It must fail on the original code.
3. Port the minimal change (from `marlem-baseline` where it exists). Rerun the test and the evidence trace, and record a before/after.
4. Set the status to `fixed`. Move to the next step only when all of the step's issues are `fixed`, `decided` or `wontfix`.

**Code links** open the exact lines in `src_thesis/` as of 2026-09-23 (the original code). Line numbers shift once a step edits that file, so update the links when you close a step.

**Status values:** `open` → `agreed` (plan and test agreed) → `fixed` / `decided` / `wontfix`.

**Origin:** Paper = the paper's method is unsound or silent. Fidelity = the code deviates from the paper. Code = an internal code defect where the paper is silent.
**Type:** ❌ defect · ⚠️ deviation · ❓ decision needed.

## 2. Root causes that cross levels

Fixing these early clears symptoms in later levels. Check the downstream rows again after the root is fixed; several will close without separate work.

| Root cause (step) | Downstream symptoms |
|---|---|
| I-12: orders mutated in matching (A5) | I-43 reward terms constant (C2). KPIs and info see residuals (B1). |
| I-24: DSO balance ≡ 0 (A6) | I-44 grid reward and DSO penalty inactive (C2). I-38 reputation grid term neutral (A9). Grid-balance observation (C1). |
| I-01: 23-step horizon (A1) | I-02 terminal penalty never applied (C2) |
| I-27: profit never updated (A8) | "Mean profit" observation ≡ 0 (C1) |
| I-18 to I-20: battery sign and efficiency (A8) | Flexibility-utilisation KPI (B1). Battery observations (C1). [P1] Case 5 results. |
| I-32, I-33: grid flows (A7) | Congestion KPI (B1), congestion fee (A6), `f_coop` (C2) |
| I-35, I-68: imbalance definition (B1) | Coordination score (B1). `f_coop` (C2). [P2]'s headline metric. |
| I-36, I-75: unnormalised welfare and `f_coop` (B1, C2) | I-41 `f_coop` ≈ 1811 (C2) |
| I-48: CTDE actor never trained (D1) | Every CTDE result |

## 3. Stage A: Level 0, Platform Marketplace

Market, DSO, grid, ledger and the episode loop, plus the two Level 1 classes that Level 0 physically calls (`DERAgent` action/settlement, `Battery`). The goal is that one hand-sized period produces correct orders, trades, prices, energy, cash and grid state.

### A0. Test harness

- **Components:** — (repository)
- **Why here:** A working `pytest` gate with real assertions, so every later step can add a test that fails before its fix.
- **Decisions needed first:** none
- **Acceptance test:** `pytest -q` collects and runs. A deliberately broken assertion fails.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-52 | Code | ❌ | No functioning test gate: tests without assertions, fixtures that fail, signatures that have drifted | [test_battery.py:L13-L62](../../../tests/test_battery.py#L13-L62)<br>[test_checkpoint.py](../../../tests/test_checkpoint.py) | — | — | open |
| I-53 | Code | ⚠️ | Defensive checks hide bad state (dead capacity check, bare `except`, float-only validators, mutable defaults) | [network.py:L38](../../../src_thesis/adapters/grid/network.py#L38)<br>[network.py:L95-L96](../../../src_thesis/adapters/grid/network.py#L95-L96)<br>[base.py:L56](../../../src_thesis/marketplace/grid/base.py#L56) | — | — | open |

### A1. Episode loop

- **Components:** `LEM` (`reset`, `step`)
- **Why here:** The episode contract everything else sits on: horizon, terminal flag, seeding.
- **Decisions needed first:** none
- **Acceptance test:** `max_steps = 24` gives 24 `step` calls. Only the last returns `terminated`, and it passes `is_terminal=True` to the reward. The same seed replays the episode exactly; `seed=None` advances.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-01 | Fidelity | ❌ | Only 23 of 24 periods run: termination is checked after the step increment against `max_steps − 1` | [lem.py:L443-L453](../../../src_thesis/marketplace/lem.py#L443-L453) | T1 | 2.11 | open |
| I-02 | Fidelity | ❌ | `is_terminal` is never true, so the terminal unmet-demand penalty never applies | [lem.py:L430](../../../src_thesis/marketplace/lem.py#L430)<br>[reward.py:L207-L214](../../../src_thesis/marketplace/reward.py#L207-L214) | T2 | 2.10 | open |
| I-03 | Code | ⚠️ | `reset(seed=None)` falls back to the config seed, so every episode is identical | [lem.py:L272-L274](../../../src_thesis/marketplace/lem.py#L272-L274) | C | 2.11 | open |
| I-04 | Code | ⚠️ | `LocalEnergyMarket.seed()` is shadowed by the `self.seed` attribute | [lem.py:L67](../../../src_thesis/marketplace/lem.py#L67)<br>[lem.py:L507-L514](../../../src_thesis/marketplace/lem.py#L507-L514) | C | 2.11 | open |
| I-78 | Fidelity | ⚠️ | Invalid actions raise `ValueError` instead of being dropped (Alg. 1 `ValidateOrder`) | [lem.py:L342-L343](../../../src_thesis/marketplace/lem.py#L342-L343) | C | 2.2 | open |

### A2. Inputs: profiles and units

- **Components:** Profile handlers (not in Fig. 2)
- **Why here:** The data every level consumes. Units and Δt are decided here once.
- **Decisions needed first:** I-56
- **Acceptance test:** Profiles supplied to an agent survive `reset()` (or the override is explicit). One CSV column maps to one agent deterministically. Units are stated per quantity.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-05 | Code | ⚠️ | Profiles passed to `DERAgent(...)` are overwritten at `reset()` | [lem.py:L280-L293](../../../src_thesis/marketplace/lem.py#L280-L293) | T11 | 2.11 | open |
| I-06 | Fidelity | ⚠️ | CSV profiles use a random column and random scale per reset. Procedural G is additive, not eq. 17's multiplicative form | [base.py:L31-L43](../../../src_thesis/adapters/profiles/base.py#L31-L43)<br>[der.py:L119-L131](../../../src_thesis/adapters/profiles/der.py#L119-L131)<br>[der.py:L172-L198](../../../src_thesis/adapters/profiles/der.py#L172-L198) | C | 2.11 | open |
| I-56 | Paper | ❓ | Units and timestep are inconsistent (W/kW/kWh/Wh, $/Wh vs $/kWh). There is no explicit Δt | [der.py:L35](../../../src_thesis/marl/agents/der.py#L35)<br>[matching.py:L34-L37](../../../src_thesis/marketplace/market/matching.py#L34-L37) | — | — | open |

### A3. Action → order

- **Components:** `ActionHandler`, `DERAgent.adjust_action_for_battery` (Level 1 in Fig. 2), `Order`
- **Why here:** Pulled forward from Level 1 because `LEM.step` calls it before the market.
- **Decisions needed first:** I-11
- **Acceptance test:** For G = 5, D = 30, SoC headroom h and α ∈ {0, 1}: the order quantity equals eq. 15's `q_buy,max` / `q_sell,max` (or the decided rule). α = 0.3 is a sell everywhere.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-08 | Fidelity | ❌ | Feasibility clipping does not implement eq. 15: it treats the requested `q` as the need | [der.py:L196-L228](../../../src_thesis/marl/agents/der.py#L196-L228) | C | 2.1 | open |
| I-09 | Fidelity | ❌ | `is_buy` is truthy in `adjust_action_for_battery` but `> 0.5` in `step`, so the order is sized for the wrong direction | [der.py:L196](../../../src_thesis/marl/agents/der.py#L196)<br>[lem.py:L358](../../../src_thesis/marketplace/lem.py#L358) | T8 | 2.1 | open |
| I-10 | Fidelity | ⚠️ | β = "no preference" is reachable only at the exact upper bound | [action.py:L35-L44](../../../src_thesis/marketplace/action.py#L35-L44)<br>[action.py:L68-L89](../../../src_thesis/marketplace/action.py#L68-L89)<br>[lem.py:L359](../../../src_thesis/marketplace/lem.py#L359) | C | 2.1 | open |
| I-11 | Paper | ❓ | No "submit nothing" action when `q_min > 0` | [der.py:L231-L232](../../../src_thesis/marl/agents/der.py#L231-L232) | — | 2.1 | open |
| I-77 | Fidelity | ⚠️ | Rule-based partner selection is a lexicographic sort plus a random top-half pick, not a weighted score | [der.py:L136-L159](../../../src_thesis/marl/agents/der.py#L136-L159)<br>[lem.py:L362-L365](../../../src_thesis/marketplace/lem.py#L362-L365) | C | 2.2 | open |

### A4. Pricing

- **Components:** `MarketConfig`, `ClearingMechanism`
- **Why here:** The smallest pure functions in the model. A good first fix.
- **Decisions needed first:** none
- **Acceptance test:** For every mechanism with buy = 200, sell = 50, ref = 100: the expected value from eq. 9–11 (check eq. 11 against the rendered PDF).

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-13 | Fidelity | ❌ | `SELLER` pricing returns the buyer's price (positional-argument bug) | [mechanism.py:L69-L84](../../../src_thesis/marketplace/market/mechanism.py#L69-L84)<br>[matching.py:L324-L326](../../../src_thesis/marketplace/market/matching.py#L324-L326) | T6 | 2.3 | open |
| I-17 | Fidelity | ❌ | `BID_ASK_SPREAD` pricing receives `market_price` as `factor`, so it returns the buyer's price. The mechanism is also absent from §3.3.3 | [mechanism.py:L87-L111](../../../src_thesis/marketplace/market/mechanism.py#L87-L111)<br>[matching.py:L324-L326](../../../src_thesis/marketplace/market/matching.py#L324-L326) | T12 | 2.3 | open |

### A5. Matching

- **Components:** `OrderMatcher`, `MatchingResult`, `Trade`
- **Why here:** Stages 1–3 of Algorithm 1.
- **Decisions needed first:** I-15, I-16
- **Acceptance test:** A hand case with 2 sellers and 1 buyer at known prices gives the expected trades, quantities and clearing price. Submitted orders are unchanged after matching.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-12 | Code | ❌ | Orders are mutated in place, so the reward, KPIs and info see residual quantities (0), not submitted ones | [matching.py:L361-L362](../../../src_thesis/marketplace/market/matching.py#L361-L362)<br>[dso.py:L212-L253](../../../src_thesis/marketplace/dso/dso.py#L212-L253)<br>[lem.py:L424-L431](../../../src_thesis/marketplace/lem.py#L424-L431) | T3 | 2.2 | open |
| I-14 | Fidelity | ⚠️ | P2P loss is topped up from the DSO. The buyer's `energy_bought` counts `q + loss` | [matching.py:L361](../../../src_thesis/marketplace/market/matching.py#L361)<br>[lem.py:L392-L411](../../../src_thesis/marketplace/lem.py#L392-L411) | C | 2.2 | open |
| I-15 | Paper | ❓ | Stage 1 clears DSO-preferred orders with the DSO before any P2P matching | [matching.py:L620-L647](../../../src_thesis/marketplace/market/matching.py#L620-L647) | — | 2.2 | open |
| I-16 | Paper | ❓ | The clearing price is a VWAP that includes DSO trades | [matching.py:L399](../../../src_thesis/marketplace/market/matching.py#L399) | — | 2.2 | open |
| I-54 | Code | ⚠️ | DSO fallback skips grid feasibility (zero distance, loss and fee), and `validate_grid_constraints` ignores direction | [dso.py:L190-L272](../../../src_thesis/marketplace/dso/dso.py#L190-L272)<br>[dso.py:L347-L392](../../../src_thesis/marketplace/dso/dso.py#L347-L392) | — | 2.2 | open |
| I-55 | Code | ❌ | The Stage-2 capacity check uses `max_quantity·N` and the current balance, not grid capacity or the projected trade | [matching.py:L172](../../../src_thesis/marketplace/market/matching.py#L172)<br>[matching.py:L312-L313](../../../src_thesis/marketplace/market/matching.py#L312-L313) | C | 2.2 | open |

### A6. DSO: balance and fees

- **Components:** `DSOAgent`
- **Why here:** The DSO's balance (eq. 7) and fees (eq. 8).
- **Decisions needed first:** I-29, I-74
- **Acceptance test:** `B_DSO` after one step equals `Σ(E_sold − E_bought)` over DSO trades, with one sign convention. Each fee term matches eq. 8 on a hand case, and the total is charged to the decided payer.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-24 | Fidelity | ❌ | `dso.balance` changes only on Stage-1 DSO-preferred trades and carries across steps, so it is ≡ 0 by default | [matching.py:L272-L280](../../../src_thesis/marketplace/market/matching.py#L272-L280)<br>[matching.py:L388](../../../src_thesis/marketplace/market/matching.py#L388) | T4 | 2.4 | open |
| I-25 | Code | ❓ | The B_DSO sign convention is inconsistent between `match_orders` and `_match_preferred_partners` | [matching.py:L272-L280](../../../src_thesis/marketplace/market/matching.py#L272-L280)<br>[matching.py:L640-L647](../../../src_thesis/marketplace/market/matching.py#L640-L647) | C | 2.4 | open |
| I-28 | Fidelity | ❌ | Grid fees are computed but never charged to anyone | [dso.py:L342-L343](../../../src_thesis/marketplace/dso/dso.py#L342-L343)<br>[matching.py:L333-L346](../../../src_thesis/marketplace/market/matching.py#L333-L346) | C | 2.4 | open |
| I-29 | Paper | ❓ | `F_trans` has no formula in the paper; the code uses 0 | [dso.py:L293](../../../src_thesis/marketplace/dso/dso.py#L293) | — | 2.4 | open |
| I-30 | Fidelity | ⚠️ | `F_volt` and `F_thermal` caps (0.2, 0.3) differ from or are undefined in the paper | [dso.py:L326-L333](../../../src_thesis/marketplace/dso/dso.py#L326-L333) | C | 2.4 | open |
| I-31 | Fidelity | ⚠️ | `F_imb` is effectively always 0 | [dso.py:L336-L339](../../../src_thesis/marketplace/dso/dso.py#L336-L339)<br>[dso.py:L394-L442](../../../src_thesis/marketplace/dso/dso.py#L394-L442) | C | 2.4 | open |
| I-74 | Paper | ⚠️ | Thermal-fee threshold (20 %) sits below the congestion threshold (80 %) | [dso.py:L65-L67](../../../src_thesis/marketplace/dso/dso.py#L65-L67) | — | 2.4 | open |

### A7. Grid

- **Components:** `GridNetwork`, `GridTopology`, `Location`
- **Why here:** Graph, losses and congestion (eq. 18–19).
- **Decisions needed first:** I-70
- **Acceptance test:** IEEE-34 is connected. Flows at the start of a period are the decided baseline. After one trade of `q` along a known path, each edge flow and the congestion match a hand calculation.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-32 | Fidelity | ❌ | Only Stage-1 trades update edge flows | [matching.py:L589](../../../src_thesis/marketplace/market/matching.py#L589)<br>[matching.py:L282-L370](../../../src_thesis/marketplace/market/matching.py#L282-L370) | C | 2.6 | open |
| I-33 | Fidelity | ❌ | Edge flows start random and accumulate over the episode instead of being per period | [network.py:L85](../../../src_thesis/adapters/grid/network.py#L85)<br>[network.py:L325](../../../src_thesis/adapters/grid/network.py#L325) | T10 | 2.6 | open |
| I-34 | Code | ⚠️ | Loss factor κ = 0.03 is hard-coded | [network.py:L331-L348](../../../src_thesis/adapters/grid/network.py#L331-L348) | C | 2.6 | open |
| I-57 | Fidelity | ❌ | IEEE-34 graph is disconnected (edge 832–888 missing), and the impedance table is unused | [config.py:L29-L39](../../../src_thesis/marketplace/grid/config.py#L29-L39)<br>[config.py:L43-L75](../../../src_thesis/marketplace/grid/config.py#L43-L75)<br>[network.py:L133](../../../src_thesis/adapters/grid/network.py#L133) | T13 | 2.6 | open |
| I-70 | Paper | ❓ | Grid physics scope: linear unbounded losses, `V_drop = f·d`, transport flows. "High-fidelity" is an overclaim | [network.py:L331-L348](../../../src_thesis/adapters/grid/network.py#L331-L348)<br>[dso.py:L326-L328](../../../src_thesis/marketplace/dso/dso.py#L326-L328) | — | 3 | open |

### A8. Settlement: energy and cash

- **Components:** `DERAgent` accounting, `Battery` (Level 1 in Fig. 2)
- **Why here:** Pulled forward from Level 1 because settlement is a Level 0 physical outcome. This is where conservation lives.
- **Decisions needed first:** I-22, I-71
- **Acceptance test:** Per agent and step, `G + imports + discharge = served D + exports + charge + curtailment`. Profit (eq. 14) changes by `Σ p·q` minus fees. Selling with G = D discharges. The battery respects SoC limits, η and any decided power limit. `B_grid` (eq. 20) is computed.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-18 | Fidelity | ❌ | Battery dispatch has the trade term's sign reversed: selling charges the battery | [der.py:L293-L305](../../../src_thesis/marl/agents/der.py#L293-L305) | T7 | 2.5 | open |
| I-19 | Fidelity | ❌ | A charge is refused entirely if it would reach SoC_max; there is no partial fill | [battery.py:L95-L111](../../../src_thesis/marl/agents/battery.py#L95-L111)<br>[battery.py:L131-L156](../../../src_thesis/marl/agents/battery.py#L131-L156) | C | 2.5 | open |
| I-20 | Fidelity | ❌ | Discharge efficiency is applied in the wrong direction (`·η` instead of `/η`) | [battery.py:L158-L176](../../../src_thesis/marl/agents/battery.py#L158-L176) | C | 2.5 | open |
| I-21 | Code | ⚠️ | Demand satisfaction ignores battery discharge | [der.py:L250-L262](../../../src_thesis/marl/agents/der.py#L250-L262) | C | 2.5 | open |
| I-22 | Paper | ❓ | No household energy-conservation identity is enforced | [lem.py:L391-L411](../../../src_thesis/marketplace/lem.py#L391-L411) | — | 2.5 | open |
| I-23 | Fidelity | ❌ | `B_grid` (eq. 20) is never computed. The "grid balance" observation is `dso.balance` | [lem.py:L472](../../../src_thesis/marketplace/lem.py#L472)<br>[observation.py:L285](../../../src_thesis/marketplace/observation.py#L285) | C | 2.6 | open |
| I-26 | Fidelity | ⚠️ | `agent.balance = sold − bought`, not eq. 13 | [lem.py:L440](../../../src_thesis/marketplace/lem.py#L440)<br>[matching.py:L440-L459](../../../src_thesis/marketplace/market/matching.py#L440-L459) | C | 2.5 | open |
| I-27 | Fidelity | ❌ | Agent profit (eq. 14) is never updated | [der.py:L61](../../../src_thesis/marl/agents/der.py#L61)<br>[der.py:L109](../../../src_thesis/marl/agents/der.py#L109)<br>[observation.py:L342](../../../src_thesis/marketplace/observation.py#L342) | T5 | 2.5 | open |
| I-71 | Paper | ❓ | Battery model has no charge/discharge power limit (claimed in the text), and eq. 15 ignores efficiency | [battery.py:L131-L176](../../../src_thesis/marl/agents/battery.py#L131-L176)<br>[battery.py:L205-L214](../../../src_thesis/marl/agents/battery.py#L205-L214) | — | 2.5 | open |

### A9. Reputation

- **Components:** `ReputationHandler`
- **Why here:** Eq. 12. Used as the tie-break in Stage 2.
- **Decisions needed first:** none
- **Acceptance test:** On a hand case, each of the three components and the decayed score match a hand calculation. Agents' initial reputations are independent draws.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-07 | Code | ⚠️ | All agents get the same initial reputation (the RNG is reseeded before each draw) | [lem.py:L283](../../../src_thesis/marketplace/lem.py#L283)<br>[reputation.py:L56-L68](../../../src_thesis/marketplace/market/reputation.py#L56-L68) | C | 2.7 | open |
| I-38 | Code | ⚠️ | Reputation: reliability ≡ 1, the grid term is neutral, and decay is weighted by time of day | [reputation.py:L129](../../../src_thesis/marketplace/market/reputation.py#L129)<br>[reputation.py:L87](../../../src_thesis/marketplace/market/reputation.py#L87) | C | 2.7 | open |

### A10. Ledger

- **Components:** `Validator`, `TransactionBlock`
- **Why here:** Audit chain only; no effect on outcomes.
- **Decisions needed first:** none
- **Acceptance test:** The block hash covers every settlement field. Tampering with a fee breaks `verify_chain()`.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-66 | Code | ⚠️ | The block hash omits loss and fees, and blocks are forced every step (in-memory PoW, not consensus) | [validation.py:L25-L34](../../../src_thesis/marketplace/market/validation.py#L25-L34)<br>[matching.py:L410](../../../src_thesis/marketplace/market/matching.py#L410) | — | 2.2 | open |

## 4. Stage B: Level 2, Implicit Cooperation

The KPIs computed from Stage A's outcomes. They can only be validated once A is correct, because they are functions of its output.

### B1. Cooperation KPIs

- **Components:** `ImplicitCooperation`
- **Why here:** The 10 shared KPIs (eq. 21–27) that feed both the observation and the reward.
- **Decisions needed first:** I-36, I-68, I-69
- **Acceptance test:** On a fixed hand episode (from A5–A8), each KPI matches its decided definition and range. None is identically 0 or unbounded by construction.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-35 | Fidelity | ❌ | "Supply-demand imbalance" is volume/C, not `\|Σbuy − Σsell\|/C`. The coordination score inherits this | [implicit_cooperation.py:L122-L123](../../../src_thesis/cooperation/implicit_cooperation.py#L122-L123)<br>[implicit_cooperation.py:L141-L142](../../../src_thesis/cooperation/implicit_cooperation.py#L141-L142) | C | 2.8 | open |
| I-36 | Paper | ❓ | Social welfare is turnover `Σ p·q`, not surplus | [implicit_cooperation.py:L93](../../../src_thesis/cooperation/implicit_cooperation.py#L93) | — | 2.8 | open |
| I-37 | Fidelity | ⚠️ | Price volatility is computed over the whole episode, not a window | [implicit_cooperation.py:L104-L105](../../../src_thesis/cooperation/implicit_cooperation.py#L104-L105) | C | 2.8 | open |
| I-68 | Paper | ❓ | Imbalance (eq. 24) over trades is ≡ 0 by construction. Needs a definition over orders or physical net positions, and a timing (before or after DSO clearing) for `B_grid` | [implicit_cooperation.py:L122-L123](../../../src_thesis/cooperation/implicit_cooperation.py#L122-L123) | — | 3 | open |
| I-69 | Paper | ⚠️ | "DER self-consumption" is defined as P2P share; the label does not match the quantity | [implicit_cooperation.py:L188](../../../src_thesis/cooperation/implicit_cooperation.py#L188) | — | 2.8 | open |

### B2. Metrics and plots

- **Components:** `CoordinationMetricsHandler`, `DSOMetricsHandler`, grid and `MarketMetricsHandler`, `Plotter`
- **Why here:** Reporting only. They do not affect learning.
- **Decisions needed first:** none
- **Acceptance test:** Each reported metric is either the B1 KPI or has its own stated definition. Unsupported metrics are removed or relabelled.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-65 | Code | ❌ | `src/analytics` reports welfare, grid and coordination concepts without the required inputs | [market_analytics.py:L123-L136](../../../src_thesis/cooperation/metrics/market_analytics.py#L123-L136) | — | — | open |

## 5. Stage C: Level 0 agent interface (observation and reward)

These are drawn in Level 0 in Fig. 2 but consume Level 2 KPIs, so they come after B. The reward is the paper's main contribution.

### C1. Observation

- **Components:** `ObservationHandler`
- **Why here:** Level 0 in Fig. 2, but it consumes Level 2 KPIs, so it is validated after B.
- **Decisions needed first:** I-40
- **Acceptance test:** Each of the 42 entries equals its source value (or forecast). The reset observation is consistent with the reset state. The dimension equals Table 2.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-39 | Fidelity | ❌ | Forecast error (`max_error`) is never applied, so the "remaining demand/supply" observations reveal the true future | [lem.py:L65-L66](../../../src_thesis/marketplace/lem.py#L65-L66)<br>[observation.py:L338-L341](../../../src_thesis/marketplace/observation.py#L338-L341) | C | 2.9 | open |
| I-40 | Paper | ❓ | Observations are raw and unnormalised | [observation.py:L333-L353](../../../src_thesis/marketplace/observation.py#L333-L353) | — | 2.9 | open |
| I-58 | Code | ⚠️ | The reset observation hard-codes G, D, remaining energy and KPIs to 0 | [observation.py:L195-L257](../../../src_thesis/marketplace/observation.py#L195-L257) | — | 2.9 | open |

### C2. Reward

- **Components:** `RewardHandler`
- **Why here:** Level 0 in Fig. 2, but it consumes Level 2 KPIs. This is the thesis's central mechanism (eq. 3–6).
- **Decisions needed first:** I-42, I-47, I-75, I-76
- **Acceptance test:** On the fixed hand steps, each component (`r_grid` … `γ_UD`), `f_coop` ∈ [0, 1], `f_contrib` and the final `R_i` match a hand calculation. The ordering P2P > DSO > unmet demand holds.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-41 | Fidelity | ❌ | `f_coop` is not in [0, 1] (≈ 1811) | [reward.py:L170-L192](../../../src_thesis/marketplace/reward.py#L170-L192) | T9 | 2.10 | open |
| I-42 | Paper | ❓ | The cooperation-boost form differs across [P1] eq. 4, the code and [P2] eq. 3 | [reward.py:L218-L221](../../../src_thesis/marketplace/reward.py#L218-L221) | — | 2.10 | open |
| I-43 | Code | ❌ | `r_res ≡ −1.5` and `r_trade ≡ 0` (caused by I-12) | [reward.py:L406-L412](../../../src_thesis/marketplace/reward.py#L406-L412)<br>[reward.py:L248-L249](../../../src_thesis/marketplace/reward.py#L248-L249) | T3 | 2.10 | open |
| I-44 | Fidelity | ❌ | `r_grid`, `γ_DSO` and the grid part of `f_contrib` are inactive (caused by I-24) | [reward.py:L202](../../../src_thesis/marketplace/reward.py#L202)<br>[reward.py:L253-L309](../../../src_thesis/marketplace/reward.py#L253-L309)<br>[reward.py:L472-L484](../../../src_thesis/marketplace/reward.py#L472-L484) | T4 | 2.10 | open |
| I-45 | Code | ⚠️ | `_w_local` is overwritten 0.7 → 0.3, so `r_trade = 0.3ρ_local + 0.3ρ_dso` (the paper prints 0.3/0.3) | [reward.py:L79](../../../src_thesis/marketplace/reward.py#L79)<br>[reward.py:L93](../../../src_thesis/marketplace/reward.py#L93) | C | 2.10 | open |
| I-46 | Fidelity | ⚠️ | The unmet-demand penalty uses `p_dso`, not the paper's `p_no_trades = 5` | [reward.py:L207-L214](../../../src_thesis/marketplace/reward.py#L207-L214)<br>[reward.py:L226](../../../src_thesis/marketplace/reward.py#L226) | C | 2.10 | open |
| I-47 | Paper | ❓ | The no-trade guard returns a fixed −4.46 before any other term | [reward.py:L135-L136](../../../src_thesis/marketplace/reward.py#L135-L136) | — | 2.10 | open |
| I-75 | Paper | ❓ | `f_coop` has no normalisation ranges for its unbounded KPIs, so the [0, 1] claim is unsupported | [reward.py:L170-L192](../../../src_thesis/marketplace/reward.py#L170-L192)<br>[implicit_cooperation.py:L93](../../../src_thesis/cooperation/implicit_cooperation.py#L93) | — | 3 | open |
| I-76 | Paper | ❓ | `R_base` components have no formulas in the paper; the code is the only specification | [reward.py:L148-L166](../../../src_thesis/marketplace/reward.py#L148-L166) | — | 2.10 | open |
| I-79 | Fidelity | ⚠️ | `f_contrib` grid term is a heuristic, not [P2]'s marginal `−∂\|B_grid\|/∂a_i` | [reward.py:L472-L484](../../../src_thesis/marketplace/reward.py#L472-L484) | C | 2.10 | open |

## 6. Stage D: Level 1, MARL Agents (learning)

The learning layer, last. It needs a correct environment, observations and rewards before any training result means anything.

### D1. Training paradigms

- **Components:** `RLTrainer`, `TrainingMode`, `RLAlgorithm` (plus the CTCE/CTDE modules and `GroupedLEM`, not in Fig. 2)
- **Why here:** The MARL layer.
- **Decisions needed first:** I-50, I-60, I-73
- **Acceptance test:** For each of the 9 mode × algorithm combinations: the acting weights change after one update. CTDE acts with the actor it trains. Agent order is preserved through grouping. Short runs beat the fixed no-order and random policies on physical outcomes.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-48 | Fidelity | ❌ | CTDE trains a centralized `pi` but acts with per-agent `pi_heads`, which are never trained | [ctde.py:L47-L56](../../../src_thesis/marl/ctde.py#L47-L56)<br>[ctde.py:L74-L87](../../../src_thesis/marl/ctde.py#L74-L87)<br>[ctde.py:L124-L125](../../../src_thesis/marl/ctde.py#L124-L125) | C | 2.12 | open |
| I-49 | Code | ⚠️ | The PBT lr domain [1e-4, 1e-2] excludes the initial 1e-5, and the entropy domain reaches 10 | [train.py:L180-L195](../../../src_thesis/marl/train.py#L180-L195)<br>[train.py:L216](../../../src_thesis/marl/train.py#L216) | C | 2.12 | open |
| I-50 | Paper | ❓ | The budget is counted in training iterations, but the paper says "10 000 episodes" | [train.py:L440](../../../src_thesis/marl/train.py#L440) | — | 2.12 | open |
| I-59 | Code | ❌ | Grouped obs/action tuples may be assigned to the wrong agents: insertion order vs sorted keys | [train.py:L646](../../../src_thesis/marl/train.py#L646)<br>[train.py:L681](../../../src_thesis/marl/train.py#L681)<br>[train.py:L702](../../../src_thesis/marl/train.py#L702) | — | 2.12 | open |
| I-60 | Paper | ❓ | CTCE is a centralized-information baseline, not a true upper bound. The group reward sum scales with N | [train.py:L684](../../../src_thesis/marl/train.py#L684) | — | 2.12 | open |
| I-62 | Code | ⚠️ | Training config defects: positive `evaluation_duration` rejected, CPUs double-allocated, PBT always on, no `finally` around `ray.shutdown` | [train.py:L116](../../../src_thesis/marl/train.py#L116)<br>[train.py:L285-L294](../../../src_thesis/marl/train.py#L285-L294)<br>[train.py:L432](../../../src_thesis/marl/train.py#L432)<br>[train.py:L449-L458](../../../src_thesis/marl/train.py#L449-L458) | — | 2.12 | open |
| I-73 | Paper | ❓ | Cross-paradigm return comparability: group sum vs per-agent returns | [train.py:L684](../../../src_thesis/marl/train.py#L684) | — | 3 | open |

### D2. Inference

- **Components:** `RLInference`
- **Why here:** Uses RLlib's own action path.
- **Decisions needed first:** none
- **Acceptance test:** A restored checkpoint gives the same actions as the trainer's evaluation for the same observation.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-61 | Code | ❌ | Standalone inference samples and clips actions itself instead of using RLlib's action path, and reads `info` wrongly | [inference.py:L146-L216](../../../src_thesis/marl/inference.py#L146-L216)<br>[inference.py:L235](../../../src_thesis/marl/inference.py#L235) | — | — | open |

### D3. Experiments and reporting

- **Components:** Case notebooks, config I/O, manifests
- **Why here:** What the thesis numbers come from.
- **Decisions needed first:** I-51, I-72, I-80
- **Acceptance test:** A saved run reconstructs its scenario exactly. Several seeds are reported. The Case 6 data status is labelled.

| ID | Origin | Type | Issue | Code | Ev. | § | Status |
|---|---|---|---|---|---|---|---|
| I-51 | Paper | ❓ | The Case 6 profile-to-agent mapping is unpublished | [case6_implicit_cooperation.ipynb](../../../notebooks/case6_implicit_cooperation.ipynb) | — | 2.12 | open |
| I-63 | Code | ⚠️ | The saved env config cannot reconstruct the scenario (seeds, profile sources, rounding) | [io.py:L111](../../../src_thesis/marketplace/io.py#L111)<br>[io.py:L145-L146](../../../src_thesis/marketplace/io.py#L145-L146)<br>[io.py:L55](../../../src_thesis/marketplace/io.py#L55) | — | — | open |
| I-64 | Code | ⚠️ | No run manifests, non-learning baselines or multi-seed statistics | [train.py:L439](../../../src_thesis/marl/train.py#L439)<br>[train.py:L391](../../../src_thesis/marl/train.py#L391) | — | — | open |
| I-67 | Code | ⚠️ | README, notebooks and docs describe a different repository state | [README.md](../../../README.md)<br>tests.md (removed from this repo; see upstream `marlem-main`) | — | — | open |
| I-72 | Paper | ❓ | [P2] protocol: one fixed seed, evaluation on the training scenario, ranking by shaped reward | [train.py:L275-L294](../../../src_thesis/marl/train.py#L275-L294)<br>[lem.py:L272-L274](../../../src_thesis/marketplace/lem.py#L272-L274) | — | 3 | open |
| I-80 | Paper | ❓ | [P2] evaluation metric `B_index` is undefined in the paper and absent from the code | — | C | 2.12 | open |

## 7. Progress summary

Update this table when statuses change.

| Stage | Steps | Issues | Open |
|---|---|---|---|
| A: Level 0, Platform Marketplace | A0, A1, A2, A3, A4, A5, A6, A7, A8, A9, A10 | 47 | 47 |
| B: Level 2, Implicit Cooperation | B1, B2 | 6 | 6 |
| C: Level 0 agent interface (observation and reward) | C1, C2 | 13 | 13 |
| D: Level 1, MARL Agents (learning) | D1, D2, D3 | 14 | 14 |
| **Total** | | **80** | **80** |
