# MARLEM: the market as stated in the paper

> The part of the MARLEM method this rebuild implements: the market, its DSO, the
> agents' accounting and batteries, the grid, and the order of one market step.
> Everything about reinforcement learning is left out (the observation, the reward,
> the training paradigms and algorithms, the learning experiments): here orders come
> from scripted rules or from the user on the Step page, not from learned policies.
> This file says **what the paper says**, not what the code does. Taken from the
> refactor branch's full summary of both papers and cut to the market.

**Source**

- **[P1]** Salazar-Peña, Tabares, González-Mancera. *MARLEM: A multi-agent
  reinforcement learning simulation framework for implicit cooperation in
  decentralized local energy markets.* Applied Energy 412 (2026) 127546.
  [marlem.pdf](marlem.pdf). This paper defines the environment.
- **[P2]** Same authors, *Harnessing Implicit Cooperation: A Multi-Agent
  Reinforcement Learning Approach Towards Decentralized Local Energy Markets*
  (SSRN preprint), the learning study. Cited here only for the mean congestion
  (§6.3).

Equation numbers are the paper's own, e.g. [P1] (8). Equations garbled in the PDF
text extraction were reconstructed from the surrounding text and are marked
*(reconstructed)*.

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

## 1. Architecture ([P1] §3.1, Fig. 2)

The paper has three conceptual levels:

| Level | Content | In this rebuild |
|---|---|---|
| **Level 0: Platform Marketplace** | Market Module (order matching, clearing, DSO, reputation, validation) and Grid Module (network, losses, congestion). Provides the physical and economic environment. | built: the market, and a SimBench network with a power flow instead of the paper's graph model |
| **Level 1: MARL Agents** | Self-interested DER agents with generation and demand profiles and an optional battery. Each learns a bidding policy from local observations. | the agents and their batteries, without learning: orders come from rules or the user |
| **Level 2: Implicit Cooperation** | The emergent coordination produced by shared KPIs in the observations and cooperation terms in the reward, also measured by those KPIs. | left out |

## 2. Orders ([P1] (2), §3.2.3)

In the paper an agent's action *is* its order for the period. Without learning,
the same four values describe what a participant submits:

$$
a_i = \left\langle p_{\text{bid}},\ q_{\text{bid}},\ \alpha,\ \beta \right\rangle
$$

| Component | Domain | Meaning |
|---|---|---|
| $p_{\text{bid}}$ | $[p_{\min}, p_{\max}]$ | Bid price |
| $q_{\text{bid}}$ | $[q_{\min}, q_{\max}]$ | Bid quantity |
| $\alpha$ | $\{0, 1\}$ | Order type: 0 = sell, 1 = buy |
| $\beta$ | $\{0, 1, \dots, \lvert\mathcal{I}\rvert + 1\}$ | Preferred trading partner index (the other agents, the DSO, or no preference) |

Two constraint layers are applied:

1. $p_{\text{bid}}$ and $q_{\text{bid}}$ are clipped to the market bounds.
2. $q_{\text{bid}}$ is constrained for physical feasibility with the battery, using
   $q_{\text{sell,max}}$ and $q_{\text{buy,max}}$ from [P1] (15) (§5.2).

## 3. One market step ([P1] §3.9, Fig. 4)

The paper's period $t$ runs eight phases. Phases 5 and 7 exist only for learning
(the reward, the observation) and are not part of this rebuild; the KPI update of
phase 5 belongs to Level 2 and is left out too.

| # | Phase | Content | Here |
|---|---|---|---|
| 1 | Action processing and validation | Limit each order by current generation, demand and battery state (physical). Then validate that price, quantity, type and partner fall within market bounds (rule-based). | yes |
| 2 | Order creation and submission | Validated orders become formal orders. If no partner is given, a rule-based selection scores partners by reputation and grid distance. | yes |
| 3 | Market clearing and trade execution | Three-stage clearing (§4): mutual preferences → double auction (with reputation) → DSO for the residual. Output: all executed trades and summary statistics. | yes |
| 4 | Energy tracking and battery updates | Trades update each agent's physical state (energy tracking, battery SoC) and the grid state (balance, congestion). | yes; the grid state comes from a power flow |
| 5 | Reward calculation and KPI updates | System KPIs from trades, agent states and grid conditions, then every agent's reward. | no (learning) |
| 6 | State transition | Advance the clock. Update states that depend on the full market outcome, such as financial balances and reputation scores. | yes |
| 7 | Observation update | Build each agent's next observation. | no (learning) |
| 8 | Episode management | Stop after the last period $\tau$; otherwise repeat for $t+1$. | yes: the last step of the day |

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

## 6. Grid ([P1] §3.5)

The paper's grid is a graph model. This rebuild replaces it with a SimBench network and an AC power flow ([SimBench](../simbench/README.md)); the paper's model is kept here because its distances, zones and congestion feed the DSO fees (§4.4) and the partner choice (§5.1).

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

**Mean congestion** [P2] (2):

$$
\bar{\zeta} = \frac{1}{\lvert \xi \rvert} \sum_{e \in \xi} \frac{F_e}{\max(C_e)}
$$

## 7. The paper's case study without learning ([P1] §4–5)

The case study of [P1] trains nothing: its agents bid at random within the rules. That makes it the reference for a market without learning.

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

## 8. Points the paper leaves unspecified

Needed to implement the market but not defined in [P1]:

- The formula of $F_{\text{trans}}$, and the meaning of $f_{\text{threshold}}$ in (8d).
- The fee factors $f_{\ast}$.
- Reputation weights and the decay factor.
- The loss factor $\kappa$, the edge-capacity allocation rule, whether edge flows
  reset each period, and the capacity-violation policy ("penalized or disallowed").
- Battery charge and discharge rate limits.
- The bid-ask spread mechanism used in the case study (§7), which §3.3.3 does not
  define.
