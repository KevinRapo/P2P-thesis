# MARLEM: methodology in the papers and in the original code

> A condensed, implementation-oriented summary of the two MARLEM papers: the environment loop, every model component, and every equation, so the method can be checked without reading the PDFs.
> Each section first describes **what the papers say**. It then ends with an **"Implementation in the original code"** table: how the upstream code (identical in `src_thesis/`, links go to the exact lines) implements each element. This is the checklist for validating that the functional pieces work as stated. Issue IDs (I-xx) are links to their row in the register in [../thesis/validation/paper-vs-code.md §6](../thesis/validation/paper-vs-code.md#6-issue-register).
> Written: 2026-09-24. Formulas use LaTeX math (`$…$`, `$$…$$`). They render in the VS Code Markdown preview (Ctrl+Shift+V) and on GitHub.

**Sources**

- **[P1]** Salazar-Peña, Tabares, González-Mancera. *MARLEM: A multi-agent reinforcement learning simulation framework for implicit cooperation in decentralized local energy markets.* Applied Energy 412 (2026) 127546. [marlem.pdf](marlem.pdf). This paper defines the environment.
- **[P2]** Same authors. *Harnessing Implicit Cooperation: A Multi-Agent Reinforcement Learning Approach Towards Decentralized Local Energy Markets.* SSRN preprint. [marlem-results.pdf](marlem-results.pdf). This paper covers the MARL study (3 × 3 matrix, Case 6).

Equation numbers are the papers' own, e.g. [P1] (4). Equations garbled in the PDF text extraction were reconstructed from the surrounding text and are marked *(reconstructed)*.


**Implementation status at a glance** (original code vs papers; ✅ as stated · ⚠️ differs or is partial · ❌ contradicts the paper / broken · ❓ paper silent or ambiguous):

| Section | ✅ | ⚠️ | ❌ | ❓ |
|---|---|---|---|---|
| §2 formulation | 5 | 4 | 5 | 0 |
| §3 loop | 2 | 6 | 2 | 0 |
| §4 market | 9 | 4 | 6 | 5 |
| §5 agents | 2 | 4 | 5 | 1 |
| §6 grid | 7 | 1 | 4 | 0 |
| §7 KPIs | 6 | 1 | 2 | 1 |
| §8 reward | 5 | 2 | 5 | 2 |
| §9 paradigms | 3 | 1 | 1 | 0 |
| §10 algorithms | 3 | 0 | 0 | 0 |
| §11 experiments | 4 | 6 | 2 | 2 |
| **Total** | **46** | **29** | **32** | **11** |

**Notation**

| Symbol | Meaning |
|---|---|
| $i \in \mathcal{I}$ | DER agent (prosumer) |
| $t \in \{1,\dots,\tau\}$ | Trading period (time step) |
| $G_t,\ D_t$ | Generation and demand of an agent at $t$ |
| $E_{\text{bought},t},\ E_{\text{sold},t}$ | Energy bought and sold by an agent at $t$ |
| $p,\ q$ | Price and quantity (of an order or trade) |
| $p_{\text{FiT}},\ p_{\text{utility}}$ | DSO feed-in tariff (DSO buys) and utility price (DSO sells) |
| $C_{\text{nom}},\ SoC$ | Battery nominal capacity and state of charge |
| $\mathcal{G} = \langle \mathcal{V}, \xi \rangle$ | Grid graph: nodes $\mathcal{V}$, lines (edges) $\xi$ |
| $d_{ij}$ | Electrical distance between agents $i$ and $j$ (shortest path) |
| $\psi$ | Discount factor |

---

## 1. Architecture ([P1] §3.1, Fig. 2)

Three conceptual levels:

| Level | Content |
|---|---|
| **Level 0: Platform Marketplace** | Market Module (order matching, clearing, DSO, reputation, validation) and Grid Module (network, losses, congestion). Provides the physical and economic environment. |
| **Level 1: MARL Agents** | Self-interested DER agents with generation and demand profiles and an optional battery. Each learns a bidding policy from local observations. |
| **Level 2: Implicit Cooperation** | Not a controller. It is the emergent coordination produced by the design of observations (shared KPIs) and rewards (cooperation terms). Also measures it through KPIs. |

## 2. Problem formulation: Dec-POMDP ([P1] §3.2)

The LEM is a Dec-POMDP $\langle \mathcal{I}, \mathcal{S}, \mathcal{A}, \mathcal{P}, \mathcal{R}, \Omega, \mathcal{O} \rangle$:

- $\mathcal{I}$: agents; $\mathcal{S}$: states; $\mathcal{A} = \times_i \mathcal{A}_i$: joint action space; $\mathcal{P}(s' \mid s, \mathbf{a})$: transition function;
- $\mathcal{R}$: reward function; $\Omega = \times_i \Omega_i$: joint observation space; $\mathcal{O}(o \mid s, \mathbf{a})$: observation function.

**State** [P1] (1), never fully visible to any agent:

$$
s_t = \left\langle s_t^{\text{time}},\ s_t^{\text{market}},\ s_t^{\text{agents}},\ s_t^{\text{DSO}},\ s_t^{\text{grid}},\ s_t^{\text{history}} \right\rangle
$$

It contains the temporal state, the market state (all orders and trade histories), the private internal states of all agents, the DSO metrics (clearing outcomes), the grid state (congestion of all lines) and historical performance.

**Transition** $\mathcal{P}(s' \mid s, \mathbf{a})$: defined procedurally by the step method. Actions become orders, the market clears, agent and grid states are updated from the trades, and the clock advances. It is deterministic given the joint action.

### 2.1 Action ([P1] (2), §3.2.3)

$$
a_i = \left\langle p_{\text{bid}},\ q_{\text{bid}},\ \alpha,\ \beta \right\rangle
$$

| Component | Domain | Meaning |
|---|---|---|
| $p_{\text{bid}}$ | $[p_{\min}, p_{\max}]$ | Bid price |
| $q_{\text{bid}}$ | $[q_{\min}, q_{\max}]$ | Bid quantity |
| $\alpha$ | $\{0, 1\}$ | Order type: 0 = sell, 1 = buy |
| $\beta$ | $\{0, 1, \dots, \lvert\mathcal{I}\rvert + 1\}$ | Preferred trading partner index (the other agents, the DSO, or no preference) |

The action is continuous. Two constraint layers are applied:

1. $p_{\text{bid}}$ and $q_{\text{bid}}$ are clipped to the market bounds.
2. $q_{\text{bid}}$ is constrained for physical feasibility with the battery, using $q_{\text{sell,max}}$ and $q_{\text{buy,max}}$ from [P1] (15) (§5.2).

### 2.2 Observation ([P1] §3.2.2, Table 2)

Each agent receives a local observation $o_i$ made of three blocks. No agent sees another agent's private state except (optionally) the vector of all agents' reputations.

| Market signals (public) | Agent-specific signals (private) | Implicit cooperation KPIs (shared) |
|---|---|---|
| 1 Current step | 1 Energy generation (forecast) | 1 Social welfare |
| 2 Time of day | 2 Energy demand (forecast) | 2 Market liquidity |
| 3 Clearing price | 3 Cumulative demand satisfied | 3 Mean bid-ask spread |
| 4 Clearing volume | 4 Cumulative demand deferred | 4 Price volatility |
| 5 Grid balance | 5 Remaining demand | 5 Supply-demand imbalance |
| 6 DSO buy volume | 6 Cumulative supply satisfied | 6 Grid congestion |
| 7 DSO sell volume | 7 Cumulative supply deferred | 7 Coordination score |
| 8 DSO total volume | 8 Remaining supply | 8 Coordination convergence |
| 9 P2P volume | 9 Mean profit | 9 DER self-consumption |
| 10 DSO trade ratio | 10 Reputation | 10 Flexibility utilization |
| 11 Net grid import | 11 Battery energy level | |
| 12 DSO buy price | 12 Battery SoC | |
| 13 DSO sell price | 13 Battery available charge | |
| 14 Mean local price | 14 Battery available discharge | |
| 15 Price spread | 15 Battery cumulative charge | |
| 16 Local price advantage | 16 Battery cumulative discharge | |

That is $16 + 16 + 10 = 42$ values, plus $N$ reputations when partner preference is enabled. Generation and demand are *forecasts*; [P2] Table 7 sets a maximum forecast error of 30 %.

### Implementation in the original code (§2 formulation)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| State $s_t$ (1) | Not one object: spread over the `LocalEnergyMarket` attributes set in [lem.py:45-122](../../src_thesis/marketplace/lem.py#L45-L122). The paper describes it only conceptually. | ✅ | — |
| Transition, deterministic given the action | Global `np.random` is re-seeded in every reset; with a configured seed every episode is identical [lem.py:276-278](../../src_thesis/marketplace/lem.py#L276-L278). Order timestamps are random [lem.py:378-381](../../src_thesis/marketplace/lem.py#L378-L381). | ⚠️ | [I-03](../thesis/validation/paper-vs-code.md#I-03), [I-04](../thesis/validation/paper-vs-code.md#I-04) |
| Action $\langle p, q, \alpha, \beta \rangle$, continuous | Box $[p_{\min}, q_{\min}, 0, 0]$ to $[p_{\max}, \min(q_{\max}, \text{cap}), 1, N+1]$ [action.py:36-45](../../src_thesis/marketplace/action.py#L36-L45) | ✅ |  |
| $\beta$ includes "no preference" | Only reachable at the exact upper bound after `int()` [action.py:70-91](../../src_thesis/marketplace/action.py#L70-L91) | ⚠️ | [I-10](../thesis/validation/paper-vs-code.md#I-10) |
| Clip $p, q$ to market bounds | [lem.py:362-364](../../src_thesis/marketplace/lem.py#L362-L364) | ✅ |  |
| Physical feasibility (15) | Uses the *requested* $q$ minus $G$ or $D$, not (15) [der.py:202-234](../../src_thesis/marl/agents/der.py#L202-L234) | ❌ | [I-08](../thesis/validation/paper-vs-code.md#I-08) |
| $\alpha \in \{0,1\}$ | Feasibility treats any $\alpha > 0$ as buy [der.py:202](../../src_thesis/marl/agents/der.py#L202); the order uses $\alpha > 0.5$ [lem.py:366](../../src_thesis/marketplace/lem.py#L366) | ❌ | [I-09](../thesis/validation/paper-vs-code.md#I-09) |
| Observation: 42 values, Table 2 order | Bounds [observation.py:64-176](../../src_thesis/marketplace/observation.py#L64-L176), values [observation.py:260-364](../../src_thesis/marketplace/observation.py#L260-L364) | ✅ |  |
| Generation and demand are forecasts (30 % error) | True values; `max_error` is read but never used [lem.py:66-67](../../src_thesis/marketplace/lem.py#L66-L67) | ❌ | [I-39](../thesis/validation/paper-vs-code.md#I-39) |
| Remaining demand and supply | Exact sum of the true future profile [observation.py:342-345](../../src_thesis/marketplace/observation.py#L342-L345) | ⚠️ | [I-39](../thesis/validation/paper-vs-code.md#I-39) |
| Mean profit | Always 0 (profit is never updated) [observation.py:347](../../src_thesis/marketplace/observation.py#L347) | ❌ | [I-27](../thesis/validation/paper-vs-code.md#I-27) |
| Grid balance (market signal 5) | `dso.balance`, which stays 0 [observation.py:287](../../src_thesis/marketplace/observation.py#L287) | ❌ | [I-24](../thesis/validation/paper-vs-code.md#I-24) |
| Reset observation (not in paper) | Hard-codes $G$, $D$, remaining energy and KPIs to 0 [observation.py:196-258](../../src_thesis/marketplace/observation.py#L196-L258) | ⚠️ | [I-58](../thesis/validation/paper-vs-code.md#I-58) |
| Optional reputation vector | Appended when partner preference is on [observation.py:360-362](../../src_thesis/marketplace/observation.py#L360-L362) | ✅ |  |

## 3. Environment loop ([P1] §3.9, Fig. 4)

One trading period $t$ runs eight phases:

| # | Phase | Content |
|---|---|---|
| 1 | Action processing and validation | Limit each action by current generation, demand and battery state (physical). Then validate that price, quantity, type and partner fall within market bounds (rule-based). |
| 2 | Order creation and submission | Validated actions become formal orders. If the policy does not control the partner, a rule-based selection scores partners by reputation and grid distance. |
| 3 | Market clearing and trade execution | Three-stage clearing (§4): mutual preferences → double auction (with reputation) → DSO for the residual. Output: all executed trades and summary statistics. |
| 4 | Energy tracking and battery updates | Trades update each agent's physical state (energy tracking, battery SoC) and the grid state (balance, congestion). |
| 5 | Reward calculation and KPI updates | Compute all system KPIs from trades, agent states and grid conditions, then the reward of every agent (§8). |
| 6 | State transition | Advance the global state and the clock. Update states that depend on the full market outcome, such as financial balances and reputation scores. |
| 7 | Observation update | Build $o_{i,t+1}$ from the new state: private information, public market signals and the KPIs of phase 5. |
| 8 | Episode management | Check termination (reaching the maximum number of periods $\tau$). If not terminated, return observations and rewards and repeat for $t+1$. |

### Implementation in the original code (§3 loop)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| 1 Action processing: physical limit, then market validation | Same order: physical adjustment, then `is_valid_action`, then clip [lem.py:342-368](../../src_thesis/marketplace/lem.py#L342-L368). The physical limit itself is wrong (see §2). | ⚠️ | [I-08](../thesis/validation/paper-vs-code.md#I-08) |
| Invalid actions are rejected (Alg. 1) | Raises `ValueError` instead of dropping the order [lem.py:349-350](../../src_thesis/marketplace/lem.py#L349-L350) | ⚠️ | [I-78](../thesis/validation/paper-vs-code.md#I-78) |
| 2 Order creation, rule-based partner | [lem.py:370-391](../../src_thesis/marketplace/lem.py#L370-L391). Partner rule: sort by (−reputation, distance), random pick from the top half [der.py:140-163](../../src_thesis/marl/agents/der.py#L140-L163) | ⚠️ | [I-77](../thesis/validation/paper-vs-code.md#I-77) |
| 3 Market clearing | [matching.py:240-436](../../src_thesis/marketplace/market/matching.py#L240-L436); see §4 | ⚠️ |  |
| 4 Energy and battery update from trades | [lem.py:402-423](../../src_thesis/marketplace/lem.py#L402-L423). Battery sign is reversed (§5); grid flows are updated inside matching, stage 1 only (§6). | ❌ | [I-18](../thesis/validation/paper-vs-code.md#I-18), [I-32](../thesis/validation/paper-vs-code.md#I-32) |
| 5 KPIs, then reward | [lem.py:425-445](../../src_thesis/marketplace/lem.py#L425-L445) | ✅ | content: §7–8 |
| 6 Clock, balances, reputation | [lem.py:447-456](../../src_thesis/marketplace/lem.py#L447-L456). Balance = sold − bought; profit never updated. | ⚠️ | [I-26](../thesis/validation/paper-vs-code.md#I-26), [I-27](../thesis/validation/paper-vs-code.md#I-27) |
| 7 Observation from the new state | [lem.py:495-500](../../src_thesis/marketplace/lem.py#L495-L500) (KPIs recomputed) | ✅ |  |
| 8 Terminate at $\tau$ | Checked after the increment against `max_steps − 1`: **23 of 24** periods run, and the terminal flag never reaches the reward [lem.py:459-469](../../src_thesis/marketplace/lem.py#L459-L469) | ❌ | [I-01](../thesis/validation/paper-vs-code.md#I-01), [I-02](../thesis/validation/paper-vs-code.md#I-02) |
| Reset (not specified in the papers) | Regenerates profiles, draws the same random reputation for every agent, a random balance and a random initial SoC [lem.py:260-318](../../src_thesis/marketplace/lem.py#L260-L318) | ⚠️ | [I-05](../thesis/validation/paper-vs-code.md#I-05), [I-07](../thesis/validation/paper-vs-code.md#I-07) |

## 4. Market ([P1] §3.3)

### 4.1 Market operation workflow ([P1] Algorithm 1)

```text
Input: agents I, joint action {a_1 … a_I}, market state S_t
Output: executed trades, updated market state S_t′

Phase 1 — Order collection and validation
  O_t ← ∅
  for each agent i:
      o_i ← ActionToOrder(a_i)
      if ValidateOrder(o_i, S_t): O_t ← O_t ∪ {o_i}

Phase 2 — P2P market clearing
  trades_pref,  O_rem ← PreferenceMatch(O_t)        # Stage 1: mutual preferences
  trades_price, O_rem ← PriceMatch(O_rem)           # Stage 2: continuous double auction
  trades_P2P ← trades_pref ∪ trades_price
  for each trade in trades_P2P: UpdateAgentStates(trade)   # energy, profit for buyer and seller

Phase 3 — DSO clearing and finalization
  trades_DSO ← DSOClear(O_rem)                      # Stage 3: residual cleared by the DSO
  for each trade in trades_DSO: UpdateAgentStates(trade)
  trades_t ← trades_P2P ∪ trades_DSO
  ValidateBlock(trades_t)                           # simulated blockchain validation
  S_t′ ← UpdateMarketState(trades_t, S_t)           # prices, volumes, reputations
  G_{t+1} ← UpdateGridState(trades_t, G_t)          # congestion on the affected edges
return trades_t, S_t′
```

### 4.2 Three-stage matching ([P1] §3.3.2, Fig. 3)

| Stage | Rule |
|---|---|
| 1 Preference-based | Match agents that have *mutually* specified each other as preferred partners. Pre-arranged relationships take priority over the open market. |
| 2 Price-based (double auction) | Buys sorted by price descending, sells by price ascending. Trade every compatible pair with $p_{\text{bid}} \ge p_{\text{ask}}$. Reputation is the secondary sort key (tie-breaker). |
| 3 DSO clearing | The DSO buys all residual supply at $p_{\text{FiT}}$ and sells all residual demand at $p_{\text{utility}}$, guaranteeing clearing. The prices satisfy $p_{\text{FiT}} < p_{\text{P2P}} < p_{\text{utility}}$, which makes local trading attractive. |

### 4.3 Clearing (pricing) mechanisms ([P1] §3.3.3)

The P2P trade price $p_{ij}$ is set by a configurable mechanism.

**Average** [P1] (9):

$$
p_{ij} = \frac{p_{\text{buy}} + p_{\text{sell}}}{2}
$$

**Pay-as-bid (seller):** $p_{ij} = p_{\text{seller}}$.

**Pay-as-offer (buyer):** $p_{ij} = p_{\text{buyer}}$. This favours the seller, since $p_{\text{buy}} \ge p_{\text{sell}}$.

**Nash bargaining** [P1] (10), an equal split of the surplus:

$$
p_{ij} = p_{\text{sell}} + \frac{p_{\text{buy}} - p_{\text{sell}}}{2}
$$

**Proportional surplus** [P1] (11) *(reconstructed)*: the surplus is split by each side's distance from a reference price $p_{\text{ref}}$:

$$
p_{ij} = p_{\text{sell}} + \frac{p_{\text{buy}} - p_{\text{ref}}}{(p_{\text{buy}} - p_{\text{ref}}) + (p_{\text{ref}} - p_{\text{sell}})} \cdot \left(p_{\text{buy}} - p_{\text{sell}}\right)
$$

The [P1] case study also uses a **bid-ask spread** mechanism, which is not defined in §3.3.3.

### 4.4 DSO: balance and fees ([P1] §3.3.1)

The DSO is the market maker of last resort and a proxy grid operator that collects grid fees.

**DSO balance** [P1] (7):

$$
B_{\text{DSO}} = \sum_{\text{trades}} \left( E_{\text{sold}} - E_{\text{bought}} \right)
$$

**Total fee for a trade** between $i$ and $j$ with quantity $q_{ij}$ and price $p_{ij}$ [P1] (8):

$$
F_{\text{total}} = F_{\text{cong}} + F_{\text{trans}} + F_{\text{imb}} + F_{\text{volt}} + F_{\text{thermal}} + F_{\text{zone}}
$$

$$
\begin{aligned}
F_{\text{cong}}    &= f_{\text{cong}} \,(C_t - C_{\text{threshold}})\, q_{ij}\, p_{ij} && \text{(8a)} \\
F_{\text{imb}}     &= f_{\text{imb}} \,\lvert B_{\text{impact}} \rvert\, q_{ij}\, p_{ij} && \text{(8b)} \\
F_{\text{volt}}    &= \min(V_{\text{drop}},\, V_{\text{threshold}})\, q_{ij}\, p_{ij} && \text{(8c)} \\
F_{\text{thermal}} &= \min(f_{\text{thermal}},\, f_{\text{threshold}})\, q_{ij}\, p_{ij} && \text{(8d)} \\
F_{\text{zone}}    &= -\, f_{\text{zone}}\, q_{ij}\, p_{ij} \quad \text{(same-zone bonus)} && \text{(8e)} \\
V_{\text{drop}}    &= f_{\text{volt}}\, d_{ij} && \text{(8f)} \\
f_{\text{thermal}} &= \frac{C_t - T_{\text{threshold}}}{1 - T_{\text{threshold}}} && \text{(8g)}
\end{aligned}
$$

$$
B_{\text{impact}} =
\begin{cases}
\ \ \min\!\left(\dfrac{q_{ij}}{\lvert B_{\text{grid}} \rvert},\, 1\right) & \text{DSO buying during excess supply / selling during excess demand} \\[2ex]
-\min\!\left(\dfrac{q_{ij}}{\lvert B_{\text{grid}} \rvert},\, 1\right) & \text{DSO buying during excess demand / selling during excess supply} \\[2ex]
\ \ 0 & \text{balanced grid}
\end{cases}
\qquad \text{(8h)}
$$

| Parameter | Meaning | Default in paper |
|---|---|---|
| $C_t \in [0,1]$ | Congestion level at $t$ | — |
| $C_{\text{threshold}}$ | Congestion intervention threshold | 0.8 (80 % utilization) |
| $V_{\text{threshold}}$ | Voltage-drop threshold | 0.05 (5 %) |
| $T_{\text{threshold}}$ | Thermal instability threshold | 0.2 (20 % utilization) |
| $B_{\text{grid}} \in [-1,1]$ | Grid balance ($>0$ excess supply, $<0$ excess demand) | — |
| $f_{\ast}$ | Configurable fee factors | not given |

$F_{\text{trans}}$ (usage per unit distance) is named in (8) but has **no formula** in the paper. Agents do not observe the topology; only the DSO computes distance fees and congestion.

### 4.5 Reputation and validation ([P1] §3.3.4)

**Reputation** $r_i \in [0,1]$ [P1] (12), updated after every trading period with a decay factor that weighs recent behaviour more:

$$
r_i = w_{\text{rel}}\, \delta_{\text{rel},i} + w_{\text{fair}}\, \delta_{\text{fair},i} + w_{\text{grid}}\, \delta_{\text{grid},i}
$$

- $\delta_{\text{rel}}$: reliability, the ratio of matched to total order volume;
- $\delta_{\text{fair}}$: price fairness, the deviation from the market clearing price;
- $\delta_{\text{grid}}$: grid contribution, whether trades alleviate or worsen grid stress.

The weights $w$ are not given. Reputation is the tie-breaker in the double auction.

**Decentralized validation.** After each period, all trades are hashed (SHA-256), aggregated into a block and validated with a simplified proof-of-work, then appended to an immutable ledger.

### Implementation in the original code (§4 market)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| Stage 1: mutual preferences | Orders preferring the DSO are first cleared **by the DSO**; then mutual P2P pairs, ranked by price gap [matching.py:607-752](../../src_thesis/marketplace/market/matching.py#L607-L752) | ❓ | [I-15](../thesis/validation/paper-vs-code.md#I-15) |
| Stage 2: double auction, reputation tie-break | Sort and tie-break as described [matching.py:293-294](../../src_thesis/marketplace/market/matching.py#L293-L294); loop [matching.py:286-379](../../src_thesis/marketplace/market/matching.py#L286-L379) | ✅ |  |
| Capacity handling in stage 2 | Checks the *current* balance against `max_quantity · N`, not grid capacity or the projected trade [matching.py:317-318](../../src_thesis/marketplace/market/matching.py#L317-L318) | ❌ | [I-55](../thesis/validation/paper-vs-code.md#I-55) |
| Stage 3: DSO clears the residual at $p_{\text{FiT}}$ / $p_{\text{utility}}$ | [dso.py:192-275](../../src_thesis/marketplace/dso/dso.py#L192-L275), with zero distance, loss and fee | ✅ | [I-54](../thesis/validation/paper-vs-code.md#I-54) |
| Submitted orders stay intact | Matching subtracts fills from the order objects [matching.py:370-371](../../src_thesis/marketplace/market/matching.py#L370-L371) and the DSO sets them to 0 [dso.py:215-256](../../src_thesis/marketplace/dso/dso.py#L215-L256), so the reward and KPIs see **0** | ❌ | [I-12](../thesis/validation/paper-vs-code.md#I-12) |
| Loss derates the delivered quantity | Buyer's residual drops by $q - l$ only, so the loss is re-bought from the DSO [matching.py:370](../../src_thesis/marketplace/market/matching.py#L370) | ⚠️ | [I-14](../thesis/validation/paper-vs-code.md#I-14) |
| Clearing price | Volume-weighted mean of **all** trades, DSO tariffs included [matching.py:410](../../src_thesis/marketplace/market/matching.py#L410) | ❓ | [I-16](../thesis/validation/paper-vs-code.md#I-16) |
| Average (9) | [mechanism.py:31-48](../../src_thesis/marketplace/market/mechanism.py#L31-L48) | ✅ |  |
| Pay-as-bid (seller) | Receives the buy order positionally, so it returns $p_{\text{buy}}$ [mechanism.py:70-85](../../src_thesis/marketplace/market/mechanism.py#L70-L85) | ❌ | [I-13](../thesis/validation/paper-vs-code.md#I-13) |
| Pay-as-offer (buyer) | [mechanism.py:51-66](../../src_thesis/marketplace/market/mechanism.py#L51-L66) | ✅ |  |
| Nash (10) | [mechanism.py:116-150](../../src_thesis/marketplace/market/mechanism.py#L116-L150) | ✅ |  |
| Proportional surplus (11) | [mechanism.py:153-192](../../src_thesis/marketplace/market/mechanism.py#L153-L192) | ✅ |  |
| Bid-ask spread | Receives the market price as its interpolation factor, so it returns $p_{\text{buy}}$ [mechanism.py:89-113](../../src_thesis/marketplace/market/mechanism.py#L89-L113) | ❌ | [I-17](../thesis/validation/paper-vs-code.md#I-17) |
| DSO balance (7) | Only changed by stage-1 DSO-preferred trades, carried across steps; stays 0 by default [matching.py:275-283](../../src_thesis/marketplace/market/matching.py#L275-L283), [matching.py:398](../../src_thesis/marketplace/market/matching.py#L398) | ❌ | [I-24](../thesis/validation/paper-vs-code.md#I-24), [I-25](../thesis/validation/paper-vs-code.md#I-25) |
| Fee (8), (8a), (8e) | [dso.py:277-353](../../src_thesis/marketplace/dso/dso.py#L277-L353); congestion and zone terms as printed | ✅ |  |
| $F_{\text{trans}}$ | Always 0 [dso.py:297](../../src_thesis/marketplace/dso/dso.py#L297) | ❓ | [I-29](../thesis/validation/paper-vs-code.md#I-29) |
| $F_{\text{volt}}$ (8c), $F_{\text{thermal}}$ (8d) | Voltage fee only when $V_{\text{drop}} > 0.05$, then $\min(0.2, V_{\text{drop}})$; thermal $\min(0.3, \cdot)$ [dso.py:329-339](../../src_thesis/marketplace/dso/dso.py#L329-L339) | ⚠️ | [I-30](../thesis/validation/paper-vs-code.md#I-30) |
| $F_{\text{imb}}$ (8b), $B_{\text{impact}}$ (8h) | Impact as in (8h) [dso.py:403-451](../../src_thesis/marketplace/dso/dso.py#L403-L451), fee only when negative [dso.py:343-346](../../src_thesis/marketplace/dso/dso.py#L343-L346); effectively always 0 | ⚠️ | [I-31](../thesis/validation/paper-vs-code.md#I-31) |
| Fees are paid | Stored on the trade and summed in `dso.fees`, **never charged** to anyone [dso.py:350-351](../../src_thesis/marketplace/dso/dso.py#L350-L351) | ❌ | [I-28](../thesis/validation/paper-vs-code.md#I-28) |
| Default thresholds 0.8 / 0.05 / 0.2 | [dso.py:66-75](../../src_thesis/marketplace/dso/dso.py#L66-L75) | ✅ |  |
| Reputation (12) | [reputation.py:103-163](../../src_thesis/marketplace/market/reputation.py#L103-L163); weights 0.3 / 0.2 / 0.5 [reputation.py:24-26](../../src_thesis/marketplace/market/reputation.py#L24-L26) | ❓ | weights not in paper |
| Reliability, grid contribution | Reliability ≡ 1 (unmatched list always empty) [reputation.py:132](../../src_thesis/marketplace/market/reputation.py#L132); grid term neutral because balance is 0 [reputation.py:142-156](../../src_thesis/marketplace/market/reputation.py#L142-L156) | ⚠️ | [I-38](../thesis/validation/paper-vs-code.md#I-38) |
| Decay factor | $r \leftarrow t_{\text{day}} \cdot r_{\text{old}} + (1 - t_{\text{day}}) \cdot r_{\text{new}}$ [reputation.py:89](../../src_thesis/marketplace/market/reputation.py#L89) | ❓ | [I-38](../thesis/validation/paper-vs-code.md#I-38) |
| SHA-256 block + proof-of-work per period | [matching.py:415-422](../../src_thesis/marketplace/market/matching.py#L415-L422), [validation.py:26-35](../../src_thesis/marketplace/market/validation.py#L26-L35); the hash omits loss and fees | ✅ | [I-66](../thesis/validation/paper-vs-code.md#I-66) |

## 5. Agents ([P1] §3.4)

### 5.1 State and accounting

Each agent has an ID, a grid location, forecast profiles $G_t$ and $D_t$, a balance, profit, reputation, and cumulative demand satisfied and deferred.

**Balance** [P1] (13); positive means surplus, negative means deficit:

$$
B_t = (G_t - D_t) + (E_{\text{bought},t} - E_{\text{sold},t})
$$

**Profit** [P1] (14):

$$
\text{profit}_{t+1} = \text{profit}_t + \sum_{\text{trades}} \left( p_{\text{sell}}\, q_{\text{sell}} - p_{\text{buy}}\, q_{\text{buy}} \right)
$$

**Partner selection:** learned through $\beta$, or, if not RL-controlled, rule-based. The rule-based variant uses a weighted score of high reputation and short grid distance.

### 5.2 Physical feasibility ([P1] (15))

Before an order is submitted, the requested quantity is constrained by:

$$
\begin{aligned}
q_{\text{sell,max}} &= \max(0,\, G_t - D_t) + E_{\text{dischargeable}} && \text{(15a)} \\
q_{\text{buy,max}}  &= \max(0,\, D_t - G_t) + E_{\text{chargeable}}    && \text{(15b)} \\
E_{\text{dischargeable}} &= (SoC_t - SoC_{\min})\, C_{\text{nom}}     && \text{(15c)} \\
E_{\text{chargeable}}    &= (SoC_{\max} - SoC_t)\, C_{\text{nom}}     && \text{(15d)}
\end{aligned}
$$

### 5.3 Battery ([P1] (16))

Parameters: $C_{\text{nom}}$, $SoC_{\min}$, $SoC_{\max}$, $\eta_{\text{charge}} \in [0,1]$, $\eta_{\text{discharge}} \in [0,1]$. The energy stays within $SoC_{\min} C_{\text{nom}} \le E_{\text{bat},t} \le SoC_{\max} C_{\text{nom}}$ and evolves with the net flow from the agent's balance and trades:

$$
E_{\text{bat},t+1} =
\begin{cases}
\min\!\left(E_{\text{bat},t} + E_{\text{in}}\, \eta_{\text{charge}},\ SoC_{\max}\, C_{\text{nom}}\right) & \text{charging with } E_{\text{in}} \\[1.5ex]
\max\!\left(E_{\text{bat},t} - \dfrac{E_{\text{out}}}{\eta_{\text{discharge}}},\ SoC_{\min}\, C_{\text{nom}}\right) & \text{delivering } E_{\text{out}}
\end{cases}
$$

Discharging depletes storage by *more* than the delivered energy. The text says the operations are also bound by "maximum charge/discharge rates", but no rate appears in (16).

### 5.4 Profiles ([P1] §3.4.4)

Profiles are loaded from files (real data) or generated procedurally, then smoothed.

**Generation** [P1] (17), solar PV:

$$
G_t = C_{\text{gen},i}\, I_t\, \left(1 + \varepsilon_{\text{noise}} + \varepsilon_{\text{cloud}}\right)
$$

$C_{\text{gen},i}$ is the nominal capacity (PV plus battery). $I_t$ is irradiance, a Gaussian centred at noon. $\varepsilon_{\text{noise}}$ is random noise. $\varepsilon_{\text{cloud}}$ is correlated cloud-cover variation.

**Demand:** a typical pattern with morning and evening peaks, which creates the temporal mismatch with solar generation.

**DSO prices:** $p_{\text{FiT}}$ and $p_{\text{utility}}$ are step functions with higher prices at peak hours, generated by the same algorithm, always with $p_{\text{utility}} > p_{\text{FiT}}$, and smoothed.

### Implementation in the original code (§5 agents)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| Balance (13) | `agent.balance = sold − bought` [lem.py:455](../../src_thesis/marketplace/lem.py#L455), [matching.py:453-472](../../src_thesis/marketplace/market/matching.py#L453-L472): no $G - D$, opposite sign | ⚠️ | [I-26](../thesis/validation/paper-vs-code.md#I-26) |
| Profit (14) | Initialised and reset, **never updated** [der.py:63](../../src_thesis/marl/agents/der.py#L63), [der.py:112](../../src_thesis/marl/agents/der.py#L112) | ❌ | [I-27](../thesis/validation/paper-vs-code.md#I-27) |
| Feasibility (15) | Uses the requested quantity, not (15) [der.py:202-234](../../src_thesis/marl/agents/der.py#L202-L234); see §2 | ❌ | [I-08](../thesis/validation/paper-vs-code.md#I-08) |
| Battery charging (16) | $E + E_{\text{in}}\,\eta$ ✓, but a charge that would reach $SoC_{\max}$ is refused entirely [battery.py:96-159](../../src_thesis/marl/agents/battery.py#L96-L159) | ❌ | [I-19](../thesis/validation/paper-vs-code.md#I-19) |
| Battery discharging (16) | Stored energy drops by $E_{\text{out}} \cdot \eta$ instead of $E_{\text{out}} / \eta$ [battery.py:162-180](../../src_thesis/marl/agents/battery.py#L162-L180) | ❌ | [I-20](../thesis/validation/paper-vs-code.md#I-20) |
| Battery dispatch from the balance | Trade term has the wrong sign: selling **charges** the battery [der.py:302-314](../../src_thesis/marl/agents/der.py#L302-L314) | ❌ | [I-18](../thesis/validation/paper-vs-code.md#I-18) |
| Charge/discharge rate limits (text) | None in [battery.py:134-187](../../src_thesis/marl/agents/battery.py#L134-L187) (the paper's equation has none either) | ❓ | [I-71](../thesis/validation/paper-vs-code.md#I-71) |
| Demand satisfied / deferred | Ignores battery discharge [der.py:258-270](../../src_thesis/marl/agents/der.py#L258-L270) | ⚠️ | [I-21](../thesis/validation/paper-vs-code.md#I-21) |
| Generation (17), multiplicative noise | Additive $(\text{base} + \text{noise} + \text{cloud}) \cdot C$, Gaussian at noon [der.py:174-200](../../src_thesis/adapters/profiles/der.py#L174-L200) | ⚠️ | [I-06](../thesis/validation/paper-vs-code.md#I-06) |
| Profiles from files | Random CSV column and random scale per reset [base.py:32-44](../../src_thesis/adapters/profiles/base.py#L32-L44), [der.py:120-132](../../src_thesis/adapters/profiles/der.py#L120-L132) | ⚠️ | [I-06](../thesis/validation/paper-vs-code.md#I-06) |
| Demand pattern, smoothing | [der.py:207](../../src_thesis/adapters/profiles/der.py#L207), [base.py:46](../../src_thesis/adapters/profiles/base.py#L46) | ✅ |  |
| DSO step prices, $p_{\text{utility}} > p_{\text{FiT}}$ | [dso.py:219](../../src_thesis/adapters/profiles/dso.py#L219), [dso.py:279](../../src_thesis/adapters/profiles/dso.py#L279), [dso.py:99](../../src_thesis/adapters/profiles/dso.py#L99) | ✅ |  |

## 6. Grid ([P1] §3.5)

### 6.1 Topology

The network is a weighted undirected graph $\mathcal{G} = \langle \mathcal{V}, \xi \rangle$ with agents at nodes.

- **Predefined topologies:** IEEE 13-node and IEEE 34-node feeders.
- **Procedural topologies:** mesh, ring and line.

The electrical distance $d_{ij}$ is the **shortest-path length** through the graph, not a Euclidean distance.

**Zones** ([P1] §3.5.4): the graph can be partitioned into connected zones $\mathcal{Z} = \langle \mathcal{V}, \xi \rangle \subseteq \mathcal{G}$. By default a same-zone trade gets a bonus (the negative fee $F_{\text{zone}}$); cross-zone trades can carry extra fees or constraints.

### 6.2 Constraints

**Transmission losses** [P1] (18), linear, with loss factor $\kappa$. The loss derates the delivered quantity and is included in the DSO fees:

$$
l_{ij} = d_{ij}\, q_{ij}\, \kappa
$$

**Congestion** [P1] (19). Total grid capacity is distributed over the edges, with more capacity for shorter (lower-impedance) edges. The congestion of edge $e$ is:

$$
\zeta_e = \frac{F_e}{\max(C_e)}
$$

### 6.3 State updates ([P1] §3.5.3)

**Power-flow update:** after each period, for every executed trade, find the shortest path between buyer and seller, then increase the flow $F_e$ on every edge of that path by $q_{ij}$ (considering losses). Trades that would violate capacity "can be penalized or disallowed by the DSO".

**Grid balance** [P1] (20); close to 0 means a self-sufficient market:

$$
B_{\text{grid}} = \sum_{i \in \mathcal{I}} \left( G_i - D_i + E_{\text{bought},i} - E_{\text{sold},i} \right)
$$

**Mean congestion**, used as the observed KPI [P2] (2):

$$
\bar{\zeta} = \frac{1}{\lvert \xi \rvert} \sum_{e \in \xi} \frac{F_e}{\max(C_e)}
$$

### Implementation in the original code (§6 grid)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| Topologies IEEE 13/34, mesh, ring, line | [network.py:113-226](../../src_thesis/adapters/grid/network.py#L113-L226) | ✅ |  |
| IEEE-34 feeder | Edge 832–888 missing (graph disconnected); impedance table unused [config.py:30-40](../../src_thesis/marketplace/grid/config.py#L30-L40) | ❌ | [I-57](../thesis/validation/paper-vs-code.md#I-57) |
| Shortest-path distance $d_{ij}$ | [base.py:34-58](../../src_thesis/marketplace/grid/base.py#L34-L58); falls back to Euclidean on any error | ✅ | [I-53](../thesis/validation/paper-vs-code.md#I-53) |
| Zones, same-zone bonus | [dso.py:321-323](../../src_thesis/marketplace/dso/dso.py#L321-L323) | ✅ |  |
| Loss (18) | $d \cdot q \cdot 0.03$, κ hard-coded [network.py:338-355](../../src_thesis/adapters/grid/network.py#L338-L355) | ✅ | [I-34](../thesis/validation/paper-vs-code.md#I-34) |
| Edge capacity by inverse length | [network.py:69-83](../../src_thesis/adapters/grid/network.py#L69-L83) | ✅ |  |
| Congestion (19) | [network.py:357-381](../../src_thesis/adapters/grid/network.py#L357-L381) | ✅ |  |
| Flow update for every executed trade | Only **stage-1** trades update flows [matching.py:603](../../src_thesis/marketplace/market/matching.py#L603) | ❌ | [I-32](../thesis/validation/paper-vs-code.md#I-32) |
| Flow per period | Flows start at a random 0–30 % and **accumulate** over the episode, capped at capacity [network.py:87](../../src_thesis/adapters/grid/network.py#L87), [network.py:330](../../src_thesis/adapters/grid/network.py#L330) | ❌ | [I-33](../thesis/validation/paper-vs-code.md#I-33) |
| Violations penalized or disallowed | Silently capped at edge capacity; no penalty or rejection [network.py:330](../../src_thesis/adapters/grid/network.py#L330) | ⚠️ | [I-33](../thesis/validation/paper-vs-code.md#I-33) |
| Grid balance (20) | Never computed; the observation uses `dso.balance` [lem.py:489](../../src_thesis/marketplace/lem.py#L489) | ❌ | [I-23](../thesis/validation/paper-vs-code.md#I-23) |
| Mean congestion $\bar\zeta$ | [network.py:412-431](../../src_thesis/adapters/grid/network.py#L412-L431) | ✅ |  |

## 7. Implicit-cooperation KPIs ([P1] §3.6, [P2] §3.2)

The KPIs are computed at the end of every period. They are **injected both into observations** (shared signals) **and into the reward** ($f_{\text{coop}}$, $f_{\text{contrib}}$). [P1] numbers them (21)–(27); [P2] numbers them (4)–(10).

**Economic efficiency**

$$
\text{Social Welfare} = \sum_{\text{trades}} p_{\text{trade}}\, q_{\text{trade}} \qquad \text{(21)}
$$

The text describes this as "the sum of consumer and producer surplus".

$$
\text{Liquidity} = \sum_{\text{trades}} q_{\text{trade}} \qquad \text{(22)}
$$

$$
\text{Spread} = \mathbb{E}[p_{\text{ask}}] - \mathbb{E}[p_{\text{bid}}] \qquad \text{(23)}
$$

This is the average difference between buy and sell order prices. **Price volatility** is the standard deviation of the clearing price over a time window.

**Grid stability**

$$
\text{Imbalance} = \frac{\left\lvert \sum q_{\text{buy}} - \sum q_{\text{sell}} \right\rvert}{C_{\text{grid}}} \qquad \text{(24)}
$$

**Grid congestion** is the mean congestion $\bar{\zeta}$ over all lines. **Grid balance** is $B_{\text{grid}}$ from (20).

**Resource coordination**

$$
\text{Self-Consumption} = \frac{\sum q_{\text{P2P}}}{\sum q_{\text{P2P}} + \sum q_{\text{DSO}}} \qquad \text{(25)}
$$

$$
\text{Flexibility Utilization} = \frac{\sum q_{\text{P2P}}}{q_{\text{available}}} \qquad \text{(26)}
$$

$q_{\text{available}}$ is the total sellable flexibility (surplus generation plus battery discharge capacity) plus the buyable flexibility (deficit demand plus battery charge capacity).

**Coordination effectiveness**

$$
\text{Coordination Score} = 1 - \text{Imbalance} \qquad \text{(27)}
$$

**Coordination convergence** is the stability of trading volumes over a recent window, computed like price volatility.

### Implementation in the original code (§7 KPIs)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| Social welfare (21) | $\sum p\,\lvert q\rvert$ as printed (turnover, unnormalised) [implicit_cooperation.py:95](../../src_thesis/cooperation/implicit_cooperation.py#L95) | ❓ | [I-36](../thesis/validation/paper-vs-code.md#I-36) |
| Liquidity (22) | [implicit_cooperation.py:98](../../src_thesis/cooperation/implicit_cooperation.py#L98) | ✅ |  |
| Spread (23) | [implicit_cooperation.py:101-103](../../src_thesis/cooperation/implicit_cooperation.py#L101-L103) | ✅ |  |
| Price volatility over a window | Over the whole episode so far [implicit_cooperation.py:107-108](../../src_thesis/cooperation/implicit_cooperation.py#L107-L108) | ⚠️ | [I-37](../thesis/validation/paper-vs-code.md#I-37) |
| Imbalance (24) | $\lvert \sum_{\text{trades}} q \rvert / C$ = total volume, not buy − sell [implicit_cooperation.py:127-128](../../src_thesis/cooperation/implicit_cooperation.py#L127-L128) | ❌ | [I-35](../thesis/validation/paper-vs-code.md#I-35), [I-68](../thesis/validation/paper-vs-code.md#I-68) |
| Grid congestion | [implicit_cooperation.py:131](../../src_thesis/cooperation/implicit_cooperation.py#L131) | ✅ |  |
| Coordination score (27) | $1 -$ the volume-based imbalance [implicit_cooperation.py:147-148](../../src_thesis/cooperation/implicit_cooperation.py#L147-L148) | ❌ | [I-35](../thesis/validation/paper-vs-code.md#I-35) |
| Coordination convergence | $1 - \sigma/\mu$ of the last 3 clearing volumes [implicit_cooperation.py:151-157](../../src_thesis/cooperation/implicit_cooperation.py#L151-L157) | ✅ |  |
| Self-consumption (25) | [implicit_cooperation.py:195](../../src_thesis/cooperation/implicit_cooperation.py#L195) | ✅ | [I-69](../thesis/validation/paper-vs-code.md#I-69) (label) |
| Flexibility utilization (26) | [implicit_cooperation.py:197-230](../../src_thesis/cooperation/implicit_cooperation.py#L197-L230) | ✅ |  |

## 8. Reward ([P1] §3.2.4)

**Final reward** [P1] (3): sign-preserving log compression of the raw reward:

$$
R_i = \operatorname{sign}(r_{\text{raw}}) \cdot \ln\!\left(1 + \frac{\lvert r_{\text{raw}} \rvert}{20}\right) \cdot 20
$$

**Raw reward** [P1] (4), as printed:

$$
r_{\text{raw}} = R_{\text{base},i} \left( 1 + \frac{\ln\!\left(1 + \max\left(0,\ f_{\text{coop}}\, f_{\text{contrib},i} - 1\right)\right)}{5} \right) - \gamma_{\text{DSO},i} - \gamma_{\text{UD},i}
$$

[P2] (3) states the same structure without the log term:

$$
R_i = R_{\text{base},i} \left(1 + f_{\text{coop}}\, f_{\text{contrib},i}\right) - \gamma_{\text{DSO},i} - \gamma_{\text{UD},i}
$$

#### Which version the original code implements

Upstream MARLEM, unchanged in [reward.py `calculate_reward`](../../src_thesis/marketplace/reward.py#L103). This note is about the code, not the paper.

**Cooperation boost:** the code uses **neither** printed form exactly. It applies the [P1] log structure but **without the $-1$** ([reward.py:218-221](../../src_thesis/marketplace/reward.py#L218-L221)). It computes `cooperation_boost = 1 + f_coop·f_contrib`, then `log1p(max(0, cooperation_boost − 1))`, which equals $\ln(1 + f_{\text{coop}} f_{\text{contrib},i})$:

$$
r_{\text{raw}}^{\text{code}} = R_{\text{base},i} \left( 1 + \frac{\ln\!\left(1 + f_{\text{coop}}\, f_{\text{contrib},i}\right)}{5} \right) - s \cdot \gamma_{\text{DSO},i} - \frac{s}{p_{\text{dso}}} \cdot \gamma_{\text{UD},i}, \qquad s = 0.3 \cdot \max\!\left(\lvert R_{\text{base},i}\,(1 + \ln(1 + f_{\text{coop}} f_{\text{contrib},i})/5) \rvert,\ 1\right)
$$

**Penalty terms in the code:**

- $s$ scales the penalties by 0.3 × the magnitude of the boosted base reward. This is the paper's "implicit scaling" ([reward.py:224-229](../../src_thesis/marketplace/reward.py#L224-L229)).
- $\gamma_{\text{DSO},i} = \text{dso\_ratio}_i \cdot p_{\text{dso}} \cdot \lvert B_{\text{DSO}} \rvert / C_{\text{grid}}$, where $\text{dso\_ratio}_i$ is the agent's DSO volume over its total traded volume ([reward.py:201-202](../../src_thesis/marketplace/reward.py#L201-L202)).
- $\gamma_{\text{UD},i} = p_{\text{dso}} \cdot (\text{unmet demand} / \text{total demand})^2$, **only at the terminal step** ([reward.py:207-214](../../src_thesis/marketplace/reward.py#L207-L214)). It uses $p_{\text{dso}} = 15$, which the $/p_{\text{dso}}$ scaling above cancels. The paper's $p_{\text{no\_trades}} = 5$ is not used here.

**Final compression:** the same as [P1] (3) ([reward.py:232](../../src_thesis/marketplace/reward.py#L232)).

**Extra rule not in either paper:** an agent with **no trades** in the step returns a fixed $R_i = -20 \ln(1 + 5/20) \approx -4.46$ before any other term is computed ([reward.py:135-136](../../src_thesis/marketplace/reward.py#L135-L136)). This is where $p_{\text{no\_trades}} = 5$ is used.

**Base reward:** a weighted sum of normalized components:

$$
R_{\text{base},i} = \sum_k w_k\, r_{k,i}
$$

| Component | Weight $w_k$ | Description (paper) | Range |
|---|---|---|---|
| Grid balance $r_{\text{grid}}$ | 10.0 | Rewards actions that reduce grid imbalance (e.g., buying during surplus). Contribution score normalized by grid capacity plus a penalty for increasing imbalance. | $[-1, 2]$ |
| Resource allocation $r_{\text{res}}$ | 1.5 | Execution ratio minus a penalty for the unexecuted portion | $[-1.5, 1]$ |
| Trading success $r_{\text{trade}}$ | 5.0 | $0.3\,\rho_{\text{local}} + 0.3\,\rho_{\text{dso}}$, with $\rho$ the fill rate of local and DSO trades | $[0, 0.6]$ |
| Stability $r_{\text{stab}}$ | 2.0 | Price stability ($w = 0.3$) + grid improvement ($w = 0.7$) | $[0, 1]$ |
| Economic efficiency $r_{\text{econ}}$ | 3.0 | Price efficiency vs the clearing price ($w = 0.4$) + profit relative to DSO prices ($w = 0.6$) | $[0, 1]$ |

Grid balance is the dominant weight by design. The paper gives no formulas beyond these descriptions.

**Cooperation factor** [P1] (5): a market-wide factor that scales the base reward:

$$
f_{\text{coop}} = \frac{1}{w_{\text{coop}}} \sum_{k} f_k\, \tilde{k}, \qquad w_{\text{coop}} = \sum_k f_k = 56.0, \qquad \tilde{k} = \begin{cases} 1 - k & \text{if lower is better} \\ k & \text{otherwise} \end{cases}
$$

The sum runs over the 10 KPIs of §7, normalized. Price volatility and grid congestion are examples of "lower is better" KPIs. The stated weights are congestion $f = 9.0$, supply-demand imbalance $f = 10.0$ and social welfare $f = 7.0$; the remaining weights are not listed. The paper states $f_{\text{coop}} \in [0,1]$.

**Contribution factor** [P1] (6): the agent's own contribution, in $[0,1]$:

$$
f_{\text{contrib},i} = 0.5\, r_{\text{grid}} + 0.3\, r_{\text{share}} + 0.2\, r_{\text{dev}}
$$

- $r_{\text{grid}}$: 0.5 for a neutral action, rising towards 1.0 if the agent's trade reduces system imbalance, falling towards 0.0 if it worsens it. [P2] describes this as the agent's marginal contribution $-\,\partial \lvert B_{\text{grid}} \rvert / \partial a_i$.
- $r_{\text{share}}$: ratio of the agent's P2P trades to its total trades.
- $r_{\text{dev}}$: price efficiency, from the average relative deviation of the agent's trade prices from the clearing price.

**Penalties:**

| Penalty | Weight | Meaning |
|---|---|---|
| $\gamma_{\text{DSO},i}$ | $p_{\text{dso}} = 15.0$ | Reliance on the DSO. [P2]: scaled by the current grid imbalance, amplified during critical imbalance. |
| $\gamma_{\text{UD},i}$ | $p_{\text{no\_trades}} = 5.0$ | Unmet demand |

Penalties are "implicitly scaled relative to the reward magnitude" (no formula is given).

**Sensitivity (as reported):**

- $w_{\text{grid}}$ is effective in $[5, 15]$;
- $p_{\text{dso}}$ needs $[5, 25]$;
- the log scale 20 was chosen from $[10, 40]$.

### Implementation in the original code (§8 reward)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| Log compression (3) | [reward.py:232](../../src_thesis/marketplace/reward.py#L232) | ✅ |  |
| Cooperation boost (4) | No $-1$ (see the note above) [reward.py:218-221](../../src_thesis/marketplace/reward.py#L218-L221) | ❓ | [I-42](../thesis/validation/paper-vs-code.md#I-42) |
| Base weights 10 / 1.5 / 5 / 2 / 3 | [reward.py:51-56](../../src_thesis/marketplace/reward.py#L51-L56) | ✅ |  |
| $f_{\text{coop}}$ weights (paper: 3 of 10) | All 10 in code: welfare 7, liquidity 1.5, spread 1.5, volatility 3, coordination 5, imbalance 10, congestion 9, convergence 8, self-consumption 5, flexibility 6 (Σ = 56) [reward.py:59-68](../../src_thesis/marketplace/reward.py#L59-L68) | ✅ |  |
| $f_{\text{coop}} \in [0,1]$ | Unnormalised KPIs are averaged, ≈ **1800** in practice [reward.py:170-192](../../src_thesis/marketplace/reward.py#L170-L192) | ❌ | [I-41](../thesis/validation/paper-vs-code.md#I-41), [I-75](../thesis/validation/paper-vs-code.md#I-75) |
| $r_{\text{trade}} = 0.3\rho_{\text{local}} + 0.3\rho_{\text{dso}}$ | Matches, but only because `_w_local` 0.7 is overwritten with 0.3 [reward.py:79](../../src_thesis/marketplace/reward.py#L79), [reward.py:93](../../src_thesis/marketplace/reward.py#L93) | ⚠️ | [I-45](../thesis/validation/paper-vs-code.md#I-45) |
| $r_{\text{res}}$, $r_{\text{trade}}$ inputs | Divide by the mutated order quantity (0), so $r_{\text{res}} \equiv -1.5$, $r_{\text{trade}} \equiv 0$ [reward.py:248-249](../../src_thesis/marketplace/reward.py#L248-L249), [reward.py:406-412](../../src_thesis/marketplace/reward.py#L406-L412) | ❌ | [I-43](../thesis/validation/paper-vs-code.md#I-43) |
| $r_{\text{grid}}$ | [reward.py:253-309](../../src_thesis/marketplace/reward.py#L253-L309); driven by `dso.balance`, which stays 0 | ❌ | [I-44](../thesis/validation/paper-vs-code.md#I-44) |
| $r_{\text{stab}}$ 0.3 / 0.7 | [reward.py:414-446](../../src_thesis/marketplace/reward.py#L414-L446) | ✅ |  |
| $r_{\text{econ}}$ 0.4 / 0.6 | [reward.py:311-386](../../src_thesis/marketplace/reward.py#L311-L386) | ✅ |  |
| $f_{\text{contrib}}$ (6) 0.5 / 0.3 / 0.2 | [reward.py:448-499](../../src_thesis/marketplace/reward.py#L448-L499); share by *count* of trades; grid part is a heuristic, not $-\partial\lvert B\rvert/\partial a$ | ⚠️ | [I-79](../thesis/validation/paper-vs-code.md#I-79) |
| $\gamma_{\text{DSO}}$ | [reward.py:201-202](../../src_thesis/marketplace/reward.py#L201-L202); 0 while `dso.balance` is 0 | ❌ | [I-44](../thesis/validation/paper-vs-code.md#I-44) |
| $\gamma_{\text{UD}}$ | Terminal only, and the terminal flag never arrives [reward.py:207-214](../../src_thesis/marketplace/reward.py#L207-L214) | ❌ | [I-02](../thesis/validation/paper-vs-code.md#I-02), [I-46](../thesis/validation/paper-vs-code.md#I-46) |
| No-trade rule (not in paper) | Fixed −4.46 [reward.py:135-136](../../src_thesis/marketplace/reward.py#L135-L136) | ❓ | [I-47](../thesis/validation/paper-vs-code.md#I-47) |

## 9. MARL paradigms ([P1] §3.7.1, [P2] §3.4)

| Paradigm | Training | Execution | Objective |
|---|---|---|---|
| **CTCE** | One policy on the global state $s_t$ (concatenated observations) | Joint action for all agents | Global return, [P2] (17). Described as the theoretical upper bound / benchmark. |
| **CTDE** | Centralized critic $Q_\phi(s, \mathbf{a})$ on global state and joint action | Each agent's own actor $\pi_{\theta_i}(a_i \mid o_i)$ on its local observation; the critic is discarded | Actor gradient, [P2] (18) |
| **DTDE** | Independent actor and critic per agent on local $o_i$ and $a_i$ only | Local | Own return, [P2] (19) |

**CTCE policy** [P2] (16):

$$
\pi_\theta(a_{1,t}, \dots, a_{I,t} \mid s_t) = \prod_{i=1}^{I} \pi_{\theta,i}(a_{i,t} \mid s_t)
$$

**CTCE objective** [P2] (17):

$$
J_{\text{CTCE}}(\theta) = \mathbb{E}_{s \sim \rho^\pi,\ a \sim \pi_\theta} \left[ \sum_{t=0}^{\tau} \sum_{i=1}^{I} \psi^t\, R_i(s_t, a_t) \right]
$$

**CTDE actor gradient** [P2] (18):

$$
\nabla_{\theta_i} J(\theta_i) = \mathbb{E}_{s, a} \left[ \nabla_{\theta_i} \log \pi_{\theta_i}(a_i \mid o_i)\; Q_\phi(s, a_{1,t}, \dots, a_{I,t}) \right]
$$

**DTDE objective** [P2] (19):

$$
J_{\text{DTDE}}(\theta_i) = \mathbb{E}_{o_i, a_i} \left[ \sum_{t=0}^{\tau} \psi^t\, R_i(o_{i,t}, a_{i,t}) \right]
$$

**Non-stationarity seen by agent $i$** [P2] (20):

$$
P_i(s' \mid s, a_i) = \sum_{a_{-i} \in \mathcal{A}_{-i}} P(s' \mid s, a_i, a_{-i}) \prod_{j \ne i} \pi_j(a_j \mid o_j)
$$

The paper's claim is that injecting the KPIs into $o_i$ makes the DTDE environment "quasi-stationary": the KPIs summarise the other agents' aggregate effect.

### Implementation in the original code (§9 paradigms)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| DTDE: independent policy per agent | [train.py:337-354](../../src_thesis/marl/train.py#L337-L354) | ✅ |  |
| CTCE: one policy on concatenated observations | [train.py:314-323](../../src_thesis/marl/train.py#L314-L323), module [ctce.py:29-65](../../src_thesis/marl/ctce.py#L29-L65) | ✅ |  |
| Global return = Σ of agent rewards (17) | [train.py:698](../../src_thesis/marl/train.py#L698) | ✅ | [I-73](../thesis/validation/paper-vs-code.md#I-73) (scale) |
| CTDE: centralized critic, local actors | Trains a centralized `pi` on all observations [ctde.py:127-128](../../src_thesis/marl/ctde.py#L127-L128) but acts with per-agent `pi_heads` [ctde.py:76-89](../../src_thesis/marl/ctde.py#L76-L89) that are **never trained** | ❌ | [I-48](../thesis/validation/paper-vs-code.md#I-48) |
| Agent ordering in grouped modes | Grouping uses insertion order, spaces use sorted keys [train.py:657](../../src_thesis/marl/train.py#L657), [train.py:717](../../src_thesis/marl/train.py#L717) | ⚠️ | [I-59](../thesis/validation/paper-vs-code.md#I-59) |

## 10. Algorithms ([P2] §3.3)

**PPO** (on-policy). Clipped surrogate objective with GAE advantages; $\varepsilon$ is typically 0.2.

$$
J^{\text{CLIP}}(\theta_i) = \mathbb{E}_t \left[ \min\!\left( r_t(\theta_i)\, A_t,\ \operatorname{clip}\!\left(r_t(\theta_i),\, 1-\varepsilon,\, 1+\varepsilon\right) A_t \right) \right] \qquad \text{(11)}
$$

$$
r_t(\theta_i) = \frac{\pi_{\theta_i}(a_t \mid o_t)}{\pi_{\theta_{\text{old}}}(a_t \mid o_t)} \qquad \text{(12)}
$$

**APPO** (asynchronous actor–learner). V-trace off-policy correction:

$$
V_t^{\text{target}} = V(s_t) + \sum_{k=0}^{l-1} \psi^k \left( \prod_{j=0}^{k-1} c_{t+j} \right) \rho_{t+k}\, \delta_{t+k} \qquad \text{(13)}
$$

$$
\rho_t = \min\!\left( \bar{\rho},\ \frac{\pi_{\text{target}}(a_t \mid o_t)}{\pi_{\text{behavior}}(a_t \mid o_t)} \right) \qquad \text{(14)}
$$

$l$ is the trajectory segment length. $\delta$ is the TD error; the standard form is $\delta_t = r_t + \psi V(s_{t+1}) - V(s_t)$ *(reconstructed; not spelled out in the extraction)*.

**SAC** (off-policy, replay buffer). Maximum-entropy objective with temperature $\alpha$, twin Q-networks (the minimum is used for updates) and a reparameterized stochastic policy:

$$
J(\pi) = \sum_{t=0}^{\tau} \mathbb{E}_{(o_t, a_t) \sim \rho_\pi} \left[ r(o_t, a_t) + \alpha\, \mathcal{H}\!\left(\pi(\cdot \mid o_t)\right) \right] \qquad \text{(15)}
$$

### Implementation in the original code (§10 algorithms)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| PPO (11)–(12), GAE | RLlib PPO; clip 0.2, λ 0.95 [train.py:216-230](../../src_thesis/marl/train.py#L216-L230) | ✅ |  |
| APPO, V-trace (13)–(14) | RLlib APPO, `vtrace=True` [train.py:231-239](../../src_thesis/marl/train.py#L231-L239) | ✅ |  |
| SAC (15), twin Q, target entropy rule | RLlib SAC; target entropy −Σdim for CTCE/CTDE, −dim for DTDE [train.py:240-265](../../src_thesis/marl/train.py#L240-L265) | ✅ |  |

## 11. Experiments

### 11.1 [P1] case study: battery storage coordination (§4–5)

| Item | Value |
|---|---|
| Agents | 7, 24-hour daily cycle |
| Grid | Mesh topology, nominal capacity 1200 kW |
| Clearing | Bid-ask spread mechanism |
| Price / quantity range | 35–280 \$/MWh; 0.1–200 kWh |
| Generation | Base capacity 60 kW per agent (random variation) |
| Scenarios | (1) no battery; (2) strategic battery: battery ratios 0.5–1.2, 95 % efficiency, profiles designed for time-shifting (morning generation with storage vs evening demand) |
| Agents' policy | **Zero-intelligence**: uniform random bids within valid bounds that respect physical constraints. No MARL training in [P1]. |
| Reported | P2P price distribution, net grid imbalance and P2P trading ratio over 24 h, coordination score, trading-network plots |

### 11.2 [P2] Case 6: 3 × 3 MARL matrix (§4)

**Agents** ([P2] Table 6): 8 agents on IEEE-34 nodes. Every battery has 95 % charge/discharge efficiency and SoC limits of 5 %–95 %.

| Agent | Node | Capacity (kW) | Battery (kW) | Ratio | Role |
|---|---|---|---|---|---|
| Small industry | 840 | 180 | 108 | 0.6 | Continuous demand with morning peak; relies on stored energy |
| Community hospital | 890 | 170 | 85 | 0.5 | High morning demand, afternoon generation surplus |
| University campus | 844 | 140 | 98 | 0.7 | Bi-modal demand; moderate midday generation |
| Shopping mall | 816 | 130 | 78 | 0.6 | High afternoon/evening demand; sink for midday surplus |
| Residential complex | 800 | 80 | 64 | 0.8 | Dual-peak demand; relies on storage for the evening ramp |
| Apartment building | 830 | 75 | 52.5 | 0.7 | Like the residential complex; moderate generation |
| Community solar farm | 848 | 180 | 180 | 1.0 | High midday generation, minimal demand; flexibility provider |
| Parking lot | 860 | 160 | 144 | 0.9 | High midday generation; flexibility provider |

**Environment** ([P2] Table 7):

| Parameter | Value |
|---|---|
| Max steps | 24 (1 h per step) |
| Grid topology / capacity | IEEE 34-bus, 1800 kW |
| Seed | 42 (global; all stochastic processes) |
| Price range | 20–600 |
| Quantity range | 0–180 kWh |
| Forecast error | 30 % (max_error = 0.3) |
| Async orders | True |

DSO tariffs: time-varying feed-in tariff and utility price ([P2] Fig. 3).

**Hyperparameters** ([P2] Table 8, initial values; PBT mutates them):

| | PPO | APPO | SAC |
|---|---|---|---|
| Learning rate | $10^{-5}$ | $10^{-5}$ | actor $10^{-5}$, critic $10^{-5}$ |
| Discount $\psi$ | 0.99 | 0.99 | 0.99 |
| Entropy coefficient | 0.01 | 0.01 | dynamic (target entropy\*) |
| Gradient clip | 0.5 | 0.5 | 0.5 |
| Clip parameter | 0.2 | — | — |
| Advantage | GAE | V-trace | — |
| Batch / buffer | minibatch 128 | — | buffer capacity 1 000 |

\* SAC target entropy $= -\sum_i \dim(\mathcal{A}_i)$ for CTCE/CTDE, and $-\dim(\mathcal{A}_i)$ for DTDE.

**Training protocol** ([P2] §4.2):

- 3 paradigms × 3 algorithms = 9 configurations.
- Population-Based Training with 10 tune samples per configuration (90 concurrent trials). Weights of the best trials are cloned (exploit); hyperparameters of low performers are mutated (explore).
- 10 000 training episodes per configuration.
- Checkpoint every 10 iterations. Evaluation at every training iteration, with the number of evaluation episodes set automatically from the evaluation workers.
- Hardware: Ryzen 9 9900X (12 cores), 128 GB RAM, RTX 4090, Ubuntu 24.04, CUDA 13.
- Reported: all 9 runs converged before 300 episodes.

**Evaluation metrics** ([P2] §4.3):

| Metric | Definition |
|---|---|
| Coordination score | $1 - $ normalized imbalance. The core measure of success. |
| Grid balance index $B_{\text{index}}$ | "Incorporates transmission losses and external grid reliance". No formula is given. |
| P2P trade ratio | Share of P2P trades in total volume |
| Social welfare | Eq. (21) |
| Agent responsiveness | Correlation between system-level signals and agent actions over time |
| Price volatility, DER self-consumption | §7 |

**Scalability test:** the same environment with 1 000 episodes per run, 1 tune sample, the full 3 × 3 matrix, and agent counts in $\{2, 20, 34\}$ (34 is the node limit of IEEE-34). The measure is wall-clock time until convergence or 1 000 episodes.

### Implementation in the original code (§11 experiments)

| Paper | Original code | Status | Issue |
|---|---|---|---|
| [P1] Case 5 setup: mesh, 1200 kW, 35–280, 0.1–200 kWh, 60 kW base | All as stated; capacities $60 + U(-10, 15)$; demand scaled ×0.5 (not in paper); `max_error` 0.18 [case5_battery_coordination.ipynb](../../notebooks/case5_battery_coordination.ipynb) | ✅ |  |
| [P1] Case 5 bid-ask spread mechanism | Selected in [case5_battery_coordination.ipynb](../../notebooks/case5_battery_coordination.ipynb); broken: returns the buyer's price [mechanism.py:89-113](../../src_thesis/marketplace/market/mechanism.py#L89-L113) | ❌ | [I-17](../thesis/validation/paper-vs-code.md#I-17) |
| [P1] Case 5 scenarios: no battery vs strategic | [case5_battery_coordination.ipynb](../../notebooks/case5_battery_coordination.ipynb) defines more scenarios (small, large, mixed, efficiency variants) | ⚠️ |  |
| [P1] zero-intelligence agents | `action_space.sample()` in [case5_battery_coordination.ipynb](../../notebooks/case5_battery_coordination.ipynb), followed by the (wrong) feasibility step [der.py:165-241](../../src_thesis/marl/agents/der.py#L165-L241) | ⚠️ | [I-08](../thesis/validation/paper-vs-code.md#I-08) |
| [P2] Case 6 environment: IEEE-34, 1800 kW, seed 42, price 20–600, 30 % forecast error | As stated, but $q_{\min} = 0.1$ (paper 0) and the forecast error is unused [case6_implicit_cooperation.ipynb](../../notebooks/case6_implicit_cooperation.ipynb) | ⚠️ | [I-39](../thesis/validation/paper-vs-code.md#I-39) |
| [P2] Table 6 agents (8 roles, 75–180 kW, fixed IEEE-34 nodes) | **Different agents** in [case6_implicit_cooperation.ipynb](../../notebooks/case6_implicit_cooperation.ipynb): commercial/shopping/industrial/flexible, 150–400 kW, battery ratios 0.5–1.0; no `node_id`, so nodes are random [network.py:266-277](../../src_thesis/adapters/grid/network.py#L266-L277); profiles from a random CSV column [base.py:32-44](../../src_thesis/adapters/profiles/base.py#L32-L44) | ❌ | [I-51](../thesis/validation/paper-vs-code.md#I-51) |
| Mechanism and partner preference in Case 6 | Proportional surplus, partner preference **on**, PoW difficulty 2 in [case6_implicit_cooperation.ipynb](../../notebooks/case6_implicit_cooperation.ipynb) (the paper does not state these) | ❓ |  |
| Table 8 hyperparameters | [train.py:209-265](../../src_thesis/marl/train.py#L209-L265) | ✅ |  |
| PBT, 10 samples per configuration | [case6_implicit_cooperation.ipynb](../../notebooks/case6_implicit_cooperation.ipynb) uses `TUNE_SAMPLES = 100`; mutation lr domain $[10^{-4}, 10^{-2}]$ excludes the initial $10^{-5}$ [train.py:182-197](../../src_thesis/marl/train.py#L182-L197) | ⚠️ | [I-49](../thesis/validation/paper-vs-code.md#I-49) |
| 10 000 episodes | `TRAINING_EPISODES = 10000` in [case6_implicit_cooperation.ipynb](../../notebooks/case6_implicit_cooperation.ipynb) is passed as `iters`, the RLlib **iteration** stop criterion [train.py:449](../../src_thesis/marl/train.py#L449) | ⚠️ | [I-50](../thesis/validation/paper-vs-code.md#I-50) |
| 3 × 3 matrix | [case6_implicit_cooperation.ipynb](../../notebooks/case6_implicit_cooperation.ipynb) trains one `ALGO`/`MODE` pair per run; no 3 × 3 loop | ⚠️ |  |
| Evaluation every iteration, checkpoint every 10 | [train.py:290-299](../../src_thesis/marl/train.py#L290-L299); deterministic evaluation, same scenario as training | ✅ | [I-72](../thesis/validation/paper-vs-code.md#I-72) |
| Agent responsiveness | [coordination_metrics.py:416](../../src_thesis/cooperation/metrics/coordination_metrics.py#L416) | ✅ | [I-65](../thesis/validation/paper-vs-code.md#I-65) (unaudited) |
| Grid balance index $B_{\text{index}}$ | Not implemented anywhere in the code (and not defined in the paper) | ❓ | [I-80](../thesis/validation/paper-vs-code.md#I-80) |

## 12. Points the papers leave unspecified

These are needed to implement the method but are not defined in either paper:

- The formulas of the five $R_{\text{base}}$ components (only descriptions and ranges are given), and 7 of the 10 $f_{\text{coop}}$ weights.
- Which reward form is intended: [P1] (4) as printed (with "$-1$", which makes the bonus 0 whenever $f_{\text{coop}} f_{\text{contrib}} \le 1$) or [P2] (3).
- The formula of $F_{\text{trans}}$. The meaning of $f_{\text{threshold}}$ in (8d).
- How the KPIs are normalized to $[0,1]$ for $f_{\text{coop}}$ (social welfare and liquidity are unbounded).
- Reputation weights and the decay factor.
- Whether imbalance (24) is computed over orders or trades, and before or after DSO clearing (over trades $\sum q_{\text{buy}} = \sum q_{\text{sell}}$ by construction).
- The loss factor $\kappa$, the edge-capacity allocation rule, whether edge flows reset each period, and the capacity-violation policy ("penalized or disallowed").
- Battery charge and discharge rate limits.
- The $\gamma_{\text{DSO}}$ and $\gamma_{\text{UD}}$ formulas, and the "implicit scaling" of the penalties.
- The Case 6 mapping of profile data to agents and its scaling.
- What "10 000 episodes" means in terms of RLlib iterations, and the PBT mutation domains and perturbation interval.
- The definition of $B_{\text{index}}$ and of agent responsiveness.
