# MARLEM: paper vs. original code

> Status: frozen description of the **original** MARLEM for step-by-step validation. It records facts and open decisions; it proposes no fixes.
> Written: 2026-09-23 · Final completeness pass: 2026-09-23 · Branch: `dev`
> This document is the **contract and evidence**: what the paper says, what the code does, and every issue with its ID (§6). The work order and live **status** are in [marlem-validation-by-level.md](plan-by-level.md). [validation-plan-fix.md](validation-plan-fix.md) is kept as detailed evidence and fix rationale, looked up via the register's **VP** column.

## 0. How to read this

**Sources**

- **[P1]**: Salazar-Peña et al., *MARLEM*, Applied Energy 412 (2026) 127546 ([pdf](../../paper/marlem.pdf)). It defines the environment: loop, market, grid, agents, KPIs and reward.
- **[P2]**: *Harnessing Implicit Cooperation*, SSRN preprint ([pdf](../../paper/marlem-results.pdf)). It covers the MARL modes, the Case 6 setup, and Tables 6–8.
- **Code**: the original upstream implementation. `marlem-dev/src/` is byte-identical to `marlem-main/src/`. `src_thesis/` is the same code, relocated; only imports and formatting differ. Paths below use the `src_thesis/` layout.

**Three origins.** Every issue is tagged with where it originates. (These are *not* the paper's Levels 0–2; those are used for the validation plan.) They are checked in this order, because a lower origin is meaningless until the one above it is settled:

| Origin | Question | If it fails |
|---|---|---|
| **Paper** (paper method) | Is what the paper describes sound, complete and unambiguous? | Record a decision (§3). The paper is not the oracle for this item. |
| **Fidelity** | Does the code implement what the paper describes? | Either implement the paper, or record a justified deviation. |
| **Code** (code correctness) | Where the paper is silent, is the code internally correct (conservation, interfaces, no silent failure)? | Fix it with a test. |

**Status legend**

| Mark | Meaning |
|---|---|
| ✅ | Code matches the paper |
| ⚠️ | Code runs but differs from the paper (a choice or a simplification) |
| ❌ | Code contradicts the paper or its own documented intent. This is a defect. |
| ❓ | The paper is silent or ambiguous, so it cannot serve as the oracle. A decision must be recorded. |

**Evidence**

- **T*n*** means confirmed by running [evidence/trace_original_episode.py](evidence/trace_original_episode.py). It uses 3 agents, a mesh grid, seeded random actions and the original code. Run it with the `marlem` conda env.
- **C** means confirmed by reading the code only.

Trace output referenced below:

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

---

## 1. The loop: one trading period

The paper order is [P1] §3.9 phases 1–8 and Algorithm 1. The code is [lem.py `step`](../../../src_thesis/marketplace/lem.py#L314).

| # | Paper phase | Code (in `LocalEnergyMarket.step`) | Match |
|---|---|---|---|
| 1 | Clip `a_i` to market bounds, then clip `q` to physical feasibility (eq. 15) | `DERAgent.adjust_action_for_battery` → `ActionHandler.is_valid_action` → clip again → `is_buy = a[2] > 0.5` → [der.py:L161-L234](../../../src_thesis/marl/agents/der.py#L161-L234)<br>[lem.py:L336-L359](../../../src_thesis/marketplace/lem.py#L336-L359) | ⚠️ See §2.1 |
| 2 | Action → `Order`. Rule-based partner if the RL partner is disabled | `Order(...)`. Default `enable_partner_preference=False` → `select_preferred_partner(randomize=True)` → [lem.py:L361-L381](../../../src_thesis/marketplace/lem.py#L361-L381) | ✅ |
| 3 | Clearing: Stage 1 preference → Stage 2 double auction → Stage 3 DSO | `OrderMatcher.match_orders` (also mines the block, sets `dso.balance` and `dso.congestion_level`) → [matching.py:L238-L424](../../../src_thesis/marketplace/market/matching.py#L238-L424) | ⚠️ See §2.2 |
| 4 | Update agent energy, battery and grid state from trades | `update_energy_tracking` + `update_battery_from_trades`. Grid flows are updated inside matching, Stage 1 only → [lem.py:L391-L411](../../../src_thesis/marketplace/lem.py#L391-L411)<br>[matching.py:L589](../../../src_thesis/marketplace/market/matching.py#L589) | ❌ See §2.5, §2.6 |
| 5 | Compute KPIs → reward per agent | `implicit_cooperation.get_kpis` → `reward_handler.calculate_reward` → [lem.py:L413-L431](../../../src_thesis/marketplace/lem.py#L413-L431) | ❌ See §2.8, §2.10 |
| 6 | Clock `t+1`. Update balances and reputation | `current_step += 1`; `agent.balance = market.get_agent_position`; `update_reputation` → [lem.py:L433-L441](../../../src_thesis/marketplace/lem.py#L433-L441) | ⚠️ Profit is never updated (§2.5) |
| 7 | Build `o_{i,t+1}` (private + public + KPIs) | `observation_handler.update_observation_space` (recomputes KPIs) → [lem.py:L478-L483](../../../src_thesis/marketplace/lem.py#L478-L483) | ⚠️ See §2.9 |
| 8 | Terminate at `t = τ` | `terminated` when `current_step >= max_steps - 1`, checked *after* the increment → [lem.py:L443-L453](../../../src_thesis/marketplace/lem.py#L443-L453) | ❌ T1, T2 |

**Reset** ([`reset`](../../../src_thesis/marketplace/lem.py#L258)) does the following:

- Reseeds global `np.random`.
- Draws a **random reputation** in U(0, 1) and **regenerates** every agent's profiles (T11).
- Draws a random `agent.balance` in U(−cap, cap).
- Resets the market, DSO, grid flows and battery. Battery SoC starts random in [SoC_min, SoC_max].
- Optionally regenerates the DSO prices.

---

## 2. Component contract

### 2.1 Action and feasibility ([P1] eq. 2, 15; §3.2.3)

Paper: `a_i = ⟨p_bid, q_bid, α, β⟩`, with α ∈ {0 = sell, 1 = buy} and β ∈ {0…|I|+1} (the peers, then the DSO, then "no preference").

```
q_sell,max = max(0, G_t − D_t) + E_dischargeable,   E_dischargeable = (SoC_t − SoC_min)·C_nom
q_buy,max  = max(0, D_t − G_t) + E_chargeable,      E_chargeable    = (SoC_max − SoC_t)·C_nom
```

| Item | Code | Status |
|---|---|---|
| Space | `Box([p_min, q_min, 0, 0], [p_max, min(q_max, capacity), 1, N+1])`. α and β are continuous. ([action.py](../../../src_thesis/marketplace/action.py#L35)) → [action.py:L35-L44](../../../src_thesis/marketplace/action.py#L35-L44) | ⚠️ β = N+1 ("no preference") is reachable only at the exact upper bound after `int()` |
| Feasibility | `adjust_action_for_battery` treats the *requested* `q` as the need. Buy: `q − G`, then charge/discharge offsets. Sell: `q − D`, then offsets. It does **not** compute eq. 15. ([der.py](../../../src_thesis/marl/agents/der.py#L161)) → [der.py:L161-L234](../../../src_thesis/marl/agents/der.py#L161-L234) | ❌ C |
| α interpretation | `adjust` uses `if is_buy:` (any value > 0 counts as buy). The environment uses `is_buy > 0.5`. → [der.py:L196](../../../src_thesis/marl/agents/der.py#L196)<br>[lem.py:L358](../../../src_thesis/marketplace/lem.py#L358) | ❌ T8 |
| `q_min` | After clipping, quantity is ≥ `q_min`. With `q_min > 0`, an agent can never submit "no order". → [der.py:L231-L232](../../../src_thesis/marl/agents/der.py#L231-L232) | ❓ The paper has no no-trade action |

### 2.2 Matching ([P1] Algorithm 1, §3.3.2)

| Stage | Paper | Code ([matching.py `match_orders`](../../../src_thesis/marketplace/market/matching.py#L238)) | Status |
|---|---|---|---|
| 1 | Match mutually preferred pairs | Orders with β = DSO are cleared **by the DSO first**. Mutual DER pairs are ranked by `1 − (p_b − p_s)/(p_max − p_min)` and must pass `dso.validate_grid_constraints`. → [matching.py:L593-L736](../../../src_thesis/marketplace/market/matching.py#L593-L736) | ❓ The DSO-first sub-stage is not in the paper |
| 2 | Double auction: buys by price ↓, sells by price ↑, reputation breaks ties, trade while `p_b ≥ p_s` | As described, with sort key `(price, −reputation, timestamp)`. The capacity check `abs(grid_balance) > grid_capacity` never binds because the balance is 0 (T4). → [matching.py:L282-L370](../../../src_thesis/marketplace/market/matching.py#L282-L370) | ✅ / ⚠️ |
| 3 | DSO buys all residual supply at `p_fit` and sells all residual demand at `p_util` | `dso.clear_unmatched_orders`. It sets every residual `order.quantity = 0`. → [dso.py:L190-L272](../../../src_thesis/marketplace/dso/dso.py#L190-L272) | ✅ |
| Loss handling | Loss `l_ij` derates `q_ij` | Buyer's residual `-= (q − loss)`, so the loss is bought again from the DSO in Stage 3. `energy_bought` counts `q + loss`. → [matching.py:L361-L362](../../../src_thesis/marketplace/market/matching.py#L361-L362) | ⚠️ C |
| Order mutation | Not specified | Orders are mutated in place, so reward, KPIs and the info dict see **residual** quantities, not submitted ones. → [matching.py:L361-L362](../../../src_thesis/marketplace/market/matching.py#L361-L362)<br>[dso.py:L212-L253](../../../src_thesis/marketplace/dso/dso.py#L212-L253) | ❌ T3 |
| Clearing price | "last clearing price" | VWAP over **all** trades, DSO trades included → [matching.py:L399](../../../src_thesis/marketplace/market/matching.py#L399) | ❓ |
| Unmatched orders | — | `unmatched_orders = []` always, because the DSO clears everything → [matching.py:L394-L396](../../../src_thesis/marketplace/market/matching.py#L394-L396) | ✅ (it feeds reputation reliability, which is therefore ≡ 1) |
| Invalid orders (Alg. 1 `ValidateOrder`) | Invalid orders are dropped from the order set | `step` raises `ValueError` on an invalid action → [lem.py:L342-L343](../../../src_thesis/marketplace/lem.py#L342-L343) | ⚠️ C |
| Rule-based partner (§3.4.1) | "Weighted score of high reputation and short grid distance" | Lexicographic sort by (−reputation, distance), then a **random** pick from the top half → [der.py:L136-L159](../../../src_thesis/marl/agents/der.py#L136-L159) | ⚠️ C |
| Asynchronous orders ([P2] Table 7) | "Realistic market latency" | Random timestamp jitter within the period, used only as the last sort key → [lem.py:L368-L371](../../../src_thesis/marketplace/lem.py#L368-L371) | ✅ C |
| Block validation | SHA-256 + PoW per period | One block per step, `blockchain_difficulty ≥ 1` enforced → [matching.py:L404-L410](../../../src_thesis/marketplace/market/matching.py#L404-L410)<br>[validation.py:L91-L113](../../../src_thesis/marketplace/market/validation.py#L91-L113) | ✅ PoW is the dominant `env.step` cost |

### 2.3 Pricing ([P1] eq. 9–11)

| Mechanism | Paper | Code ([mechanism.py](../../../src_thesis/marketplace/market/mechanism.py)) | Status |
|---|---|---|---|
| Average | `(p_b + p_s)/2` | Same → [mechanism.py:L31-L48](../../../src_thesis/marketplace/market/mechanism.py#L31-L48) | ✅ |
| Pay-as-bid, seller | `p_s` | `SellerPricing.calculate_price(sell_order, …)` receives the **buy** order positionally, so it returns `p_b` → [mechanism.py:L69-L84](../../../src_thesis/marketplace/market/mechanism.py#L69-L84) | ❌ T6 |
| Pay-as-offer, buyer | `p_b` | Same → [mechanism.py:L51-L66](../../../src_thesis/marketplace/market/mechanism.py#L51-L66) | ✅ |
| Nash | `p_s + (p_b − p_s)/2` (= average) | Same → [mechanism.py:L114-L148](../../../src_thesis/marketplace/market/mechanism.py#L114-L148) | ✅ |
| Proportional surplus | eq. 11, using `p_ref` | `p_s + d_b/(d_b + d_s)·(p_b − p_s)`, with `d_b = max(0, p_b − p_ref)` and `d_s = max(0, p_ref − p_s)` → [mechanism.py:L151-L190](../../../src_thesis/marketplace/market/mechanism.py#L151-L190) | ✅ Assuming eq. 11 reads this way; the PDF extraction is garbled |
| Bid-ask spread | Not in §3.3.3. Used in the §4 case study | Intended to be `p_s + factor·(p_b − p_s)`. The matcher passes `market_price` as the third positional argument, so it becomes `factor`, is clipped to [0, 1], and with prices > 1 the result is `p_b`. → [mechanism.py:L87-L111](../../../src_thesis/marketplace/market/mechanism.py#L87-L111) | ❌ T12 |

### 2.4 DSO balance and fees ([P1] eq. 7, 8a–8h)

```
B_DSO   = Σ_trades (E_sold − E_bought)
F_total = F_cong + F_trans + F_imb + F_volt + F_thermal + F_zone
F_cong  = f_cong·(C_t − C_thr)·q·p            F_imb   = f_imb·|B_impact|·q·p
F_volt  = min(V_drop, V_thr)·q·p, V_drop = f_volt·d_ij
F_therm = min(f_thermal, f_thr)·q·p, f_thermal = (C_t − T_thr)/(1 − T_thr)
F_zone  = −f_zone·q·p   (same zone)
```

| Item | Code ([dso.py](../../../src_thesis/marketplace/dso/dso.py)) | Status |
|---|---|---|
| `B_DSO` | `match_orders` receives the *previous* `dso.balance`. It changes it only for **Stage-1 DSO-preferred** trades and never for Stage 3, then carries it across steps. With rule-based partners it stays 0. → [matching.py:L272-L280](../../../src_thesis/marketplace/market/matching.py#L272-L280)<br>[matching.py:L388](../../../src_thesis/marketplace/market/matching.py#L388) | ❌ T4 |
| Sign convention | `match_orders` does `−q` when the DSO buys and `+q` when it sells. `_match_preferred_partners` applies the opposite sign to the same trades, but only to a local copy that is never returned. → [matching.py:L272-L280](../../../src_thesis/marketplace/market/matching.py#L272-L280)<br>[matching.py:L640-L647](../../../src_thesis/marketplace/market/matching.py#L640-L647) | ❓ Needs a hand check |
| `F_trans` | Always 0. The paper names the term but gives **no formula**. → [dso.py:L293](../../../src_thesis/marketplace/dso/dso.py#L293) | ❓ |
| `F_volt` | Charged only if `V_drop > 0.05`, then `min(0.2, V_drop)`. The paper gives `min(V_drop, V_thr)`. → [dso.py:L325-L328](../../../src_thesis/marketplace/dso/dso.py#L325-L328) | ⚠️ |
| `F_thermal` | `min(0.3, f_thermal)` → [dso.py:L331-L333](../../../src_thesis/marketplace/dso/dso.py#L331-L333) | ⚠️ The paper cap `f_thr` is undefined |
| `F_imb` | Only when `B_impact < 0`. `B_impact = 0` for P2P trades, and DSO trades carry no fees. So it is **effectively always 0**. → [dso.py:L336-L339](../../../src_thesis/marketplace/dso/dso.py#L336-L339)<br>[dso.py:L394-L442](../../../src_thesis/marketplace/dso/dso.py#L394-L442) | ⚠️ C |
| Fee settlement | Fees are stored on `Trade.fees` and summed into `dso.fees`. They are **never charged** to any agent. → [dso.py:L342-L343](../../../src_thesis/marketplace/dso/dso.py#L342-L343) | ❌ C, and see §2.5 |
| Constants | `C_thr = 0.8`, `V_thr = 0.05`, `T_thr = 0.2`, `f_cong = 0.5`, `f_volt = 0.15`, `f_zone = 0.15`, `f_imb = 0.15` → [dso.py:L65-L74](../../../src_thesis/marketplace/dso/dso.py#L65-L74) | ✅ Defaults match the text where given |

### 2.5 Agent accounting and battery ([P1] eq. 13, 14, 16)

```
B_t      = (G_t − D_t) + (E_bought − E_sold)
profit_{t+1} = profit_t + Σ_trades (p_sell·q_sell − p_buy·q_buy)
E_bat,t+1 = min(E + E_in·η_ch, SoC_max·C)   |   max(E − E_out/η_dis, SoC_min·C)
```

| Item | Code | Status |
|---|---|---|
| Balance (eq. 13) | `agent.balance = market.get_agent_position()` = `sold − bought` (no G, no D) → [lem.py:L440](../../../src_thesis/marketplace/lem.py#L440)<br>[matching.py:L440-L459](../../../src_thesis/marketplace/market/matching.py#L440-L459) | ⚠️ Different quantity with the opposite sign |
| Profit (eq. 14) | **Never updated.** The observation "mean profit" is always 0. → [der.py:L61](../../../src_thesis/marl/agents/der.py#L61)<br>[der.py:L109](../../../src_thesis/marl/agents/der.py#L109) | ❌ T5 |
| Battery dispatch | `energy_balance = G − D + sold − bought`. The trade term has the **wrong sign**: selling charges the battery. → [der.py:L293-L305](../../../src_thesis/marl/agents/der.py#L293-L305) | ❌ T7 |
| Charging | `_can_charge` refuses the *whole* charge if it would reach SoC_max. There is no partial fill up to the cap. → [battery.py:L95-L111](../../../src_thesis/marl/agents/battery.py#L95-L111)<br>[battery.py:L131-L156](../../../src_thesis/marl/agents/battery.py#L131-L156) | ❌ C ([battery.py](../../../src_thesis/marl/agents/battery.py#L95)) |
| Discharge efficiency | Stored energy drops by `E_out·η` (less than delivered). The paper drops it by `E_out/η` (more). → [battery.py:L158-L176](../../../src_thesis/marl/agents/battery.py#L158-L176) | ❌ C |
| Demand tracking | `satisfied = min(D, G + bought)`. Battery discharge is ignored. → [der.py:L250-L262](../../../src_thesis/marl/agents/der.py#L250-L262) | ⚠️ C |
| Energy conservation | There is no identity `G + imports + discharge = served D + exports + charge + curtailment`. → [lem.py:L391-L411](../../../src_thesis/marketplace/lem.py#L391-L411) | ❓ The paper does not state one |

### 2.6 Grid ([P1] eq. 18–20, §3.5)

| Item | Paper | Code ([network.py](../../../src_thesis/adapters/grid/network.py)) | Status |
|---|---|---|---|
| Distance | Shortest-path length | Same (`Location.distance_to`) → [base.py:L34-L57](../../../src_thesis/marketplace/grid/base.py#L34-L57) | ✅ |
| Loss (eq. 18) | `l = d·q·κ` | `d·q·0.03` → [network.py:L331-L348](../../../src_thesis/adapters/grid/network.py#L331-L348) | ✅ κ is not configurable per scenario |
| IEEE-34 topology | Canonical IEEE-34 feeder | Edge `832–888` is missing, so 888–890 is an island. The impedance table exists but is never used; weights are lengths only. → [config.py:L29-L39](../../../src_thesis/marketplace/grid/config.py#L29-L39)<br>[config.py:L43-L75](../../../src_thesis/marketplace/grid/config.py#L43-L75) | ❌ T13 |
| Edge capacity | Total capacity split across edges, more for shorter edges | `C_e = C·(1/w_e)/Σ(1/w)` → [network.py:L68-L82](../../../src_thesis/adapters/grid/network.py#L68-L82) | ✅ |
| Flow update | Every executed trade, along its path | Only **Stage-1** trades (`_create_trade`). Stage 2 and the DSO never update flows. → [network.py:L279-L329](../../../src_thesis/adapters/grid/network.py#L279-L329)<br>[matching.py:L589](../../../src_thesis/marketplace/market/matching.py#L589) | ❌ C |
| Flow lifetime | Per trading period (congestion is F/C for the period) | Initialised to U(0, 0.3)·C_e at reset, **accumulates** over the episode, capped at C_e → [network.py:L85](../../../src_thesis/adapters/grid/network.py#L85)<br>[network.py:L325](../../../src_thesis/adapters/grid/network.py#L325) | ❌ T10 |
| Congestion KPI (eq. 19) | Mean over edges of F_e/C_e | Same formula → [network.py:L405-L424](../../../src_thesis/adapters/grid/network.py#L405-L424) | ✅ |
| `B_grid` (eq. 20) | `Σ_i (G − D + bought − sold)` | Not computed anywhere. The observation "grid balance" is `dso.balance` (§2.4). → [lem.py:L472](../../../src_thesis/marketplace/lem.py#L472) | ❌ C |
| Zones | Same-zone bonus | Yes, via `F_zone` → [dso.py:L317-L319](../../../src_thesis/marketplace/dso/dso.py#L317-L319) | ✅ |

### 2.7 Reputation ([P1] eq. 12)

`r_i = w_rel·δ_rel + w_fair·δ_fair + w_grid·δ_grid`, with decay toward recent behaviour.

| Item | Code ([reputation.py](../../../src_thesis/marketplace/market/reputation.py#L70)) | Status |
|---|---|---|
| Weights | 0.3 / 0.2 / 0.5 → [reputation.py:L24-L26](../../../src_thesis/marketplace/market/reputation.py#L24-L26) | ❓ Paper values not given |
| Reliability | `trades/(trades + unmatched)`. It is ≡ 1 because nothing is ever unmatched. → [reputation.py:L129](../../../src_thesis/marketplace/market/reputation.py#L129) | ⚠️ |
| Grid term | Uses `matching.grid_balance`, which is ≡ 0 (T4), so δ_grid is neutral (→ 0.5) → [reputation.py:L162-L195](../../../src_thesis/marketplace/market/reputation.py#L162-L195) | ⚠️ |
| Decay | `r ← tod·r_old + (1 − tod)·r_new`. The weight depends on the time of day. → [reputation.py:L87](../../../src_thesis/marketplace/market/reputation.py#L87) | ❓ |
| Init | U(0, 1) with the same seed for every agent, so all agents get the **same** initial reputation → [reputation.py:L56-L68](../../../src_thesis/marketplace/market/reputation.py#L56-L68)<br>[lem.py:L283](../../../src_thesis/marketplace/lem.py#L283) | ⚠️ C |

### 2.8 Implicit-cooperation KPIs ([P1] eq. 21–27)

| KPI | Paper | Code ([implicit_cooperation.py](../../../src_thesis/cooperation/implicit_cooperation.py)) | Status |
|---|---|---|---|
| Social welfare | `Σ p·q` (labelled "consumer + producer surplus") | `Σ p·\|q\|`, **unnormalised** → [implicit_cooperation.py:L93](../../../src_thesis/cooperation/implicit_cooperation.py#L93) | ❓ The formula is turnover, not surplus |
| Liquidity | `Σ q` | Same, unnormalised → [implicit_cooperation.py:L96](../../../src_thesis/cooperation/implicit_cooperation.py#L96) | ✅ |
| Bid-ask spread | `E[p_buy] − E[p_sell]` over orders | Same → [implicit_cooperation.py:L99-L101](../../../src_thesis/cooperation/implicit_cooperation.py#L99-L101) | ✅ |
| Price volatility | Std of clearing price "over a window" | Std over the **whole episode so far** → [implicit_cooperation.py:L104-L105](../../../src_thesis/cooperation/implicit_cooperation.py#L104-L105) | ⚠️ |
| Supply–demand imbalance | `\|Σ q_buy − Σ q_sell\| / C_grid` | `\|Σ_trades q\| / C`, which is total volume, not imbalance → [implicit_cooperation.py:L122-L123](../../../src_thesis/cooperation/implicit_cooperation.py#L122-L123) | ❌ C |
| Grid congestion | Mean edge congestion | `dso.congestion_level` → [implicit_cooperation.py:L126](../../../src_thesis/cooperation/implicit_cooperation.py#L126) | ✅ (inherits §2.6) |
| Coordination score | `1 − Imbalance` | `1 − volume/C` → [implicit_cooperation.py:L141-L142](../../../src_thesis/cooperation/implicit_cooperation.py#L141-L142) | ❌ Inherits the above |
| Coordination convergence | Volume stability over a window | `1 − std/mean` of the last 3 clearing volumes → [implicit_cooperation.py:L145-L151](../../../src_thesis/cooperation/implicit_cooperation.py#L145-L151) | ✅ |
| Self-consumption | `Σ q_P2P / (Σ q_P2P + Σ q_DSO)` | Same → [implicit_cooperation.py:L188](../../../src_thesis/cooperation/implicit_cooperation.py#L188) | ✅ |
| Flexibility utilisation | `Σ q_P2P / F_total` | Same, where F_total counts both sell and buy flexibility → [implicit_cooperation.py:L190-L223](../../../src_thesis/cooperation/implicit_cooperation.py#L190-L223) | ✅ |

### 2.9 Observation ([P1] Table 2: 16 market + 16 private + 10 KPI = 42, plus optional N reputations)

| Item | Code ([observation.py](../../../src_thesis/marketplace/observation.py#L259)) | Status |
|---|---|---|
| Layout, 42 dims | Matches Table 2 order → [observation.py:L64-L176](../../../src_thesis/marketplace/observation.py#L64-L176) | ✅ |
| G, D "forecasts" ([P2] Table 7: forecast error 30 %) | True values for `t+1`. `max_error` and `num_anchor` are read in `lem.__init__` and **never used**. → [lem.py:L65-L66](../../../src_thesis/marketplace/lem.py#L65-L66)<br>[observation.py:L334-L335](../../../src_thesis/marketplace/observation.py#L334-L335) | ❌ C |
| Remaining demand/supply | `Σ profile[t:]` of the **true** future, which is perfect foresight → [observation.py:L338-L341](../../../src_thesis/marketplace/observation.py#L338-L341) | ⚠️ C |
| Mean profit | Always 0 (§2.5) → [observation.py:L342](../../../src_thesis/marketplace/observation.py#L342) | ❌ T5 |
| Grid balance | `dso.balance` ≡ 0 (§2.4) → [observation.py:L285](../../../src_thesis/marketplace/observation.py#L285) | ❌ T4 |
| Scaling | Raw units. Box bounds are set but there is no normalisation. → [observation.py:L353](../../../src_thesis/marketplace/observation.py#L353) | ❓ |

### 2.10 Reward ([P1] eq. 3–6)

```
R_i   = sign(r_raw)·ln(1 + |r_raw|/20)·20                                      (3)
r_raw = R_base,i·(1 + ln(1 + max(0, f_coop·f_contrib,i − 1))/5) − γ_DSO,i − γ_UD,i   (4)  [as printed]
R_base,i = 10·r_grid + 1.5·r_res + 5·r_trade + 2·r_stab + 3·r_econ
f_coop   = (1/56)·Σ_k f_k·k̃,   k̃ = 1 − k for "lower is better"                    (5)
f_contrib,i = 0.5·r_grid + 0.3·r_share + 0.2·r_dev                                  (6)
```

[P2] eq. 3 gives a different form again: `R_i = R_base·(1 + f_coop·f_contrib) − γ_DSO − γ_UD`, with no log.

Code: [reward.py `calculate_reward`](../../../src_thesis/marketplace/reward.py#L103).

| Item | Code | Status |
|---|---|---|
| Log compression (3) | Same → [reward.py:L232](../../../src_thesis/marketplace/reward.py#L232) | ✅ |
| Penalty scaling | Paper (§3.2.4): penalties are "implicitly scaled relative to the reward magnitude". Code: `scale = 0.3·max(\|boosted base\|, 1)` → [reward.py:L224-L226](../../../src_thesis/marketplace/reward.py#L224-L226) | ✅ The text describes the code; no formula is given |
| `R_base` components | Paper gives only names, weights and "typical ranges", no formulas; the code is the only definition → [reward.py:L148-L166](../../../src_thesis/marketplace/reward.py#L148-L166) | ❓ I-76 |
| Cooperation boost (4) | `1 + ln(1 + f_coop·f_contrib)/5`. The code has no `−1`. The printed eq. 4 is ≡ `R_base` when `f_coop·f_contrib ≤ 1`. → [reward.py:L218-L221](../../../src_thesis/marketplace/reward.py#L218-L221) | ❓ The paper contradicts itself ([P1] vs [P2]) |
| `f_coop` ∈ [0, 1] | Unnormalised SW and liquidity, and "1 − spread/volatility" in price units → [reward.py:L170-L192](../../../src_thesis/marketplace/reward.py#L170-L192) | ❌ T9 (≈ 1811) |
| Weights (5) | 7, 1.5, 1.5, 3, 10, 9, 5, 8, 5, 6 (Σ = 56) → [reward.py:L59-L68](../../../src_thesis/marketplace/reward.py#L59-L68) | ✅ |
| `r_trade` | `0.3·ρ_local + 0.3·ρ_dso`. `_w_local` is overwritten 0.7 → 0.3. This matches the paper's printed `0.3/0.3`, which looks like it copied the bug. → [reward.py:L234-L251](../../../src_thesis/marketplace/reward.py#L234-L251)<br>[reward.py:L79-L93](../../../src_thesis/marketplace/reward.py#L79-L93) | ⚠️ |
| `r_res`, `r_trade`, `r_grid` inputs | Use `order.quantity` after matching, which is 0 (T3). So `r_res ≡ −1.5`, `r_trade ≡ 0`, and the contribution term in `r_grid` is 0. → [reward.py:L248-L249](../../../src_thesis/marketplace/reward.py#L248-L249)<br>[reward.py:L406-L412](../../../src_thesis/marketplace/reward.py#L406-L412) | ❌ T3 |
| `r_grid` | `(1 − \|B\|/C) + (±q/C − 10·\|B\|/C) + 0.5·impact`, with `B = dso.balance ≡ 0` and `impact` driven by last step's `agent.balance` → [reward.py:L253-L309](../../../src_thesis/marketplace/reward.py#L253-L309) | ❌ Inherits T3, T4 |
| `r_econ` | `0.4·price_eff + 0.6·dso_profit_score`. `execution_efficiency` is computed but unused. → [reward.py:L311-L386](../../../src_thesis/marketplace/reward.py#L311-L386) | ✅ / ⚠️ |
| `γ_DSO` | `dso_ratio·15·\|B\|/C·scale`, with `scale = 0.3·max(\|boosted\|, 1)`. It is 0 while `B ≡ 0`. → [reward.py:L201-L202](../../../src_thesis/marketplace/reward.py#L201-L202) | ❌ Inherits T4 |
| `γ_UD` (paper weight `p_no_trades = 5`) | Terminal only: `ratio²·scale`. It **never fires** because `is_terminal` is never true. `p_no_trades` is used elsewhere. → [reward.py:L204-L214](../../../src_thesis/marketplace/reward.py#L204-L214) | ❌ T2 |
| No-trade guard | No trades → fixed `−4.46` (log of `−5`), returned before any other term → [reward.py:L135-L136](../../../src_thesis/marketplace/reward.py#L135-L136) | ❓ Not in the paper. It is reachable only when `q_min = 0`, which is Case 6's setting; otherwise the DSO always fills. |
| `f_contrib` (6) | 0.5 grid (≡ 0.5 while `B = 0`) + 0.2 price + 0.3 local-share by *count* of trades. [P2] describes the grid part as the marginal effect `−∂\|B_grid\|/∂a_i`. → [reward.py:L448-L499](../../../src_thesis/marketplace/reward.py#L448-L499) | ⚠️ |

### 2.11 Episode, seeds, profiles

| Item | Paper | Code | Status |
|---|---|---|---|
| Horizon | τ = 24 steps ([P2] Table 7) | 23 → [lem.py:L443-L453](../../../src_thesis/marketplace/lem.py#L443-L453) | ❌ T1 |
| Seed | Global seed 42 controls all stochasticity | Global `np.random.seed(seed)` is called again in env, agent, battery, market, DSO, grid and reputation resets. `reset(seed=None)` falls back to the config seed, so with a configured seed **every episode is identical** (profiles, reputation, SoC, flows). `LocalEnergyMarket.seed()` is shadowed by the `self.seed` attribute. → [lem.py:L271-L274](../../../src_thesis/marketplace/lem.py#L271-L274)<br>[lem.py:L507-L514](../../../src_thesis/marketplace/lem.py#L507-L514) | ⚠️ C |
| Profiles (eq. 17) | `G = C·I_t·(1 + ε + c)` (multiplicative), from files or procedural | Procedural uses `(base + noise + cloud)·C` (additive). With CSV files, each reset picks a **random column** and applies a random scale of 1–1.3 (G) or 0.6–1.0 (D). → [der.py:L105-L131](../../../src_thesis/adapters/profiles/der.py#L105-L131)<br>[der.py:L172-L198](../../../src_thesis/adapters/profiles/der.py#L172-L198) | ⚠️ / ❓ This makes Case 6 unreproducible from the paper alone |
| Profiles given to `DERAgent` | — | Overwritten at `reset()` → [lem.py:L285-L293](../../../src_thesis/marketplace/lem.py#L285-L293) | ⚠️ T11 |

### 2.12 MARL modes and training ([P2] §3.4, §4.2, Tables 7–8)

| Item | Paper | Code ([train.py](../../../src_thesis/marl/train.py), [ctde.py](../../../src_thesis/marl/ctde.py)) | Status |
|---|---|---|---|
| DTDE | Independent actor and critic per agent on local `o_i` and `R_i` | One module per agent id, `policy_mapping_fn = agent_id` → [train.py:L332-L349](../../../src_thesis/marl/train.py#L332-L349) | ✅ |
| CTCE | One policy on the global state → joint action. Objective `Σ_i R_i` ([P2] eq. 17) | `GroupedLEM` + `CTCEModule` on concatenated observations. Reward = **sum**. → [train.py:L309-L318](../../../src_thesis/marl/train.py#L309-L318)<br>[train.py:L684](../../../src_thesis/marl/train.py#L684) | ✅ |
| CTDE | Centralized critic on (s, a). **Decentralized actor** `π(a_i \| o_i)` | Rollout and inference use per-agent `pi_heads` on local `o_i` ([ctde.py:74](../../../src_thesis/marl/ctde.py#L74)). The training loss uses a separate centralized `pi_encoder`/`pi` on concatenated observations ([ctde.py:124](../../../src_thesis/marl/ctde.py#L124)). So the actor that is trained is **not** the actor that acts. → [ctde.py:L47-L56](../../../src_thesis/marl/ctde.py#L47-L56)<br>[ctde.py:L124-L125](../../../src_thesis/marl/ctde.py#L124-L125) | ❌ C |
| Hyperparameters (Table 8) | lr 1e-5, γ 0.99, entropy 0.01, clip 0.5, PPO clip 0.2, minibatch 128, SAC buffer 1000, target entropy rule | Same → [train.py:L207-L262](../../../src_thesis/marl/train.py#L207-L262) | ✅ |
| PBT | 10 samples × 9 configs | PBT with `num_samples=tune_samples`. Mutation domain lr ∈ [1e-4, 1e-2] **excludes** the initial 1e-5. Entropy mutation reaches up to 10. → [train.py:L180-L195](../../../src_thesis/marl/train.py#L180-L195)<br>[train.py:L432-L435](../../../src_thesis/marl/train.py#L432-L435) | ⚠️ C |
| Budget | "10 000 episodes" | Stop criterion is `training_iteration`, which is not episodes. The number of episodes per iteration differs by algorithm. → [train.py:L440](../../../src_thesis/marl/train.py#L440) | ❓ |
| Case 6 | 8 agents, IEEE-34 nodes, 1800 kW, prices 20–600, quantities 0–180 ([P2] Tables 6–7) | Configured in the notebook. The profile-to-agent mapping is **not published**. → [case6_implicit_cooperation.ipynb](../../../notebooks/case6_implicit_cooperation.ipynb) | ❓ (see baseline `paper-faithful-freeze-contract.md`) |
| Zero-intelligence baseline ([P1] §4.2) | Random bids within bounds, respecting physical constraints | Only in notebooks: `action_space.sample()` followed by the §2.1 feasibility step. There is no reusable baseline. → [case5_battery_coordination.ipynb](../../../notebooks/case5_battery_coordination.ipynb) | ⚠️ C |
| Evaluation metrics ([P2] §4.3) | Coordination score, "grid balance index B_index" (including losses and external reliance), P2P ratio, social welfare, agent responsiveness | `B_index` is **not defined** in the paper and does not exist in the code. Responsiveness exists only in `cooperation/metrics` (unaudited, I-65). → [market_analytics.py:L123-L136](../../../src_thesis/cooperation/metrics/market_analytics.py#L123-L136) | ❓ C |

---

## 3. Paper origin: is the paper's method sound?

This asks whether the paper's method holds up on its own terms, before any code is involved. None of these items prevents building a working model. Each one needs a **recorded decision** (paper text → options → chosen rule → reason), because the paper cannot settle it. The register rows carry the decisions.

| Topic | Concern | Why it matters for the thesis | Register |
|---|---|---|---|
| Reward form (eq. 4) | [P1] eq. 4 as printed is ≡ `R_base` for normalised `f_coop·f_contrib ≤ 1`. [P2] eq. 3 has a different form, and the code a third. | The paper's central contribution, the cooperation bonus, has no single definition | I-42 |
| Reward components | `R_base` terms are given only as names, weights and ranges | The code is the de-facto specification, and it is partly broken (I-43, I-44) | I-76 |
| `f_coop` normalisation | Claimed to lie in [0, 1], but welfare, liquidity, spread and volatility have no stated normalisation ranges | The weights (Σ = 56) are meaningless across unnormalised scales | I-75, I-41 |
| Social welfare (eq. 21) | Defined as consumer + producer surplus, but written as `Σ p·q`, which is turnover. Transfers between agents cancel in true welfare. | This is the highest-weighted KPI in `f_coop` (7/56) | I-36 |
| Imbalance (eq. 24) | `\|Σq_buy − Σq_sell\|` computed over *trades* is ≡ 0, since every trade has one buyer and one seller. It only means something over *orders* or physical net positions. `B_grid` (eq. 20) after full DSO clearing is ≈ 0 by construction. | Coordination score (eq. 27), the headline metric in [P2], depends on it | I-68, I-35 |
| KPI labels | "DER self-consumption" is defined as P2P share | Wording in thesis results | I-69 |
| Grid physics | Losses are linear in `d·q` (not `I²R`) and unbounded when `d·κ > 1`. Voltage drop is `f·d`. Flows are transport on a graph, not power flow. The paper nevertheless calls this "high-fidelity". | Scope of any physical claim; motivates SimBench | I-70 |
| Fee design | `F_trans` has no formula. Thermal fees start at 20 % loading, below the 80 % congestion threshold. | Fees shape P2P incentives only if they are charged at all (I-28) | I-29, I-74 |
| Battery | eq. 16 has no charge/discharge power limit, although the text claims one. eq. 15 ignores efficiency. | Storage arbitrage results | I-71 |
| Market design | Stage-1 DSO-preferred sub-stage; clearing price mixes P2P and DSO tariffs | The "clearing price" signal in observations and rewards | I-15, I-16 |
| Action semantics | No explicit "submit nothing" action. α and β are discrete but modelled as continuous. | Whether inactivity can be learned or exploited; exploration | I-11, I-47 |
| Information | "Forecasts" are specified (30 % error) but the observation also exposes exact remaining future demand | Partial observability and privacy claims | I-39 |
| Units | P1 uses $/MWh (35–280). P2 plots up to 600 "$/kWh". Quantities are kWh per 1-h step with Δt implicit. | Every economic number | I-56 |
| Paradigm comparison | CTCE is called a "theoretical upper bound" but uses the same approximate learner. The group reward is a sum over agents, so returns scale with N. | Validity of the 3×3 ranking in [P2] Table 9 | I-60, I-73 |
| Evaluation protocol | One fixed seed (42), evaluation on the training scenario, ranking by shaped reward | No variance or generalisation evidence for [P2]'s claims | I-72, I-50 |
| Data | The Case 6 profile-to-agent mapping and scaling are not published | Exact reproduction is impossible without the authors | I-51 |

**Verdict on the paper's method:** the overall design is coherent and worth building on: a market with a physical-grid layer, KPI-shaped observations and rewards, and three training paradigms compared. The weak points are **definitions**, not architecture: reward and KPI formulas, grid-physics scope, and the evaluation protocol. They can all be fixed by recorded decisions. None of them requires abandoning the framework.

## 4. Impact on the published results

The upstream repository is the published version. If the papers' figures were produced with this code (not independently confirmable), then:

- **[P1] §5, Case 5 (battery, zero-intelligence agents):** the case uses `BID_ASK_SPREAD` pricing, which returns the buyer's bid (I-17). The P2P price distributions in Fig. 5 are therefore buyer bids. Battery dispatch has the reversed trade sign (I-18) and the wrong efficiency direction (I-19, I-20). The "imbalance" and "coordination score" in Figs. 6–7 measure traded volume, not imbalance (I-35, I-68). The paper's conclusion that batteries stabilise prices is **not supported** by this code.
- **[P2] Case 6 (MARL 3×3):** the reward the agents optimised has constant or inactive components (I-43, I-44), an unnormalised `f_coop` (I-41), and no terminal penalty (I-02). Observations expose exact future demand (I-39) and a constant zero profit (I-27). The CTDE actor that acted was never trained (I-48). The ranking in Table 9 describes learning on *this* reward, not on the paper's intended model.

**Thesis consequence:** the thesis cannot claim to reproduce either paper. The defensible framing is a **paper-faithful corrected reimplementation**: every paper decision and fidelity deviation is listed, and the original is kept as a named comparison.

## 5. Validation order

Superseded by [marlem-validation-by-level.md](plan-by-level.md). That document orders the work by the paper's Figure 2 levels: Level 0 → Level 2 → Level 1.

## 6. Issue register

**VP** is the matching ID in [validation-plan-fix.md](validation-plan-fix.md); `—` means that plan does not list it. I-52 to I-67 were added from that plan, which covers things outside the paper comparison.

**Origin** is defined in §0 (Paper, Fidelity, Code). **Step** is the validation step in [marlem-validation-by-level.md](plan-by-level.md), which also holds each issue's **status**.

Each issue has a stable ID, so tests, commits and decisions can refer to it (for example `test_I01_...` or `fix(I-12): ...`). Type uses the §0 legend. **Code** links open the exact lines in `src_thesis/` (original code, as of 2026-09-23; line numbers shift once code is edited).

| ID | Origin | Step | Issue | Code | Type | Ev. | § | VP |
|---|---|---|---|---|---|---|---|---|
| I-01 | Fidelity | A1 | Only 23 of 24 periods run: termination is checked after the step increment against `max_steps − 1` | [lem.py:L443-L453](../../../src_thesis/marketplace/lem.py#L443-L453) | ❌ | T1 | 2.11 | P0-07 |
| I-02 | Fidelity | A1 | `is_terminal` is never true, so the terminal unmet-demand penalty never applies | [lem.py:L430](../../../src_thesis/marketplace/lem.py#L430)<br>[reward.py:L207-L214](../../../src_thesis/marketplace/reward.py#L207-L214) | ❌ | T2 | 2.10 | P0-07 |
| I-03 | Code | A1 | `reset(seed=None)` falls back to the config seed, so every episode is identical | [lem.py:L272-L274](../../../src_thesis/marketplace/lem.py#L272-L274) | ⚠️ | C | 2.11 | P2-01 |
| I-04 | Code | A1 | `LocalEnergyMarket.seed()` is shadowed by the `self.seed` attribute | [lem.py:L67](../../../src_thesis/marketplace/lem.py#L67)<br>[lem.py:L507-L514](../../../src_thesis/marketplace/lem.py#L507-L514) | ⚠️ | C | 2.11 | — |
| I-05 | Code | A2 | Profiles passed to `DERAgent(...)` are overwritten at `reset()` | [lem.py:L280-L293](../../../src_thesis/marketplace/lem.py#L280-L293) | ⚠️ | T11 | 2.11 | P0-08 |
| I-06 | Fidelity | A2 | CSV profiles use a random column and random scale per reset. Procedural G is additive, not eq. 17's multiplicative form | [base.py:L31-L43](../../../src_thesis/adapters/profiles/base.py#L31-L43)<br>[der.py:L119-L131](../../../src_thesis/adapters/profiles/der.py#L119-L131)<br>[der.py:L172-L198](../../../src_thesis/adapters/profiles/der.py#L172-L198) | ⚠️ | C | 2.11 | P2-03 |
| I-07 | Code | A9 | All agents get the same initial reputation (the RNG is reseeded before each draw) | [lem.py:L283](../../../src_thesis/marketplace/lem.py#L283)<br>[reputation.py:L56-L68](../../../src_thesis/marketplace/market/reputation.py#L56-L68) | ⚠️ | C | 2.7 | P0-08 |
| I-08 | Fidelity | A3 | Feasibility clipping does not implement eq. 15: it treats the requested `q` as the need | [der.py:L196-L228](../../../src_thesis/marl/agents/der.py#L196-L228) | ❌ | C | 2.1 | P0-02 |
| I-09 | Fidelity | A3 | `is_buy` is truthy in `adjust_action_for_battery` but `> 0.5` in `step`, so the order is sized for the wrong direction | [der.py:L196](../../../src_thesis/marl/agents/der.py#L196)<br>[lem.py:L358](../../../src_thesis/marketplace/lem.py#L358) | ❌ | T8 | 2.1 | P0-03 |
| I-10 | Fidelity | A3 | β = "no preference" is reachable only at the exact upper bound | [action.py:L35-L44](../../../src_thesis/marketplace/action.py#L35-L44)<br>[action.py:L68-L89](../../../src_thesis/marketplace/action.py#L68-L89)<br>[lem.py:L359](../../../src_thesis/marketplace/lem.py#L359) | ⚠️ | C | 2.1 | P0-03 |
| I-11 | Paper | A3 | No "submit nothing" action when `q_min > 0` | [der.py:L231-L232](../../../src_thesis/marl/agents/der.py#L231-L232) | ❓ | — | 2.1 | P0-02 |
| I-12 | Code | A5 | Orders are mutated in place, so the reward, KPIs and info see residual quantities (0), not submitted ones | [matching.py:L361-L362](../../../src_thesis/marketplace/market/matching.py#L361-L362)<br>[dso.py:L212-L253](../../../src_thesis/marketplace/dso/dso.py#L212-L253)<br>[lem.py:L424-L431](../../../src_thesis/marketplace/lem.py#L424-L431) | ❌ | T3 | 2.2 | P0-04 |
| I-13 | Fidelity | A4 | `SELLER` pricing returns the buyer's price (positional-argument bug) | [mechanism.py:L69-L84](../../../src_thesis/marketplace/market/mechanism.py#L69-L84)<br>[matching.py:L324-L326](../../../src_thesis/marketplace/market/matching.py#L324-L326) | ❌ | T6 | 2.3 | P0-05 |
| I-14 | Fidelity | A5 | P2P loss is topped up from the DSO. The buyer's `energy_bought` counts `q + loss` | [matching.py:L361](../../../src_thesis/marketplace/market/matching.py#L361)<br>[lem.py:L392-L411](../../../src_thesis/marketplace/lem.py#L392-L411) | ⚠️ | C | 2.2 | P1-01 |
| I-15 | Paper | A5 | Stage 1 clears DSO-preferred orders with the DSO before any P2P matching | [matching.py:L620-L647](../../../src_thesis/marketplace/market/matching.py#L620-L647) | ❓ | — | 2.2 | P1-13 |
| I-16 | Paper | A5 | The clearing price is a VWAP that includes DSO trades | [matching.py:L399](../../../src_thesis/marketplace/market/matching.py#L399) | ❓ | — | 2.2 | P1-07, P1-13 |
| I-17 | Fidelity | A4 | `BID_ASK_SPREAD` pricing receives `market_price` as `factor`, so it returns the buyer's price. The mechanism is also absent from §3.3.3 | [mechanism.py:L87-L111](../../../src_thesis/marketplace/market/mechanism.py#L87-L111)<br>[matching.py:L324-L326](../../../src_thesis/marketplace/market/matching.py#L324-L326) | ❌ | T12 | 2.3 | P0-05 |
| I-18 | Fidelity | A8 | Battery dispatch has the trade term's sign reversed: selling charges the battery | [der.py:L293-L305](../../../src_thesis/marl/agents/der.py#L293-L305) | ❌ | T7 | 2.5 | P0-01 |
| I-19 | Fidelity | A8 | A charge is refused entirely if it would reach SoC_max; there is no partial fill | [battery.py:L95-L111](../../../src_thesis/marl/agents/battery.py#L95-L111)<br>[battery.py:L131-L156](../../../src_thesis/marl/agents/battery.py#L131-L156) | ❌ | C | 2.5 | P0-06 |
| I-20 | Fidelity | A8 | Discharge efficiency is applied in the wrong direction (`·η` instead of `/η`) | [battery.py:L158-L176](../../../src_thesis/marl/agents/battery.py#L158-L176) | ❌ | C | 2.5 | P0-06 |
| I-21 | Code | A8 | Demand satisfaction ignores battery discharge | [der.py:L250-L262](../../../src_thesis/marl/agents/der.py#L250-L262) | ⚠️ | C | 2.5 | — |
| I-22 | Paper | A8 | No household energy-conservation identity is enforced | [lem.py:L391-L411](../../../src_thesis/marketplace/lem.py#L391-L411) | ❓ | — | 2.5 | P1-01 |
| I-23 | Fidelity | A8 | `B_grid` (eq. 20) is never computed. The "grid balance" observation is `dso.balance` | [lem.py:L472](../../../src_thesis/marketplace/lem.py#L472)<br>[observation.py:L285](../../../src_thesis/marketplace/observation.py#L285) | ❌ | C | 2.6 | — |
| I-24 | Fidelity | A6 | `dso.balance` changes only on Stage-1 DSO-preferred trades and carries across steps, so it is ≡ 0 by default | [matching.py:L272-L280](../../../src_thesis/marketplace/market/matching.py#L272-L280)<br>[matching.py:L388](../../../src_thesis/marketplace/market/matching.py#L388) | ❌ | T4 | 2.4 | — |
| I-25 | Code | A6 | The B_DSO sign convention is inconsistent between `match_orders` and `_match_preferred_partners` | [matching.py:L272-L280](../../../src_thesis/marketplace/market/matching.py#L272-L280)<br>[matching.py:L640-L647](../../../src_thesis/marketplace/market/matching.py#L640-L647) | ❓ | C | 2.4 | — |
| I-26 | Fidelity | A8 | `agent.balance = sold − bought`, not eq. 13 | [lem.py:L440](../../../src_thesis/marketplace/lem.py#L440)<br>[matching.py:L440-L459](../../../src_thesis/marketplace/market/matching.py#L440-L459) | ⚠️ | C | 2.5 | P0-08 |
| I-27 | Fidelity | A8 | Agent profit (eq. 14) is never updated | [der.py:L61](../../../src_thesis/marl/agents/der.py#L61)<br>[der.py:L109](../../../src_thesis/marl/agents/der.py#L109)<br>[observation.py:L342](../../../src_thesis/marketplace/observation.py#L342) | ❌ | T5 | 2.5 | P0-11 |
| I-28 | Fidelity | A6 | Grid fees are computed but never charged to anyone | [dso.py:L342-L343](../../../src_thesis/marketplace/dso/dso.py#L342-L343)<br>[matching.py:L333-L346](../../../src_thesis/marketplace/market/matching.py#L333-L346) | ❌ | C | 2.4 | P0-11 |
| I-29 | Paper | A6 | `F_trans` has no formula in the paper; the code uses 0 | [dso.py:L293](../../../src_thesis/marketplace/dso/dso.py#L293) | ❓ | — | 2.4 | P0-11 |
| I-30 | Fidelity | A6 | `F_volt` and `F_thermal` caps (0.2, 0.3) differ from or are undefined in the paper | [dso.py:L326-L333](../../../src_thesis/marketplace/dso/dso.py#L326-L333) | ⚠️ | C | 2.4 | — |
| I-31 | Fidelity | A6 | `F_imb` is effectively always 0 | [dso.py:L336-L339](../../../src_thesis/marketplace/dso/dso.py#L336-L339)<br>[dso.py:L394-L442](../../../src_thesis/marketplace/dso/dso.py#L394-L442) | ⚠️ | C | 2.4 | — |
| I-32 | Fidelity | A7 | Only Stage-1 trades update edge flows | [matching.py:L589](../../../src_thesis/marketplace/market/matching.py#L589)<br>[matching.py:L282-L370](../../../src_thesis/marketplace/market/matching.py#L282-L370) | ❌ | C | 2.6 | P1-02 |
| I-33 | Fidelity | A7 | Edge flows start random and accumulate over the episode instead of being per period | [network.py:L85](../../../src_thesis/adapters/grid/network.py#L85)<br>[network.py:L325](../../../src_thesis/adapters/grid/network.py#L325) | ❌ | T10 | 2.6 | P1-03 |
| I-34 | Code | A7 | Loss factor κ = 0.03 is hard-coded | [network.py:L331-L348](../../../src_thesis/adapters/grid/network.py#L331-L348) | ⚠️ | C | 2.6 | — |
| I-35 | Fidelity | B1 | "Supply-demand imbalance" is volume/C, not `\|Σbuy − Σsell\|/C`. The coordination score inherits this | [implicit_cooperation.py:L122-L123](../../../src_thesis/cooperation/implicit_cooperation.py#L122-L123)<br>[implicit_cooperation.py:L141-L142](../../../src_thesis/cooperation/implicit_cooperation.py#L141-L142) | ❌ | C | 2.8 | P1-07 |
| I-36 | Paper | B1 | Social welfare is turnover `Σ p·q`, not surplus | [implicit_cooperation.py:L93](../../../src_thesis/cooperation/implicit_cooperation.py#L93) | ❓ | — | 2.8 | P1-07 |
| I-37 | Fidelity | B1 | Price volatility is computed over the whole episode, not a window | [implicit_cooperation.py:L104-L105](../../../src_thesis/cooperation/implicit_cooperation.py#L104-L105) | ⚠️ | C | 2.8 | — |
| I-38 | Code | A9 | Reputation: reliability ≡ 1, the grid term is neutral, and decay is weighted by time of day | [reputation.py:L129](../../../src_thesis/marketplace/market/reputation.py#L129)<br>[reputation.py:L87](../../../src_thesis/marketplace/market/reputation.py#L87) | ⚠️ | C | 2.7 | P1-10 |
| I-39 | Fidelity | C1 | Forecast error (`max_error`) is never applied, so the "remaining demand/supply" observations reveal the true future | [lem.py:L65-L66](../../../src_thesis/marketplace/lem.py#L65-L66)<br>[observation.py:L338-L341](../../../src_thesis/marketplace/observation.py#L338-L341) | ❌ | C | 2.9 | P1-09 |
| I-40 | Paper | C1 | Observations are raw and unnormalised | [observation.py:L333-L353](../../../src_thesis/marketplace/observation.py#L333-L353) | ❓ | — | 2.9 | — |
| I-41 | Fidelity | C2 | `f_coop` is not in [0, 1] (≈ 1811) | [reward.py:L170-L192](../../../src_thesis/marketplace/reward.py#L170-L192) | ❌ | T9 | 2.10 | P1-06 |
| I-42 | Paper | C2 | The cooperation-boost form differs across [P1] eq. 4, the code and [P2] eq. 3 | [reward.py:L218-L221](../../../src_thesis/marketplace/reward.py#L218-L221) | ❓ | — | 2.10 | — |
| I-43 | Code | C2 | `r_res ≡ −1.5` and `r_trade ≡ 0` (caused by I-12) | [reward.py:L406-L412](../../../src_thesis/marketplace/reward.py#L406-L412)<br>[reward.py:L248-L249](../../../src_thesis/marketplace/reward.py#L248-L249) | ❌ | T3 | 2.10 | P0-04 |
| I-44 | Fidelity | C2 | `r_grid`, `γ_DSO` and the grid part of `f_contrib` are inactive (caused by I-24) | [reward.py:L202](../../../src_thesis/marketplace/reward.py#L202)<br>[reward.py:L253-L309](../../../src_thesis/marketplace/reward.py#L253-L309)<br>[reward.py:L472-L484](../../../src_thesis/marketplace/reward.py#L472-L484) | ❌ | T4 | 2.10 | — |
| I-45 | Code | C2 | `_w_local` is overwritten 0.7 → 0.3, so `r_trade = 0.3ρ_local + 0.3ρ_dso` (the paper prints 0.3/0.3) | [reward.py:L79](../../../src_thesis/marketplace/reward.py#L79)<br>[reward.py:L93](../../../src_thesis/marketplace/reward.py#L93) | ⚠️ | C | 2.10 | P1-06 |
| I-46 | Fidelity | C2 | The unmet-demand penalty uses `p_dso`, not the paper's `p_no_trades = 5` | [reward.py:L207-L214](../../../src_thesis/marketplace/reward.py#L207-L214)<br>[reward.py:L226](../../../src_thesis/marketplace/reward.py#L226) | ⚠️ | C | 2.10 | — |
| I-47 | Paper | C2 | The no-trade guard returns a fixed −4.46 before any other term | [reward.py:L135-L136](../../../src_thesis/marketplace/reward.py#L135-L136) | ❓ | — | 2.10 | P1-06 |
| I-48 | Fidelity | D1 | CTDE trains a centralized `pi` but acts with per-agent `pi_heads`, which are never trained | [ctde.py:L47-L56](../../../src_thesis/marl/ctde.py#L47-L56)<br>[ctde.py:L74-L87](../../../src_thesis/marl/ctde.py#L74-L87)<br>[ctde.py:L124-L125](../../../src_thesis/marl/ctde.py#L124-L125) | ❌ | C | 2.12 | P0-09 |
| I-49 | Code | D1 | The PBT lr domain [1e-4, 1e-2] excludes the initial 1e-5, and the entropy domain reaches 10 | [train.py:L180-L195](../../../src_thesis/marl/train.py#L180-L195)<br>[train.py:L216](../../../src_thesis/marl/train.py#L216) | ⚠️ | C | 2.12 | — |
| I-50 | Paper | D1 | The budget is counted in training iterations, but the paper says "10 000 episodes" | [train.py:L440](../../../src_thesis/marl/train.py#L440) | ❓ | — | 2.12 | — |
| I-51 | Paper | D3 | The Case 6 profile-to-agent mapping is unpublished | [case6_implicit_cooperation.ipynb](../../../notebooks/case6_implicit_cooperation.ipynb) | ❓ | — | 2.12 | — |
| I-52 | Code | A0 | No functioning test gate: tests without assertions, fixtures that fail, signatures that have drifted | [test_battery.py:L13-L62](../../../tests/test_battery.py#L13-L62)<br>[test_checkpoint.py](../../../tests/test_checkpoint.py) | ❌ | — | — | P0-12 |
| I-53 | Code | A0 | Defensive checks hide bad state (dead capacity check, bare `except`, float-only validators, mutable defaults) | [network.py:L38](../../../src_thesis/adapters/grid/network.py#L38)<br>[network.py:L95-L96](../../../src_thesis/adapters/grid/network.py#L95-L96)<br>[base.py:L56](../../../src_thesis/marketplace/grid/base.py#L56) | ⚠️ | — | — | P3-02 |
| I-54 | Code | A5 | DSO fallback skips grid feasibility (zero distance, loss and fee), and `validate_grid_constraints` ignores direction | [dso.py:L190-L272](../../../src_thesis/marketplace/dso/dso.py#L190-L272)<br>[dso.py:L347-L392](../../../src_thesis/marketplace/dso/dso.py#L347-L392) | ⚠️ | — | 2.2 | P1-05 |
| I-55 | Code | A5 | The Stage-2 capacity check uses `max_quantity·N` and the current balance, not grid capacity or the projected trade | [matching.py:L172](../../../src_thesis/marketplace/market/matching.py#L172)<br>[matching.py:L312-L313](../../../src_thesis/marketplace/market/matching.py#L312-L313) | ❌ | C | 2.2 | P1-02 |
| I-56 | Paper | A2 | Units and timestep are inconsistent (W/kW/kWh/Wh, $/Wh vs $/kWh). There is no explicit Δt | [der.py:L35](../../../src_thesis/marl/agents/der.py#L35)<br>[matching.py:L34-L37](../../../src_thesis/marketplace/market/matching.py#L34-L37) | ❓ | — | — | P1-11 |
| I-57 | Fidelity | A7 | IEEE-34 graph is disconnected (edge 832–888 missing), and the impedance table is unused | [config.py:L29-L39](../../../src_thesis/marketplace/grid/config.py#L29-L39)<br>[config.py:L43-L75](../../../src_thesis/marketplace/grid/config.py#L43-L75)<br>[network.py:L133](../../../src_thesis/adapters/grid/network.py#L133) | ❌ | T13 | 2.6 | P1-04 |
| I-58 | Code | C1 | The reset observation hard-codes G, D, remaining energy and KPIs to 0 | [observation.py:L195-L257](../../../src_thesis/marketplace/observation.py#L195-L257) | ⚠️ | — | 2.9 | P1-09 |
| I-59 | Code | D1 | Grouped obs/action tuples may be assigned to the wrong agents: insertion order vs sorted keys | [train.py:L646](../../../src_thesis/marl/train.py#L646)<br>[train.py:L681](../../../src_thesis/marl/train.py#L681)<br>[train.py:L702](../../../src_thesis/marl/train.py#L702) | ❌ | — | 2.12 | P0-10 |
| I-60 | Paper | D1 | CTCE is a centralized-information baseline, not a true upper bound. The group reward sum scales with N | [train.py:L684](../../../src_thesis/marl/train.py#L684) | ❓ | — | 2.12 | P1-12 |
| I-61 | Code | D2 | Standalone inference samples and clips actions itself instead of using RLlib's action path, and reads `info` wrongly | [inference.py:L146-L216](../../../src_thesis/marl/inference.py#L146-L216)<br>[inference.py:L235](../../../src_thesis/marl/inference.py#L235) | ❌ | — | — | P2-02 |
| I-62 | Code | D1 | Training config defects: positive `evaluation_duration` rejected, CPUs double-allocated, PBT always on, no `finally` around `ray.shutdown` | [train.py:L116](../../../src_thesis/marl/train.py#L116)<br>[train.py:L285-L294](../../../src_thesis/marl/train.py#L285-L294)<br>[train.py:L432](../../../src_thesis/marl/train.py#L432)<br>[train.py:L449-L458](../../../src_thesis/marl/train.py#L449-L458) | ⚠️ | — | 2.12 | P2-05 |
| I-63 | Code | D3 | The saved env config cannot reconstruct the scenario (seeds, profile sources, rounding) | [io.py:L111](../../../src_thesis/marketplace/io.py#L111)<br>[io.py:L145-L146](../../../src_thesis/marketplace/io.py#L145-L146)<br>[io.py:L55](../../../src_thesis/marketplace/io.py#L55) | ⚠️ | — | — | P2-04 |
| I-64 | Code | D3 | No run manifests, non-learning baselines or multi-seed statistics | [train.py:L439](../../../src_thesis/marl/train.py#L439)<br>[train.py:L391](../../../src_thesis/marl/train.py#L391) | ⚠️ | — | — | P2-06 |
| I-65 | Code | B2 | `src/analytics` reports welfare, grid and coordination concepts without the required inputs | [market_analytics.py:L123-L136](../../../src_thesis/cooperation/metrics/market_analytics.py#L123-L136) | ❌ | — | — | P1-08 |
| I-66 | Code | A10 | The block hash omits loss and fees, and blocks are forced every step (in-memory PoW, not consensus) | [validation.py:L25-L34](../../../src_thesis/marketplace/market/validation.py#L25-L34)<br>[matching.py:L410](../../../src_thesis/marketplace/market/matching.py#L410) | ⚠️ | — | 2.2 | P3-01 |
| I-67 | Code | D3 | README, notebooks and docs describe a different repository state | [README.md](../../../README.md)<br>tests.md (removed from this repo; see upstream `marlem-main`) | ⚠️ | — | — | P3-03 |
| I-68 | Paper | B1 | Imbalance (eq. 24) over trades is ≡ 0 by construction. Needs a definition over orders or physical net positions, and a timing (before or after DSO clearing) for `B_grid` | [implicit_cooperation.py:L122-L123](../../../src_thesis/cooperation/implicit_cooperation.py#L122-L123) | ❓ | — | 3 | — |
| I-69 | Paper | B1 | "DER self-consumption" is defined as P2P share; the label does not match the quantity | [implicit_cooperation.py:L188](../../../src_thesis/cooperation/implicit_cooperation.py#L188) | ⚠️ | — | 2.8 | P1-07 |
| I-70 | Paper | A7 | Grid physics scope: linear unbounded losses, `V_drop = f·d`, transport flows. "High-fidelity" is an overclaim | [network.py:L331-L348](../../../src_thesis/adapters/grid/network.py#L331-L348)<br>[dso.py:L326-L328](../../../src_thesis/marketplace/dso/dso.py#L326-L328) | ❓ | — | 3 | P1-04 |
| I-71 | Paper | A8 | Battery model has no charge/discharge power limit (claimed in the text), and eq. 15 ignores efficiency | [battery.py:L131-L176](../../../src_thesis/marl/agents/battery.py#L131-L176)<br>[battery.py:L205-L214](../../../src_thesis/marl/agents/battery.py#L205-L214) | ❓ | — | 2.5 | P0-06 |
| I-72 | Paper | D3 | [P2] protocol: one fixed seed, evaluation on the training scenario, ranking by shaped reward | [train.py:L275-L294](../../../src_thesis/marl/train.py#L275-L294)<br>[lem.py:L272-L274](../../../src_thesis/marketplace/lem.py#L272-L274) | ❓ | — | 3 | P2-01 |
| I-73 | Paper | D1 | Cross-paradigm return comparability: group sum vs per-agent returns | [train.py:L684](../../../src_thesis/marl/train.py#L684) | ❓ | — | 3 | P1-12 |
| I-74 | Paper | A6 | Thermal-fee threshold (20 %) sits below the congestion threshold (80 %) | [dso.py:L65-L67](../../../src_thesis/marketplace/dso/dso.py#L65-L67) | ⚠️ | — | 2.4 | — |
| I-75 | Paper | C2 | `f_coop` has no normalisation ranges for its unbounded KPIs, so the [0, 1] claim is unsupported | [reward.py:L170-L192](../../../src_thesis/marketplace/reward.py#L170-L192)<br>[implicit_cooperation.py:L93](../../../src_thesis/cooperation/implicit_cooperation.py#L93) | ❓ | — | 3 | P1-06 |
| I-76 | Paper | C2 | `R_base` components have no formulas in the paper; the code is the only specification | [reward.py:L148-L166](../../../src_thesis/marketplace/reward.py#L148-L166) | ❓ | — | 2.10 | — |
| I-77 | Fidelity | A3 | Rule-based partner selection is a lexicographic sort plus a random top-half pick, not a weighted score | [der.py:L136-L159](../../../src_thesis/marl/agents/der.py#L136-L159)<br>[lem.py:L362-L365](../../../src_thesis/marketplace/lem.py#L362-L365) | ⚠️ | C | 2.2 | — |
| I-78 | Fidelity | A1 | Invalid actions raise `ValueError` instead of being dropped (Alg. 1 `ValidateOrder`) | [lem.py:L342-L343](../../../src_thesis/marketplace/lem.py#L342-L343) | ⚠️ | C | 2.2 | — |
| I-79 | Fidelity | C2 | `f_contrib` grid term is a heuristic, not [P2]'s marginal `−∂\|B_grid\|/∂a_i` | [reward.py:L472-L484](../../../src_thesis/marketplace/reward.py#L472-L484) | ⚠️ | C | 2.10 | — |
| I-80 | Paper | D3 | [P2] evaluation metric `B_index` is undefined in the paper and absent from the code | — | ❓ | C | 2.12 | — |

## 7. Completeness check and readiness

**Coverage of the paper (fidelity).** Every numbered element was compared:

| Source | Items | Where |
|---|---|---|
| [P1] | §3.9 loop, Algorithm 1 | §1, §2.2 |
| [P1] | eq. 2, 15 | §2.1 |
| [P1] | eq. 9–11 | §2.3 |
| [P1] | eq. 7, 8a–8h | §2.4 |
| [P1] | eq. 13, 14, 16 | §2.5 |
| [P1] | eq. 18–20, zones, topologies | §2.6 |
| [P1] | eq. 12 | §2.7 |
| [P1] | eq. 21–27 | §2.8 |
| [P1] | Table 2 | §2.9 |
| [P1] | eq. 3–6 | §2.10 |
| [P1] | eq. 17, profiles | §2.11 |
| [P1] | §4 Case 5, zero-intelligence baseline | §2.12, §4 |
| [P2] | eq. 1–3 | §2.6, §2.10 |
| [P2] | KPI eq. 7–10 (same as [P1]) | §2.8 |
| [P2] | eq. 16–20 (paradigms) | §2.12 |
| [P2] | Tables 6–8, §4.2–4.3 | §2.12 |

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

1. **Paper-origin decisions are taken per step, just before that step, not all up front.** Each step in [marlem-validation-by-level.md](plan-by-level.md) lists the decisions it needs.
2. **Every decision is recorded** in the by-level plan (status `decided`, plus a one-line rule and reason) before code changes. A changed decision is a new version, not an edit.
3. **The thesis claim is "paper-faithful corrected reimplementation"** (§4), not reproduction.
4. **A new finding reopens a closed row only** if it shows a violated invariant, a paper contradiction not already listed, or a failed reproduction. A preference alone does not.
