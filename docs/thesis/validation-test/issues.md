# MARLEM validation: issue register

> The **single source** for every issue: its text, the exact code lines, the evidence and the live status. Every other document cites issues by ID (`I-xx`) and links here; only this file is edited when an issue changes.
> The description is of the **original** code (frozen 2026-09-23; line numbers updated 2026-09-24 when the code markers were added). The status column is live.
> Legends and the ID scheme: [README.md](README.md#legends). Paper vs code per equation: [methodology.md](methodology.md). Work order: [plan.md](plan.md).

## 1. Evidence

- **T*n*** means confirmed by running [evidence/trace_original_episode.py](evidence/trace_original_episode.py). It uses 3 agents, a mesh grid, seeded random actions and the original code. Run it with the `marlem` conda env.
- **C** means confirmed by reading the code only. **—** means a judgment (paper-origin items) or taken from the earlier audit.

| Id | Observation |
|---|---|
| T1 | Episode with `max_steps=24` executes **23** steps. |
| T2 | `is_terminal=True` is never passed to the reward. |
| T3 | `order.quantity` seen by the reward is always **0**. |
| T4 | `dso.balance` stays at **0.0** for the whole episode (default rule-based partner selection). |
| T5 | `agent.profit` is never non-zero. |
| T6 | `SELLER` pricing with buy=200 and sell=50 returns **200**. |
| T7 | Selling 10 kWh with G = D *charges* the battery: 50 → 60. |
| T8 | Raw `is_buy=0.3` is sized with buy logic but submitted as a sell order. |
| T9 | `f_coop` ≈ **1811**. The paper says it lies in [0, 1]. |
| T10 | Congestion never decreases within an episode. |
| T11 | Profiles passed to `DERAgent(...)` are replaced at `reset()`. |
| T12 | `BID_ASK_SPREAD` pricing with buy=200, sell=50 and market=100 returns **200**. |
| T13 | The IEEE-34 graph is **not connected**: nodes 888–890 form an island. |

## 2. Register

| Column | Meaning |
|---|---|
| **Class** | The [P1] Fig. 2 class (or module outside Fig. 2) the issue lives in. The fault maps in [plan.md](plan.md#2-fault-map) are generated from it. |
| **Step** | The validation step in [plan.md](plan.md) that fixes or decides it. The code marker carries the same step. |
| **Origin** | Paper, Fidelity or Code ([legend](README.md#legends)). |
| **Type** | ❌ defect · ⚠️ deviation · ❓ decision needed. Sets the code marker tag: `FAULT` / `DEVIATION` / `DECIDE`. |
| **Status** | `open` → `agreed` → `fixed` / `decided` / `wontfix`. Edit it **here only**. |
| **Code** | Exact lines in `src_thesis/`. Each points at the line below the issue's code marker. |
| **Method §** | The methodology section whose "Implementation" table covers it. |
| **Old ID** | The ID in the archived fix plan ([archive/validation-plan-fix.md](archive/validation-plan-fix.md)); `—` if that plan does not list it. Reverse lookup in §6. |

**Totals** (generated):

<!-- BEGIN generated:register-totals -->
| Origin | ❌ | ⚠️ | ❓ | Total |
|---|---|---|---|---|
| Paper | 0 | 2 | 21 | 23 |
| Fidelity | 21 | 11 | 0 | 32 |
| Code | 7 | 17 | 1 | 25 |
| **Total** | **28** | **30** | **22** | **80** |
<!-- END generated:register-totals -->

| ID | Class | Step | Origin | Type | Status | Issue | Code | Ev. | Method § | Old ID |
|---|---|---|---|---|---|---|---|---|---|---|
| <a id="I-01"></a>I-01 | LocalEnergyMarket | A1 | Fidelity | ❌ | open | Only 23 of 24 periods run: termination is checked after the step increment against `max_steps − 1` | [lem.py:L459-L469](../../../src_thesis/marketplace/lem.py#L459-L469) | T1 | [§3](methodology.md#implementation-in-the-original-code-3-loop) | P0-07 |
| <a id="I-02"></a>I-02 | LocalEnergyMarket, RewardHandler | A1 | Fidelity | ❌ | open | `is_terminal` is never true, so the terminal unmet-demand penalty never applies | [lem.py:L444](../../../src_thesis/marketplace/lem.py#L444)<br>[reward.py:L216-L223](../../../src_thesis/marketplace/reward.py#L216-L223) | T2 | [§3](methodology.md#implementation-in-the-original-code-3-loop) | P0-07 |
| <a id="I-03"></a>I-03 | LocalEnergyMarket | A1 | Code | ⚠️ | open | `reset(seed=None)` falls back to the config seed, so every episode is identical | [lem.py:L276-L278](../../../src_thesis/marketplace/lem.py#L276-L278) | C | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | P2-01 |
| <a id="I-04"></a>I-04 | LocalEnergyMarket | A1 | Code | ⚠️ | open | `LocalEnergyMarket.seed()` is shadowed by the `self.seed` attribute | [lem.py:L69](../../../src_thesis/marketplace/lem.py#L69)<br>[lem.py:L525-L532](../../../src_thesis/marketplace/lem.py#L525-L532) | C | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | — |
| <a id="I-05"></a>I-05 | LocalEnergyMarket | A2 | Code | ⚠️ | open | Profiles passed to `DERAgent(...)` are overwritten at `reset()` | [lem.py:L285-L299](../../../src_thesis/marketplace/lem.py#L285-L299) | T11 | [§3](methodology.md#implementation-in-the-original-code-3-loop) | P0-08 |
| <a id="I-06"></a>I-06 | DERProfileHandler, ProfileHandler | A2 | Fidelity | ⚠️ | open | CSV profiles use a random column and random scale per reset. Procedural G is additive, not eq. 17's multiplicative form | [base.py:L32-L44](../../../src_thesis/adapters/profiles/base.py#L32-L44)<br>[der.py:L120-L132](../../../src_thesis/adapters/profiles/der.py#L120-L132)<br>[der.py:L174-L200](../../../src_thesis/adapters/profiles/der.py#L174-L200) | C | [§5](methodology.md#implementation-in-the-original-code-5-agents) | P2-03 |
| <a id="I-07"></a>I-07 | LocalEnergyMarket, ReputationHandler | A9 | Code | ⚠️ | open | All agents get the same initial reputation (the RNG is reseeded before each draw) | [lem.py:L289](../../../src_thesis/marketplace/lem.py#L289)<br>[reputation.py:L57-L69](../../../src_thesis/marketplace/market/reputation.py#L57-L69) | C | [§3](methodology.md#implementation-in-the-original-code-3-loop) | P0-08 |
| <a id="I-08"></a>I-08 | DERAgent | A3 | Fidelity | ❌ | open | Feasibility clipping does not implement eq. 15: it treats the requested `q` as the need | [der.py:L202-L234](../../../src_thesis/marl/agents/der.py#L202-L234) | C | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | P0-02 |
| <a id="I-09"></a>I-09 | LocalEnergyMarket, DERAgent | A3 | Fidelity | ❌ | open | `is_buy` is truthy in `adjust_action_for_battery` but `> 0.5` in `step`, so the order is sized for the wrong direction | [der.py:L202](../../../src_thesis/marl/agents/der.py#L202)<br>[lem.py:L366](../../../src_thesis/marketplace/lem.py#L366) | T8 | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | P0-03 |
| <a id="I-10"></a>I-10 | ActionHandler | A3 | Fidelity | ⚠️ | open | β = "no preference" is reachable only at the exact upper bound | [action.py:L36-L45](../../../src_thesis/marketplace/action.py#L36-L45)<br>[action.py:L70-L91](../../../src_thesis/marketplace/action.py#L70-L91)<br>[lem.py:L368](../../../src_thesis/marketplace/lem.py#L368) | C | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | P0-03 |
| <a id="I-11"></a>I-11 | DERAgent | A3 | Paper | ❓ | open | No "submit nothing" action when `q_min > 0` | [der.py:L238-L239](../../../src_thesis/marl/agents/der.py#L238-L239) | — | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | P0-02 |
| <a id="I-12"></a>I-12 | OrderMatcher, Order, DSOAgent | A5 | Code | ❌ | open | Orders are mutated in place, so the reward, KPIs and info see residual quantities (0), not submitted ones | [matching.py:L370-L371](../../../src_thesis/marketplace/market/matching.py#L370-L371)<br>[dso.py:L215-L256](../../../src_thesis/marketplace/dso/dso.py#L215-L256)<br>[lem.py:L437-L445](../../../src_thesis/marketplace/lem.py#L437-L445) | T3 | [§4](methodology.md#implementation-in-the-original-code-4-market) | P0-04 |
| <a id="I-13"></a>I-13 | SellerPricing | A4 | Fidelity | ❌ | open | `SELLER` pricing returns the buyer's price (positional-argument bug) | [mechanism.py:L70-L85](../../../src_thesis/marketplace/market/mechanism.py#L70-L85)<br>[matching.py:L330-L332](../../../src_thesis/marketplace/market/matching.py#L330-L332) | T6 | [§4](methodology.md#implementation-in-the-original-code-4-market) | P0-05 |
| <a id="I-14"></a>I-14 | OrderMatcher | A5 | Fidelity | ⚠️ | open | P2P loss is topped up from the DSO. The buyer's `energy_bought` counts `q + loss` | [matching.py:L370](../../../src_thesis/marketplace/market/matching.py#L370)<br>[lem.py:L404-L423](../../../src_thesis/marketplace/lem.py#L404-L423) | C | [§4](methodology.md#implementation-in-the-original-code-4-market) | P1-01 |
| <a id="I-15"></a>I-15 | OrderMatcher | A5 | Paper | ❓ | open | Stage 1 clears DSO-preferred orders with the DSO before any P2P matching | [matching.py:L635-L663](../../../src_thesis/marketplace/market/matching.py#L635-L663) | — | [§4](methodology.md#implementation-in-the-original-code-4-market) | P1-13 |
| <a id="I-16"></a>I-16 | OrderMatcher | A5 | Paper | ❓ | open | The clearing price is a VWAP that includes DSO trades | [matching.py:L410](../../../src_thesis/marketplace/market/matching.py#L410) | — | [§4](methodology.md#implementation-in-the-original-code-4-market) | P1-07, P1-13 |
| <a id="I-17"></a>I-17 | BidAskSpreadPricing | A4 | Fidelity | ❌ | open | `BID_ASK_SPREAD` pricing receives `market_price` as `factor`, so it returns the buyer's price. The mechanism is also absent from §3.3.3 | [mechanism.py:L89-L113](../../../src_thesis/marketplace/market/mechanism.py#L89-L113)<br>[matching.py:L330-L332](../../../src_thesis/marketplace/market/matching.py#L330-L332) | T12 | [§4](methodology.md#implementation-in-the-original-code-4-market) | P0-05 |
| <a id="I-18"></a>I-18 | DERAgent | A8 | Fidelity | ❌ | open | Battery dispatch has the trade term's sign reversed: selling charges the battery | [der.py:L302-L314](../../../src_thesis/marl/agents/der.py#L302-L314) | T7 | [§3](methodology.md#implementation-in-the-original-code-3-loop) | P0-01 |
| <a id="I-19"></a>I-19 | Battery | A8 | Fidelity | ❌ | open | A charge is refused entirely if it would reach SoC_max; there is no partial fill | [battery.py:L96-L112](../../../src_thesis/marl/agents/battery.py#L96-L112)<br>[battery.py:L134-L159](../../../src_thesis/marl/agents/battery.py#L134-L159) | C | [§5](methodology.md#implementation-in-the-original-code-5-agents) | P0-06 |
| <a id="I-20"></a>I-20 | Battery | A8 | Fidelity | ❌ | open | Discharge efficiency is applied in the wrong direction (`·η` instead of `/η`) | [battery.py:L162-L180](../../../src_thesis/marl/agents/battery.py#L162-L180) | C | [§5](methodology.md#implementation-in-the-original-code-5-agents) | P0-06 |
| <a id="I-21"></a>I-21 | DERAgent | A8 | Code | ⚠️ | open | Demand satisfaction ignores battery discharge | [der.py:L258-L270](../../../src_thesis/marl/agents/der.py#L258-L270) | C | [§5](methodology.md#implementation-in-the-original-code-5-agents) | — |
| <a id="I-22"></a>I-22 | DERAgent | A8 | Paper | ❓ | open | No household energy-conservation identity is enforced | [lem.py:L402-L423](../../../src_thesis/marketplace/lem.py#L402-L423) | — | [§5](methodology.md#implementation-in-the-original-code-5-agents) | P1-01 |
| <a id="I-23"></a>I-23 | LocalEnergyMarket | A8 | Fidelity | ❌ | open | `B_grid` (eq. 20) is never computed. The "grid balance" observation is `dso.balance` | [lem.py:L489](../../../src_thesis/marketplace/lem.py#L489)<br>[observation.py:L287](../../../src_thesis/marketplace/observation.py#L287) | C | [§6](methodology.md#implementation-in-the-original-code-6-grid) | — |
| <a id="I-24"></a>I-24 | ObservationHandler, OrderMatcher | A6 | Fidelity | ❌ | open | `dso.balance` changes only on Stage-1 DSO-preferred trades and carries across steps, so it is ≡ 0 by default | [matching.py:L275-L283](../../../src_thesis/marketplace/market/matching.py#L275-L283)<br>[matching.py:L398](../../../src_thesis/marketplace/market/matching.py#L398) | T4 | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | — |
| <a id="I-25"></a>I-25 | OrderMatcher | A6 | Code | ❓ | open | The B_DSO sign convention is inconsistent between `match_orders` and `_match_preferred_partners` | [matching.py:L275-L283](../../../src_thesis/marketplace/market/matching.py#L275-L283)<br>[matching.py:L656-L663](../../../src_thesis/marketplace/market/matching.py#L656-L663) | C | [§4](methodology.md#implementation-in-the-original-code-4-market) | — |
| <a id="I-26"></a>I-26 | OrderMatcher, DERAgent | A8 | Fidelity | ⚠️ | open | `agent.balance = sold − bought`, not eq. 13 | [lem.py:L455](../../../src_thesis/marketplace/lem.py#L455)<br>[matching.py:L453-L472](../../../src_thesis/marketplace/market/matching.py#L453-L472) | C | [§3](methodology.md#implementation-in-the-original-code-3-loop) | P0-08 |
| <a id="I-27"></a>I-27 | ObservationHandler, DERAgent | A8 | Fidelity | ❌ | open | Agent profit (eq. 14) is never updated | [der.py:L63](../../../src_thesis/marl/agents/der.py#L63)<br>[der.py:L112](../../../src_thesis/marl/agents/der.py#L112)<br>[observation.py:L347](../../../src_thesis/marketplace/observation.py#L347) | T5 | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | P0-11 |
| <a id="I-28"></a>I-28 | Trade, DSOAgent | A6 | Fidelity | ❌ | open | Grid fees are computed but never charged to anyone | [dso.py:L350-L351](../../../src_thesis/marketplace/dso/dso.py#L350-L351)<br>[matching.py:L340-L353](../../../src_thesis/marketplace/market/matching.py#L340-L353) | C | [§4](methodology.md#implementation-in-the-original-code-4-market) | P0-11 |
| <a id="I-29"></a>I-29 | DSOAgent | A6 | Paper | ❓ | open | `F_trans` has no formula in the paper; the code uses 0 | [dso.py:L297](../../../src_thesis/marketplace/dso/dso.py#L297) | — | [§4](methodology.md#implementation-in-the-original-code-4-market) | P0-11 |
| <a id="I-30"></a>I-30 | DSOAgent | A6 | Fidelity | ⚠️ | open | `F_volt` and `F_thermal` caps (0.2, 0.3) differ from or are undefined in the paper | [dso.py:L332-L339](../../../src_thesis/marketplace/dso/dso.py#L332-L339) | C | [§4](methodology.md#implementation-in-the-original-code-4-market) | — |
| <a id="I-31"></a>I-31 | DSOAgent | A6 | Fidelity | ⚠️ | open | `F_imb` is effectively always 0 | [dso.py:L343-L346](../../../src_thesis/marketplace/dso/dso.py#L343-L346)<br>[dso.py:L403-L451](../../../src_thesis/marketplace/dso/dso.py#L403-L451) | C | [§4](methodology.md#implementation-in-the-original-code-4-market) | — |
| <a id="I-32"></a>I-32 | OrderMatcher, GridNetwork | A7 | Fidelity | ❌ | open | Only Stage-1 trades update edge flows | [matching.py:L603](../../../src_thesis/marketplace/market/matching.py#L603)<br>[matching.py:L286-L379](../../../src_thesis/marketplace/market/matching.py#L286-L379) | C | [§3](methodology.md#implementation-in-the-original-code-3-loop) | P1-02 |
| <a id="I-33"></a>I-33 | GridNetwork | A7 | Fidelity | ❌ | open | Edge flows start random and accumulate over the episode instead of being per period | [network.py:L87](../../../src_thesis/adapters/grid/network.py#L87)<br>[network.py:L330](../../../src_thesis/adapters/grid/network.py#L330) | T10 | [§6](methodology.md#implementation-in-the-original-code-6-grid) | P1-03 |
| <a id="I-34"></a>I-34 | GridNetwork | A7 | Code | ⚠️ | open | Loss factor κ = 0.03 is hard-coded | [network.py:L338-L355](../../../src_thesis/adapters/grid/network.py#L338-L355) | C | [§6](methodology.md#implementation-in-the-original-code-6-grid) | — |
| <a id="I-35"></a>I-35 | ImplicitCooperation | B1 | Fidelity | ❌ | open | "Supply-demand imbalance" is volume/C, not `\|Σbuy − Σsell\|/C`. The coordination score inherits this | [implicit_cooperation.py:L127-L128](../../../src_thesis/cooperation/implicit_cooperation.py#L127-L128)<br>[implicit_cooperation.py:L147-L148](../../../src_thesis/cooperation/implicit_cooperation.py#L147-L148) | C | [§7](methodology.md#implementation-in-the-original-code-7-kpis) | P1-07 |
| <a id="I-36"></a>I-36 | ImplicitCooperation | B1 | Paper | ❓ | open | Social welfare is turnover `Σ p·q`, not surplus | [implicit_cooperation.py:L95](../../../src_thesis/cooperation/implicit_cooperation.py#L95) | — | [§7](methodology.md#implementation-in-the-original-code-7-kpis) | P1-07 |
| <a id="I-37"></a>I-37 | ImplicitCooperation | B1 | Fidelity | ⚠️ | open | Price volatility is computed over the whole episode, not a window | [implicit_cooperation.py:L107-L108](../../../src_thesis/cooperation/implicit_cooperation.py#L107-L108) | C | [§7](methodology.md#implementation-in-the-original-code-7-kpis) | — |
| <a id="I-38"></a>I-38 | ReputationHandler | A9 | Code | ⚠️ | open | Reputation: reliability ≡ 1, the grid term is neutral, and decay is weighted by time of day | [reputation.py:L132](../../../src_thesis/marketplace/market/reputation.py#L132)<br>[reputation.py:L89](../../../src_thesis/marketplace/market/reputation.py#L89) | C | [§4](methodology.md#implementation-in-the-original-code-4-market) | P1-10 |
| <a id="I-39"></a>I-39 | LocalEnergyMarket, ObservationHandler | C1 | Fidelity | ❌ | open | Forecast error (`max_error`) is never applied, so the "remaining demand/supply" observations reveal the true future | [lem.py:L66-L67](../../../src_thesis/marketplace/lem.py#L66-L67)<br>[observation.py:L342-L345](../../../src_thesis/marketplace/observation.py#L342-L345) | C | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | P1-09 |
| <a id="I-40"></a>I-40 | ObservationHandler | C1 | Paper | ❓ | open | Observations are raw and unnormalised | [observation.py:L336-L358](../../../src_thesis/marketplace/observation.py#L336-L358) | — | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | — |
| <a id="I-41"></a>I-41 | RewardHandler | C2 | Fidelity | ❌ | open | `f_coop` is not in [0, 1] (≈ 1811) | [reward.py:L176-L198](../../../src_thesis/marketplace/reward.py#L176-L198) | T9 | [§8](methodology.md#implementation-in-the-original-code-8-reward) | P1-06 |
| <a id="I-42"></a>I-42 | RewardHandler | C2 | Paper | ❓ | open | The cooperation-boost form differs across [P1] eq. 4, the code and [P2] eq. 3 | [reward.py:L228-L231](../../../src_thesis/marketplace/reward.py#L228-L231) | — | [§8](methodology.md#implementation-in-the-original-code-8-reward) | — |
| <a id="I-43"></a>I-43 | RewardHandler | C2 | Code | ❌ | open | `r_res ≡ −1.5` and `r_trade ≡ 0` (caused by I-12) | [reward.py:L419-L425](../../../src_thesis/marketplace/reward.py#L419-L425)<br>[reward.py:L259-L260](../../../src_thesis/marketplace/reward.py#L259-L260) | T3 | [§8](methodology.md#implementation-in-the-original-code-8-reward) | P0-04 |
| <a id="I-44"></a>I-44 | RewardHandler | C2 | Fidelity | ❌ | open | `r_grid`, `γ_DSO` and the grid part of `f_contrib` are inactive (caused by I-24) | [reward.py:L209](../../../src_thesis/marketplace/reward.py#L209)<br>[reward.py:L265-L321](../../../src_thesis/marketplace/reward.py#L265-L321)<br>[reward.py:L487-L499](../../../src_thesis/marketplace/reward.py#L487-L499) | T4 | [§8](methodology.md#implementation-in-the-original-code-8-reward) | — |
| <a id="I-45"></a>I-45 | RewardHandler | C2 | Code | ⚠️ | open | `_w_local` is overwritten 0.7 → 0.3, so `r_trade = 0.3ρ_local + 0.3ρ_dso` (the paper prints 0.3/0.3) | [reward.py:L80](../../../src_thesis/marketplace/reward.py#L80)<br>[reward.py:L95](../../../src_thesis/marketplace/reward.py#L95) | C | [§8](methodology.md#implementation-in-the-original-code-8-reward) | P1-06 |
| <a id="I-46"></a>I-46 | RewardHandler | C2 | Fidelity | ⚠️ | open | The unmet-demand penalty uses `p_dso`, not the paper's `p_no_trades = 5` | [reward.py:L216-L223](../../../src_thesis/marketplace/reward.py#L216-L223)<br>[reward.py:L236](../../../src_thesis/marketplace/reward.py#L236) | C | [§8](methodology.md#implementation-in-the-original-code-8-reward) | — |
| <a id="I-47"></a>I-47 | RewardHandler | C2 | Paper | ❓ | open | The no-trade guard returns a fixed −4.46 before any other term | [reward.py:L138-L139](../../../src_thesis/marketplace/reward.py#L138-L139) | — | [§8](methodology.md#implementation-in-the-original-code-8-reward) | P1-06 |
| <a id="I-48"></a>I-48 | CTDEModule | D1 | Fidelity | ❌ | open | CTDE trains a centralized `pi` but acts with per-agent `pi_heads`, which are never trained | [ctde.py:L48-L57](../../../src_thesis/marl/ctde.py#L48-L57)<br>[ctde.py:L76-L89](../../../src_thesis/marl/ctde.py#L76-L89)<br>[ctde.py:L127-L128](../../../src_thesis/marl/ctde.py#L127-L128) | C | [§9](methodology.md#implementation-in-the-original-code-9-paradigms) | P0-09 |
| <a id="I-49"></a>I-49 | RLTrainer | D1 | Code | ⚠️ | open | The PBT lr domain [1e-4, 1e-2] excludes the initial 1e-5, and the entropy domain reaches 10 | [train.py:L182-L197](../../../src_thesis/marl/train.py#L182-L197)<br>[train.py:L219](../../../src_thesis/marl/train.py#L219) | C | [§11](methodology.md#implementation-in-the-original-code-11-experiments) | — |
| <a id="I-50"></a>I-50 | RLTrainer, CaseNotebooks | D1 | Paper | ❓ | open | The budget is counted in training iterations, but the paper says "10 000 episodes" | [train.py:L449](../../../src_thesis/marl/train.py#L449) | — | [§11](methodology.md#implementation-in-the-original-code-11-experiments) | — |
| <a id="I-51"></a>I-51 | ProfileHandler, CaseNotebooks | D3 | Paper | ❓ | open | The Case 6 profile-to-agent mapping is unpublished | [case6_implicit_cooperation.ipynb](../../../notebooks/case6_implicit_cooperation.ipynb) | — | [§11](methodology.md#implementation-in-the-original-code-11-experiments) | — |
| <a id="I-52"></a>I-52 | tests | A0 | Code | ❌ | open | No functioning test gate: tests without assertions, fixtures that fail, signatures that have drifted | [test_battery.py:L13-L62](../../../tests/test_battery.py#L13-L62)<br>[test_checkpoint.py](../../../tests/test_checkpoint.py) | — | — | P0-12 |
| <a id="I-53"></a>I-53 | GridNetwork, Location | A0 | Code | ⚠️ | open | Defensive checks hide bad state (dead capacity check, bare `except`, float-only validators, mutable defaults) | [network.py:L39](../../../src_thesis/adapters/grid/network.py#L39)<br>[network.py:L98-L99](../../../src_thesis/adapters/grid/network.py#L98-L99)<br>[base.py:L57](../../../src_thesis/marketplace/grid/base.py#L57) | — | [§6](methodology.md#implementation-in-the-original-code-6-grid) | P3-02 |
| <a id="I-54"></a>I-54 | DSOAgent | A5 | Code | ⚠️ | open | DSO fallback skips grid feasibility (zero distance, loss and fee), and `validate_grid_constraints` ignores direction | [dso.py:L192-L275](../../../src_thesis/marketplace/dso/dso.py#L192-L275)<br>[dso.py:L356-L401](../../../src_thesis/marketplace/dso/dso.py#L356-L401) | — | [§4](methodology.md#implementation-in-the-original-code-4-market) | P1-05 |
| <a id="I-55"></a>I-55 | OrderMatcher | A5 | Code | ❌ | open | The Stage-2 capacity check uses `max_quantity·N` and the current balance, not grid capacity or the projected trade | [matching.py:L174](../../../src_thesis/marketplace/market/matching.py#L174)<br>[matching.py:L317-L318](../../../src_thesis/marketplace/market/matching.py#L317-L318) | C | [§4](methodology.md#implementation-in-the-original-code-4-market) | P1-02 |
| <a id="I-56"></a>I-56 | DERAgent | A2 | Paper | ❓ | open | Units and timestep are inconsistent (W/kW/kWh/Wh, $/Wh vs $/kWh). There is no explicit Δt | [der.py:L36](../../../src_thesis/marl/agents/der.py#L36)<br>[matching.py:L35-L38](../../../src_thesis/marketplace/market/matching.py#L35-L38) | — | [§11](methodology.md#implementation-in-the-original-code-11-experiments) | P1-11 |
| <a id="I-57"></a>I-57 | GridConfig | A7 | Fidelity | ❌ | open | IEEE-34 graph is disconnected (edge 832–888 missing), and the impedance table is unused | [config.py:L30-L40](../../../src_thesis/marketplace/grid/config.py#L30-L40)<br>[config.py:L45-L77](../../../src_thesis/marketplace/grid/config.py#L45-L77)<br>[network.py:L137](../../../src_thesis/adapters/grid/network.py#L137) | T13 | [§6](methodology.md#implementation-in-the-original-code-6-grid) | P1-04 |
| <a id="I-58"></a>I-58 | ObservationHandler | C1 | Code | ⚠️ | open | The reset observation hard-codes G, D, remaining energy and KPIs to 0 | [observation.py:L196-L258](../../../src_thesis/marketplace/observation.py#L196-L258) | — | [§2](methodology.md#implementation-in-the-original-code-2-formulation) | P1-09 |
| <a id="I-59"></a>I-59 | GroupedLEM | D1 | Code | ❌ | open | Grouped obs/action tuples may be assigned to the wrong agents: insertion order vs sorted keys | [train.py:L657](../../../src_thesis/marl/train.py#L657)<br>[train.py:L693](../../../src_thesis/marl/train.py#L693)<br>[train.py:L717](../../../src_thesis/marl/train.py#L717) | — | [§9](methodology.md#implementation-in-the-original-code-9-paradigms) | P0-10 |
| <a id="I-60"></a>I-60 | GroupedLEM | D1 | Paper | ❓ | open | CTCE is a centralized-information baseline, not a true upper bound. The group reward sum scales with N | [train.py:L698](../../../src_thesis/marl/train.py#L698) | — | [§9](methodology.md#implementation-in-the-original-code-9-paradigms) | P1-12 |
| <a id="I-61"></a>I-61 | RLInference | D2 | Code | ❌ | open | Standalone inference samples and clips actions itself instead of using RLlib's action path, and reads `info` wrongly | [inference.py:L147-L217](../../../src_thesis/marl/inference.py#L147-L217)<br>[inference.py:L237](../../../src_thesis/marl/inference.py#L237) | — | — | P2-02 |
| <a id="I-62"></a>I-62 | RLTrainer | D1 | Code | ⚠️ | open | Training config defects: positive `evaluation_duration` rejected, CPUs double-allocated, PBT always on, no `finally` around `ray.shutdown` | [train.py:L117](../../../src_thesis/marl/train.py#L117)<br>[train.py:L290-L299](../../../src_thesis/marl/train.py#L290-L299)<br>[train.py:L439](../../../src_thesis/marl/train.py#L439)<br>[train.py:L459-L468](../../../src_thesis/marl/train.py#L459-L468) | — | — | P2-05 |
| <a id="I-63"></a>I-63 | EnvConfigHandler | D3 | Code | ⚠️ | open | The saved env config cannot reconstruct the scenario (seeds, profile sources, rounding) | [io.py:L113](../../../src_thesis/marketplace/io.py#L113)<br>[io.py:L148-L149](../../../src_thesis/marketplace/io.py#L148-L149)<br>[io.py:L56](../../../src_thesis/marketplace/io.py#L56) | — | — | P2-04 |
| <a id="I-64"></a>I-64 | RLTrainer | D3 | Code | ⚠️ | open | No run manifests, non-learning baselines or multi-seed statistics | [train.py:L447](../../../src_thesis/marl/train.py#L447)<br>[train.py:L397](../../../src_thesis/marl/train.py#L397) | — | — | P2-06 |
| <a id="I-65"></a>I-65 | MetricsHandlers | B2 | Code | ❌ | open | `src/analytics` reports welfare, grid and coordination concepts without the required inputs | [market_analytics.py:L124-L137](../../../src_thesis/cooperation/metrics/market_analytics.py#L124-L137) | — | [§11](methodology.md#implementation-in-the-original-code-11-experiments) | P1-08 |
| <a id="I-66"></a>I-66 | TransactionBlock, Validator | A10 | Code | ⚠️ | open | The block hash omits loss and fees, and blocks are forced every step (in-memory PoW, not consensus) | [validation.py:L26-L35](../../../src_thesis/marketplace/market/validation.py#L26-L35)<br>[matching.py:L422](../../../src_thesis/marketplace/market/matching.py#L422) | — | [§4](methodology.md#implementation-in-the-original-code-4-market) | P3-01 |
| <a id="I-67"></a>I-67 | Docs | D3 | Code | ⚠️ | open | README, notebooks and docs describe a different repository state | [README.md](../../../README.md)<br>tests.md (removed from this repo; see upstream `marlem-main`) | — | — | P3-03 |
| <a id="I-68"></a>I-68 | ImplicitCooperation | B1 | Paper | ❓ | open | Imbalance (eq. 24) over trades is ≡ 0 by construction. Needs a definition over orders or physical net positions, and a timing (before or after DSO clearing) for `B_grid` | [implicit_cooperation.py:L127-L128](../../../src_thesis/cooperation/implicit_cooperation.py#L127-L128) | — | [§7](methodology.md#implementation-in-the-original-code-7-kpis) | — |
| <a id="I-69"></a>I-69 | ImplicitCooperation | B1 | Paper | ⚠️ | open | "DER self-consumption" is defined as P2P share; the label does not match the quantity | [implicit_cooperation.py:L195](../../../src_thesis/cooperation/implicit_cooperation.py#L195) | — | [§7](methodology.md#implementation-in-the-original-code-7-kpis) | P1-07 |
| <a id="I-70"></a>I-70 | GridNetwork | A7 | Paper | ❓ | open | Grid physics scope: linear unbounded losses, `V_drop = f·d`, transport flows. "High-fidelity" is an overclaim | [network.py:L338-L355](../../../src_thesis/adapters/grid/network.py#L338-L355)<br>[dso.py:L332-L334](../../../src_thesis/marketplace/dso/dso.py#L332-L334) | — | [§6](methodology.md#implementation-in-the-original-code-6-grid) | P1-04 |
| <a id="I-71"></a>I-71 | Battery | A8 | Paper | ❓ | open | Battery model has no charge/discharge power limit (claimed in the text), and eq. 15 ignores efficiency | [battery.py:L134-L180](../../../src_thesis/marl/agents/battery.py#L134-L180)<br>[battery.py:L210-L219](../../../src_thesis/marl/agents/battery.py#L210-L219) | — | [§5](methodology.md#implementation-in-the-original-code-5-agents) | P0-06 |
| <a id="I-72"></a>I-72 | RLTrainer | D3 | Paper | ❓ | open | [P2] protocol: one fixed seed, evaluation on the training scenario, ranking by shaped reward | [train.py:L279-L299](../../../src_thesis/marl/train.py#L279-L299)<br>[lem.py:L276-L278](../../../src_thesis/marketplace/lem.py#L276-L278) | — | [§11](methodology.md#implementation-in-the-original-code-11-experiments) | P2-01 |
| <a id="I-73"></a>I-73 | GroupedLEM | D1 | Paper | ❓ | open | Cross-paradigm return comparability: group sum vs per-agent returns | [train.py:L698](../../../src_thesis/marl/train.py#L698) | — | [§9](methodology.md#implementation-in-the-original-code-9-paradigms) | P1-12 |
| <a id="I-74"></a>I-74 | DSOAgent | A6 | Paper | ⚠️ | open | Thermal-fee threshold (20 %) sits below the congestion threshold (80 %) | [dso.py:L66-L68](../../../src_thesis/marketplace/dso/dso.py#L66-L68) | — | [§4](methodology.md#implementation-in-the-original-code-4-market) | — |
| <a id="I-75"></a>I-75 | RewardHandler, ImplicitCooperation | C2 | Paper | ❓ | open | `f_coop` has no normalisation ranges for its unbounded KPIs, so the [0, 1] claim is unsupported | [reward.py:L176-L198](../../../src_thesis/marketplace/reward.py#L176-L198)<br>[implicit_cooperation.py:L95](../../../src_thesis/cooperation/implicit_cooperation.py#L95) | — | [§8](methodology.md#implementation-in-the-original-code-8-reward) | P1-06 |
| <a id="I-76"></a>I-76 | RewardHandler | C2 | Paper | ❓ | open | `R_base` components have no formulas in the paper; the code is the only specification | [reward.py:L152-L170](../../../src_thesis/marketplace/reward.py#L152-L170) | — | [§8](methodology.md#implementation-in-the-original-code-8-reward) | — |
| <a id="I-77"></a>I-77 | DERAgent | A3 | Fidelity | ⚠️ | open | Rule-based partner selection is a lexicographic sort plus a random top-half pick, not a weighted score | [der.py:L140-L163](../../../src_thesis/marl/agents/der.py#L140-L163)<br>[lem.py:L372-L375](../../../src_thesis/marketplace/lem.py#L372-L375) | C | [§3](methodology.md#implementation-in-the-original-code-3-loop) | — |
| <a id="I-78"></a>I-78 | LocalEnergyMarket | A1 | Fidelity | ⚠️ | open | Invalid actions raise `ValueError` instead of being dropped (Alg. 1 `ValidateOrder`) | [lem.py:L349-L350](../../../src_thesis/marketplace/lem.py#L349-L350) | C | [§3](methodology.md#implementation-in-the-original-code-3-loop) | — |
| <a id="I-79"></a>I-79 | RewardHandler | C2 | Fidelity | ⚠️ | open | `f_contrib` grid term is a heuristic, not [P2]'s marginal `−∂\|B_grid\|/∂a_i` | [reward.py:L487-L499](../../../src_thesis/marketplace/reward.py#L487-L499) | C | [§8](methodology.md#implementation-in-the-original-code-8-reward) | — |
| <a id="I-80"></a>I-80 | CaseNotebooks | D3 | Paper | ❓ | open | [P2] evaluation metric `B_index` is undefined in the paper and absent from the code | — | C | [§11](methodology.md#implementation-in-the-original-code-11-experiments) | — |

## 3. Paper origin: is the paper's method sound?

This asks whether the paper's method holds up on its own terms, before any code is involved. None of these items prevents building a working model. Each one needs a **recorded decision** (paper text → options → chosen rule → reason), because the paper cannot settle it. The register rows carry the decisions.

| Topic | Concern | Why it matters for the thesis | Register |
|---|---|---|---|
| Reward form (eq. 4) | [P1] eq. 4 as printed is ≡ `R_base` for normalised `f_coop·f_contrib ≤ 1`. [P2] eq. 3 has a different form, and the code a third. | The paper's central contribution, the cooperation bonus, has no single definition | [I-42](#I-42) |
| Reward components | `R_base` terms are given only as names, weights and ranges | The code is the de-facto specification, and it is partly broken (I-43, I-44) | [I-76](#I-76) |
| `f_coop` normalisation | Claimed to lie in [0, 1], but welfare, liquidity, spread and volatility have no stated normalisation ranges | The weights (Σ = 56) are meaningless across unnormalised scales | [I-75](#I-75), [I-41](#I-41) |
| Social welfare (eq. 21) | Defined as consumer + producer surplus, but written as `Σ p·q`, which is turnover. Transfers between agents cancel in true welfare. | This is the highest-weighted KPI in `f_coop` (7/56) | [I-36](#I-36) |
| Imbalance (eq. 24) | `\|Σq_buy − Σq_sell\|` computed over *trades* is ≡ 0, since every trade has one buyer and one seller. It only means something over *orders* or physical net positions. `B_grid` (eq. 20) after full DSO clearing is ≈ 0 by construction. | Coordination score (eq. 27), the headline metric in [P2], depends on it | [I-68](#I-68), [I-35](#I-35) |
| KPI labels | "DER self-consumption" is defined as P2P share | Wording in thesis results | [I-69](#I-69) |
| Grid physics | Losses are linear in `d·q` (not `I²R`) and unbounded when `d·κ > 1`. Voltage drop is `f·d`. Flows are transport on a graph, not power flow. The paper nevertheless calls this "high-fidelity". | Scope of any physical claim; motivates SimBench | [I-70](#I-70) |
| Fee design | `F_trans` has no formula. Thermal fees start at 20 % loading, below the 80 % congestion threshold. | Fees shape P2P incentives only if they are charged at all (I-28) | [I-29](#I-29), [I-74](#I-74) |
| Battery | eq. 16 has no charge/discharge power limit, although the text claims one. eq. 15 ignores efficiency. | Storage arbitrage results | [I-71](#I-71) |
| Market design | Stage-1 DSO-preferred sub-stage; clearing price mixes P2P and DSO tariffs | The "clearing price" signal in observations and rewards | [I-15](#I-15), [I-16](#I-16) |
| Action semantics | No explicit "submit nothing" action. α and β are discrete but modelled as continuous. | Whether inactivity can be learned or exploited; exploration | [I-11](#I-11), [I-47](#I-47) |
| Information | "Forecasts" are specified (30 % error) but the observation also exposes exact remaining future demand | Partial observability and privacy claims | [I-39](#I-39) |
| Units | P1 uses $/MWh (35–280). P2 plots up to 600 "$/kWh". Quantities are kWh per 1-h step with Δt implicit. | Every economic number | [I-56](#I-56) |
| Paradigm comparison | CTCE is called a "theoretical upper bound" but uses the same approximate learner. The group reward is a sum over agents, so returns scale with N. | Validity of the 3×3 ranking in [P2] Table 9 | [I-60](#I-60), [I-73](#I-73) |
| Evaluation protocol | One fixed seed (42), evaluation on the training scenario, ranking by shaped reward | No variance or generalisation evidence for [P2]'s claims | [I-72](#I-72), [I-50](#I-50) |
| Data | The Case 6 profile-to-agent mapping and scaling are not published | Exact reproduction is impossible without the authors | [I-51](#I-51) |

**Verdict on the paper's method:** the overall design is coherent and worth building on: a market with a physical-grid layer, KPI-shaped observations and rewards, and three training paradigms compared. The weak points are **definitions**, not architecture: reward and KPI formulas, grid-physics scope, and the evaluation protocol. They can all be fixed by recorded decisions. None of them requires abandoning the framework.

## 4. Impact on the published results

The upstream repository is the published version. If the papers' figures were produced with this code (not independently confirmable), then:

- **[P1] §5, Case 5 (battery, zero-intelligence agents):** the case uses `BID_ASK_SPREAD` pricing, which returns the buyer's bid (I-17). The P2P price distributions in Fig. 5 are therefore buyer bids. Battery dispatch has the reversed trade sign (I-18) and the wrong efficiency direction (I-19, I-20). The "imbalance" and "coordination score" in Figs. 6–7 measure traded volume, not imbalance (I-35, I-68). The paper's conclusion that batteries stabilise prices is **not supported** by this code.
- **[P2] Case 6 (MARL 3×3):** the reward the agents optimised has constant or inactive components (I-43, I-44), an unnormalised `f_coop` (I-41), and no terminal penalty (I-02). Observations expose exact future demand (I-39) and a constant zero profit (I-27). The CTDE actor that acted was never trained (I-48). The ranking in Table 9 describes learning on *this* reward, not on the paper's intended model.

**Thesis consequence:** the thesis cannot claim to reproduce either paper. The defensible framing is a **paper-faithful corrected reimplementation**: every paper decision and fidelity deviation is listed, and the original is kept as a named comparison.

## 5. Completeness check and readiness

**Coverage of the paper (fidelity).** Every numbered element was compared:

| Source | Items | Where in [methodology.md](methodology.md) |
|---|---|---|
| [P1] | §3.9 loop, Algorithm 1 | §3, §4.1 |
| [P1] | eq. 2, 15 | §2.1, §5.2 |
| [P1] | eq. 9–11 | §4.3 |
| [P1] | eq. 7, 8a–8h | §4.4 |
| [P1] | eq. 13, 14, 16 | §5.1, §5.3 |
| [P1] | eq. 18–20, zones, topologies | §6 |
| [P1] | eq. 12 | §4.5 |
| [P1] | eq. 21–27 | §7 |
| [P1] | Table 2 | §2.2 |
| [P1] | eq. 3–6 | §8 |
| [P1] | eq. 17, profiles | §5.4 |
| [P1] | §4 Case 5, zero-intelligence baseline | §11.1, and §4 here |
| [P2] | eq. 1–3 | §6, §8 |
| [P2] | KPI eq. 7–10 (same as [P1]) | §7 |
| [P2] | eq. 16–20 (paradigms), algorithms eq. 11–15 | §9, §10 |
| [P2] | Tables 6–8, §4.2–4.3 | §11.2 |

[P1] eq. 1 (state factorisation) is descriptive only and has nothing to test.

**Evidence strength.**
- Rows marked **T*n*** were reproduced by the evidence script.
- Rows marked **C** rest on code reading.
- Paper-origin rows are judgments that need your decision.

**Known limits of this pass:**
- `cooperation/metrics/*` and `cooperation/visualization/*` were not audited line by line; I-65 is taken from the validation plan.
- Notebooks were only checked for the Case 5 setup.
- [P1] eq. 11 (proportional surplus) is garbled in the text extraction. Check it against the rendered PDF before step A4.

**Readiness verdict: ready to move forward**, with this document frozen as the description of the original. Conditions:

1. **Paper-origin decisions are taken per step, just before that step, not all up front.** Each step in [plan.md](plan.md) lists the decisions it needs.
2. **Every decision is recorded** in the [plan's decision log](plan.md#7-decision-log) and its register status set to `decided`, before code changes. A changed decision is a new version, not an edit.
3. **The thesis claim is "paper-faithful corrected reimplementation"** (§4), not reproduction.
4. **A new finding reopens a closed row only** if it shows a violated invariant, a paper contradiction not already listed, or a failed reproduction. A preference alone does not.

## 6. Old fix-plan IDs

Reverse lookup from the archived plan's IDs (P0-01 … P3-03) to the issues here (generated). The old IDs are aliases only; use `I-xx` everywhere.

<!-- BEGIN generated:old-ids -->
| Old ID | Issues |
|---|---|
| P0-01 | [I-18](issues.md#I-18) |
| P0-02 | [I-08](issues.md#I-08), [I-11](issues.md#I-11) |
| P0-03 | [I-09](issues.md#I-09), [I-10](issues.md#I-10) |
| P0-04 | [I-12](issues.md#I-12), [I-43](issues.md#I-43) |
| P0-05 | [I-13](issues.md#I-13), [I-17](issues.md#I-17) |
| P0-06 | [I-19](issues.md#I-19), [I-20](issues.md#I-20), [I-71](issues.md#I-71) |
| P0-07 | [I-01](issues.md#I-01), [I-02](issues.md#I-02) |
| P0-08 | [I-05](issues.md#I-05), [I-07](issues.md#I-07), [I-26](issues.md#I-26) |
| P0-09 | [I-48](issues.md#I-48) |
| P0-10 | [I-59](issues.md#I-59) |
| P0-11 | [I-27](issues.md#I-27), [I-28](issues.md#I-28), [I-29](issues.md#I-29) |
| P0-12 | [I-52](issues.md#I-52) |
| P1-01 | [I-14](issues.md#I-14), [I-22](issues.md#I-22) |
| P1-02 | [I-32](issues.md#I-32), [I-55](issues.md#I-55) |
| P1-03 | [I-33](issues.md#I-33) |
| P1-04 | [I-57](issues.md#I-57), [I-70](issues.md#I-70) |
| P1-05 | [I-54](issues.md#I-54) |
| P1-06 | [I-41](issues.md#I-41), [I-45](issues.md#I-45), [I-47](issues.md#I-47), [I-75](issues.md#I-75) |
| P1-07 | [I-16](issues.md#I-16), [I-35](issues.md#I-35), [I-36](issues.md#I-36), [I-69](issues.md#I-69) |
| P1-08 | [I-65](issues.md#I-65) |
| P1-09 | [I-39](issues.md#I-39), [I-58](issues.md#I-58) |
| P1-10 | [I-38](issues.md#I-38) |
| P1-11 | [I-56](issues.md#I-56) |
| P1-12 | [I-60](issues.md#I-60), [I-73](issues.md#I-73) |
| P1-13 | [I-15](issues.md#I-15), [I-16](issues.md#I-16) |
| P2-01 | [I-03](issues.md#I-03), [I-72](issues.md#I-72) |
| P2-02 | [I-61](issues.md#I-61) |
| P2-03 | [I-06](issues.md#I-06) |
| P2-04 | [I-63](issues.md#I-63) |
| P2-05 | [I-62](issues.md#I-62) |
| P2-06 | [I-64](issues.md#I-64) |
| P3-01 | [I-66](issues.md#I-66) |
| P3-02 | [I-53](issues.md#I-53) |
| P3-03 | [I-67](issues.md#I-67) |
<!-- END generated:old-ids -->
