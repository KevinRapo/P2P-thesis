# The two papers side by side

> Do the two MARLEM papers describe the same method? This page compares every
> equation and design statement that appears in both, says where they agree and
> where they differ, and which of the two the rebuild follows. It is a first pass
> on the method only; the second paper's results are not reviewed here.

## The papers and how they divide the work

| | [P1] | [P2] |
|---|---|---|
| Title | *MARLEM: a multi-agent reinforcement learning simulation framework for implicit cooperation in decentralized local energy markets* (Applied Energy 412, 2026, 127546) | *Harnessing implicit cooperation: a multi-agent reinforcement learning approach towards decentralized local energy markets* (SSRN preprint, not peer reviewed) |
| Authors | Salazar-Peña, Tabares, González-Mancera | the same |
| Role | The framework: market, DSO, agents, batteries, grid, KPIs, reward, paradigms (overview only) | The MARL study: implicit cooperation, the three paradigms and three algorithms in detail, the 3 × 3 experiment |
| Equations | (1)-(27) | (1)-(20) |
| Case study | Batteries, zero-intelligence agents (§4) | 8 agents on IEEE 34, 3 × 3 MARL matrix (§4) |

Each paper hands part of the method to the other:

- **[P2] defers the environment to [P1].** "While the complete mathematical
  derivation of the environment is detailed in [9], we focus here on the specific
  augmentations that drive cooperative behavior" ([P2] §3.1; [9] is [P1]). [P2]
  restates no market, DSO, agent, battery or loss equation.
- **[P1] defers the MARL method to [P2].** "A detailed treatment of the MARL
  framework, including its full mathematical and implementation specifics, is
  reserved for a forthcoming paper" ([P1] §3.7).

So the two papers overlap in only five places, and only those can disagree:

1. the Dec-POMDP and the observation;
2. the grid balance and grid congestion;
3. the reward;
4. the KPIs;
5. the training paradigms and algorithms.

**For the market layer this means [P1] is the only specification.** Everything in
the [market validation](market.md) is checked against [P1] alone; [P2] neither
confirms nor contradicts it.

## Summary

| Topic | [P1] | [P2] | Verdict |
|---|---|---|---|
| Dec-POMDP tuple, partial observability | §3.2 | §3.1 | Agree |
| Observation vector (16 + 16 + 10) | Table 2 | Table 5 | Agree, word for word |
| Grid balance $B_{\text{grid}}$ | eq. 20 | eq. 1 | Same formula. [P2] calls it "normalized"; it is not |
| Grid congestion | eq. 19 (per line) | eq. 2 (mean over lines) | Agree; [P2] writes out the mean [P1] describes in words |
| **Reward, overall form** | eq. 3-4 | eq. 3 | **Differ**, and the code is a third form; [P1] eq. 4 mistranscribes it |
| **Contribution factor $f_{\text{contrib}}$** | eq. 6 | §3.1 text | **Differ**; [P1] matches the code |
| **DSO penalty $\gamma_{\text{DSO}}$** | fixed, $p_{\text{dso}} = 15$ | scaled by grid imbalance | **Differ**; [P2] matches the code |
| **Trading reward, P2P vs DSO weight** | 0.3 / 0.3 | "a higher weight for P2P" | **Differ**; the code meant [P2]'s, ran [P1]'s |
| Base reward $R_{\text{base}}$, components | five, with weights and ranges | the same five, no weights | Agree; only [P1] has numbers |
| Cooperation factor $f_{\text{coop}}$ | eq. 5, weights given | text only | Agree in words; only [P1] has the formula |
| KPIs | eq. 21-27 | eq. 4-10 | Agree, the same formulas |
| Paradigms CTCE, CTDE, DTDE | §3.7.1, words | §3.4, eq. 16-20 | Agree; [P2] adds the formulas |
| Algorithms PPO, APPO, SAC | §3.7.2, words | §3.3, eq. 11-15 | Agree; [P2] adds the formulas |
| Grid Balance Index $B_{\text{index}}$ | — | §4.3 | Only in [P2], and undefined |
| Market, DSO, fees, agents, battery, losses | eq. 2, 7-18 | — | Only in [P1] |

Four real disagreements, all in the reward, where the original code is a third
version (§3 shows it next to both papers). Everything else either agrees or is
written in only one of the papers.

## 1. Dec-POMDP and observation

**Agree.** Both formulate the market as a Dec-POMDP ⟨I, S, A, T, R, Ω, O⟩ in which
each agent sees a local observation of three parts: market signals (public),
agent-specific signals (private) and implicit-cooperation KPIs (shared). The
paragraphs describing the three parts are the same text in both papers, and
[P1] Table 2 and [P2] Table 5 list the same 42 signals in the same order:

| Market signals (16) | Agent signals (16) | KPIs (10) |
|---|---|---|
| step, time of day, clearing price and volume, grid balance, DSO buy/sell/total volume, P2P volume, DSO trade ratio, net grid import, DSO buy/sell price, mean local price, price spread, local price advantage | generation, demand, cumulative demand satisfied/deferred, remaining demand, cumulative supply satisfied/deferred, remaining supply, mean profit, reputation, battery energy, SoC, available charge/discharge, cumulative charge/discharge | social welfare, liquidity, mean bid-ask spread, price volatility, supply-demand imbalance, grid congestion, coordination score, coordination convergence, DER self-consumption, flexibility utilization |

Small differences in wording only:

- [P1] adds the state factorisation, eq. 1, $s_t = \langle s^{\text{time}}, s^{\text{market}}, s^{\text{agents}},
  s^{\text{DSO}}, s^{\text{grid}}, s^{\text{history}} \rangle$; [P2] does not repeat it.
- [P2] §3.1 says agents "observe the P2P trade ratio". The table has the *DSO*
  trade ratio, which is its complement, so the information is the same.
- [P2] Table 7 gives the forecast error (30 %) that [P1] mentions only as
  "forecasts".

The action $a_i = \langle p_{\text{bid}}, q_{\text{bid}}, \alpha, \beta \rangle$ ([P1] eq. 2) is not restated in [P2].

## 2. Grid balance and grid congestion

**Grid balance: same formula, different description.**

$$
\text{[P1] (20), [P2] (1):}\qquad
B_{\text{grid}} = \sum_{i \in \mathcal{I}} \left( G_i - D_i + E_{\text{bought},i} - E_{\text{sold},i} \right)
$$

- **[P1]** describes it as "the sum of all agents' net energy positions": close to
  0 means a self-sufficient market, large values mean heavy reliance on the external
  grid.
- **[P2]** calls it "a normalized indicator of the net energy position", with
  positive meaning surplus. Eq. 1 has no normalisation, and neither paper says what
  it would be normalised by.

Both papers also list "grid balance" as a KPI, described as "the difference between
total generation and consumption". That is $\sum (G - D)$ only, without the trade
terms of the equation they cite.

**Grid congestion: agree.** [P1] eq. 19 defines it per line, $\zeta_e = F_e /
\max(C_e)$, and the KPI as "the average congestion level across all power lines as
defined in (19)". [P2] eq. 2 writes that average out:

$$
\bar{\zeta} = \frac{1}{\lvert \xi \rvert} \sum_{e \in \xi} \frac{F_e}{\max(C_e)}
$$

## 3. Reward

This is where the papers disagree, and the original code is a third version. Each
part below shows [P1], [P2] and the code. The code is copied from
`src/environment/reward.py` in the original repository, [salazarna/marlem](https://github.com/salazarna/marlem/tree/15d6715a7b7ad31700d3758f2a2dd9df053773a7) (commit
`15d6715`).

### Overall form: three versions

$$
\text{[P1] (3):}\qquad R_i = \operatorname{sign}(r_{\text{raw}}) \cdot \ln\!\left(1 + \frac{\lvert r_{\text{raw}} \rvert}{20}\right) \cdot 20
$$

$$
\text{[P1] (4):}\qquad r_{\text{raw}} = R_{\text{base},i} \cdot \left(1 + \ln\!\left(1 + \frac{\max(0,\ f_{\text{coop}} \cdot f_{\text{contrib},i} - 1)}{5}\right)\right) - \gamma_{\text{DSO},i} - \gamma_{\text{UD},i}
$$

$$
\text{[P2] (3):}\qquad R_i = R_{\text{base},i} \cdot \left(1 + f_{\text{coop}} \cdot f_{\text{contrib},i}\right) - \gamma_{\text{DSO},i} - \gamma_{\text{UD},i}
$$

**The code**
([`reward.py` L228-L242](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L216-L232)):

```python
cooperation_boost = (1.0 + cooperation_factor * contribution_factor)

boosted_base_reward = base_reward * (1.0 + np.log1p(max(0.0, cooperation_boost - 1.0)) / 5.0)

penalty_scale = max(max(abs(boosted_base_reward), 1.0), 1.0) * 0.3
normalized_dso_penalty = dso_penalty * penalty_scale
normalized_demand_penalty = demand_response_penalty * penalty_scale / self.p_dso

raw_reward = boosted_base_reward - normalized_dso_penalty - normalized_demand_penalty

return np.sign(raw_reward) * np.log1p(np.abs(raw_reward) / 20.0) * 20.0
```

Written as an equation, the code is:

$$
\text{code:}\qquad r_{\text{raw}} = R_{\text{base},i} \cdot \left(1 + \frac{\ln\!\left(1 + f_{\text{coop}} \cdot f_{\text{contrib},i}\right)}{5}\right) - s \cdot \gamma_{\text{DSO},i} - s \cdot \frac{\gamma_{\text{UD},i}}{p_{\text{dso}}},
\qquad s = 0.3 \cdot \max(\lvert R_{\text{base},i} \cdot (\ldots) \rvert, 1)
$$

| | [P1] eq. 3-4 | [P2] eq. 3 | Code |
|---|---|---|---|
| Final log compression | Yes, scale 20 | None | Yes, scale 20 (as [P1] eq. 3) |
| Cooperation bonus on $R_{\text{base}}$ | $\ln\left(1 + \max(0,\ f_{\text{coop}} \cdot f_{\text{contrib}} - 1) / 5\right)$ | $f_{\text{coop}} \cdot f_{\text{contrib}}$ | $\ln(1 + f_{\text{coop}} \cdot f_{\text{contrib}}) / 5$ |
| Bonus at $f_{\text{coop}} \cdot f_{\text{contrib}} = 1$ (its maximum) | **0** | 1 (doubles $R_{\text{base}}$) | $\ln 2 / 5 \approx 0.14$ |
| Penalties scaled by the reward's size | Said in the text ("implicitly scaled relative to the reward magnitude"), not in the equation | No | Yes, by $s$ |

**What this shows.**

- **[P1] eq. 4 is the code, mistranscribed.** In the code, `max(0, cooperation_boost
  − 1)` subtracts the 1 that `cooperation_boost` itself added, so it is just
  $f_{\text{coop}} \cdot f_{\text{contrib}}$. [P1] printed $\max(0,\ f_{\text{coop}} \cdot f_{\text{contrib}} - 1)$, dropping the
  $1 +$, and moved the $/\,5$ inside the logarithm.
- **The printed version is inert.** Both papers say $f_{\text{coop}}$ and $f_{\text{contrib}}$ lie in
  [0, 1], so their product is at most 1. Under [P1] eq. 4 the bonus is then **always
  0**, and the reward is just $R_{\text{base}}$ minus the penalties.
- **The code's bonus is small on paper but large in practice.** With both factors
  in [0, 1] it reaches at most 14 % of $R_{\text{base}}$. But the code's $f_{\text{coop}}$ is not in
  [0, 1]: it is about 1811 in a traced episode (register I-41, below). With
  $f_{\text{contrib}} = 0.5$ the bonus is then $\ln(1 + 906) / 5 \approx 1.36$, which more than
  doubles $R_{\text{base}}$.
- **[P2] states a far stronger bonus,** up to 100 % of $R_{\text{base}}$, and calls it "the
  core contribution of this work regarding implicit cooperation". [P2]'s experiments
  ran on the code (register I-42), so the bonus the trained agents saw was the
  code's, not [P2]'s.

### Contribution factor $f_{\text{contrib}}$: [P1] matches the code, [P2] does not

| | [P1] eq. 6 | [P2] §3.1 |
|---|---|---|
| Formula | $0.5\, r_{\text{grid}} + 0.3\, r_{\text{share}} + 0.2\, r_{\text{dev}}$ | "a weighted sum of the agent's marginal contribution to reducing grid imbalance ($-\partial \lvert B_{\text{grid}} \rvert / \partial a_i$), its contribution to price efficiency, and its contribution to local trading volume" (no weights) |
| Grid part | $r_{\text{grid}}$: a score, 0.5 for neutral actions, toward 1 if the agent's trade reduces the imbalance, toward 0 if it worsens it | The marginal effect of the agent's action on $\lvert B_{\text{grid}} \rvert$ |

**The code**
([`reward.py` L487-L514](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L471-L499)):

```python
grid_contribution = NEUTRAL                    # 0.5

if matching.grid_balance != 0:
    net_contribution = sum(t.quantity if t.seller_id == agent.id else -t.quantity for t in agent_trades)
    if (matching.grid_balance > 0 and net_contribution < 0) or (matching.grid_balance < 0 and net_contribution > 0):
        impact_ratio = min(1.0, abs(net_contribution) / abs(matching.grid_balance))
        grid_contribution = 0.5 + (0.5 * impact_ratio)   # [0.5-1.0] range for helpful actions
    else:
        impact_ratio = min(1.0, abs(net_contribution) / abs(matching.grid_balance))
        grid_contribution = 0.5 - (0.5 * impact_ratio)   # [0.0-0.5] range for unhelpful actions

# ...
    price_contribution = max(0.0, min(1.0, 1.0 - avg_price_deviation * 2))

local_contribution = len(agent_local_trades) / len(agent_trades) if agent_trades else 0

return (self._w_grid * grid_contribution) + (self._w_price * price_contribution) + (self._w_local * local_contribution)
```

with `_w_grid = 0.5`, `_w_price = 0.2`, `_w_local = 0.3`
([L92-L95](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L91-L93)).

**What this shows.**

- **[P1] eq. 6 describes this code exactly:** the weights 0.5 / 0.3 / 0.2, the 0.5
  neutral point, the share of P2P trades, the price deviation.
- **[P2]'s marginal contribution $-\partial \lvert B_{\text{grid}} \rvert / \partial a_i$ exists nowhere.** The code scores
  only whether the agent's net trade has the right sign and how large it is
  against the balance (register I-79). Neither paper shows how a derivative with
  respect to an action could be taken in an auction-cleared market.
- **The grid part is constant in practice.** It reads `matching.grid_balance`,
  which is the DSO balance and always 0 (register I-24). The `if` never runs, so
  the grid part is always 0.5 (register I-44).

### DSO penalty $\gamma_{\text{DSO}}$: [P2] matches the code, [P1] does not

- **[P1]:** "penalties for reliance on the DSO ($p_{\text{dso}} = 15.0$) and unmet demand
  ($p_{\text{no_trades}} = 5.0$)". The penalties are fixed.
- **[P2]:** $\gamma_{\text{DSO}}$ "is applied for trading with the DSO, scaled by the current grid
  imbalance … amplified during critical imbalance periods".

**The code**
([`reward.py` L207-L223](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L200-L214),
[L138-L139](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L134-L136)):

```python
# γ_DSO
dso_ratio = dso_quantity / total_quantity if total_quantity > 0 else 0.0
dso_penalty = dso_ratio * self.p_dso * abs(self.dso.balance) / max(self.grid_network.capacity, 1.0)

# γ_UD
if is_terminal:
    unmet_demand = max(0.0, agent.total_demand_required - agent.cumulative_demand_satisfied)
    if agent.total_demand_required > 0:
        unmet_demand_ratio = unmet_demand / agent.total_demand_required
        demand_response_penalty = self.p_dso * (unmet_demand_ratio ** 2)

# where p_no_trades is actually used: an agent without trades gets a fixed reward
if not agent_trades:
    return np.sign(-self.p_no_trades) * np.log1p(np.abs(-self.p_no_trades) / 20.0) * 20.0
```

**What this shows.**

- **$\gamma_{\text{DSO}}$: [P2]'s description is the code's.** The penalty is the agent's DSO share
  $\times\ p_{\text{dso}} \times \lvert \text{imbalance} \rvert / \text{capacity}$. [P1]'s "$p_{\text{dso}} = 15.0$" is only the factor
  inside it.
- **In practice there is no DSO penalty.** The imbalance used is `dso.balance`,
  always 0 (register I-24), so the penalty is always 0.
- **$\gamma_{\text{UD}}$ uses $p_{\text{dso}}$, not [P1]'s $p_{\text{no_trades}} = 5$** (register I-46). It runs only
  when `is_terminal` is true, which never happens (register I-02).
- **$p_{\text{no_trades}}$ does something else:** it is the fixed reward −4.46 returned to an
  agent that made no trade at all, before any other term (register I-47).

### Trading reward: [P1] matches the code's accident, [P2] its intent

- **[P1]:** "Trading success ($w_{\text{trade}} = 5.0$): … defined as $0.3\,\rho_{\text{local}} + 0.3\,\rho_{\text{dso}}$". Local and DSO fills weigh the same.
- **[P2]:** "a trading component which incentivizes successful transactions with a
  higher weight for P2P transactions to create a preference for local coordination".

**The code**
([`reward.py` L80-L95](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L78-L93),
[L262](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L248-L251)):

```python
# Trade weights
self._w_local: float = 0.7  # Higher weight for local trades
self._w_dso: float = 0.3  # Lower weight for DSO trades
# ...
# Contribution weights
self._w_grid: float = 0.5  # Grid contribution
self._w_price: float = 0.2  # Price contribution
self._w_local: float = 0.3  # Local trading contribution

# _calculate_trading_reward
return (self._w_local * local_quantity_ratio) + (self._w_dso * dso_quantity_ratio)
```

**What this shows.** One attribute name, `_w_local`, is used for two different
weights. The trading reward's local weight (0.7, "higher weight for local trades")
is overwritten fifteen lines later by $f_{\text{contrib}}$'s local weight (0.3). The trading
reward therefore runs as 0.3 / 0.3 (register I-45).

- **[P1] printed the result of the accident,** 0.3 / 0.3.
- **[P2] describes the intent,** a higher P2P weight, which is what the code's
  first assignment and its comment say.
- **The weights in the code are right for $f_{\text{contrib}}$,** which matches [P1]
  eq. 6 (above).

### $R_{\text{base}}$ and $f_{\text{coop}}$: agree, numbers only in [P1]

Both list the same five base components: economic efficiency, grid balance,
resource allocation, trading and stability. Only [P1] gives weights (10, 1.5, 5,
2, 3) and ranges, and its weights match the code's.

Both describe $f_{\text{coop}}$ as a weighted sum of normalised system KPIs. Only [P1] gives
the formula and weights (eq. 5, total weight 56). The code
([L176-L198](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L170-L192))
computes it as [P1] eq. 5 but feeds it raw, unnormalised KPIs, so $f_{\text{coop}}$ is
nowhere near [0, 1]: about 1811 in a traced episode (register I-41, I-75). Neither
paper gives the normalisation ranges.

## 4. KPIs

**Agree.** [P2] §3.2 repeats [P1] §3.6.2 nearly word for word, with the same
equations under new numbers:

| KPI | [P1] | [P2] | Formula |
|---|---|---|---|
| Social welfare | (21) | (4) | $\sum_{\text{trades}} p \cdot q$ |
| Market liquidity | (22) | (5) | $\sum_{\text{trades}} q$ |
| Mean bid-ask spread | (23) | (6) | $\mathbb{E}[p_{\text{ask}}] - \mathbb{E}[p_{\text{bid}}]$ |
| Price volatility | text | text | std of the clearing price over a window |
| Supply-demand imbalance | (24) | (7) | $\lvert \sum q_{\text{buy}} - \sum q_{\text{sell}} \rvert / C_{\text{grid}}$ |
| Grid congestion | (19) | (2) | mean line loading |
| Grid balance | (20) | (1) | as §2 |
| DER self-consumption | (25) | (8) | $\sum q_{\text{P2P}} / \sum (q_{\text{P2P}} + q_{\text{DSO}})$ |
| Flexibility utilization | (26) | (9) | $\sum q_{\text{P2P}} / \sum q_{\text{available}}$ |
| Coordination score | (27) | (10) | $1 - \text{Imbalance}$ |
| Coordination convergence | text | text | "calculated similarly to the price volatility" |

They agree, but they share the same problems, so [P2] does not resolve them:

- **Social welfare** is described as "the sum of consumer and producer surplus" but
  written as $\sum p \cdot q$, which is turnover. In true welfare, payments between agents
  cancel (register I-36).
- **Imbalance** over *trades* is always 0, because every trade has one buyer and
  one seller. It means something only over orders or physical positions, and
  neither paper says which (register I-68). The coordination score, [P2]'s headline
  metric, is $1 - \text{Imbalance}$.
- **Spread** is $\mathbb{E}[p_{\text{ask}}] - \mathbb{E}[p_{\text{bid}}]$, which is negative whenever bids exceed asks,
  that is, whenever there is anything to trade.
- **"DER self-consumption"** measures the P2P share of traded energy, not
  self-consumption (register I-69).

## 5. Training paradigms and algorithms

**Agree.** [P1] describes CTCE, CTDE and DTDE in words; [P2] gives each a formula
and says the same things:

| Paradigm | [P1] §3.7.1 | [P2] §3.4 |
|---|---|---|
| CTCE | One policy, full global state, joint action; "a theoretical upper bound" | The same, eq. 16 (joint policy) and eq. 17 (objective summed over all agents); "the theoretical upper bound for coordination quality" |
| CTDE | Centralized critic in training, local observation in execution | The same, eq. 18 (actor gradient with a centralized critic Q(s, a)) |
| DTDE | Independent learners; non-stationarity mitigated by the shared KPIs | The same, eq. 19-20 (each agent's transition absorbs the others' policies) |

The same holds for the algorithms. [P1] §3.7.2 names PPO, APPO and SAC with one
sentence each, and [P2] §3.3 gives their objectives (eq. 11-15). Both name
Population-Based Training.

One addition in [P2] matters for comparing the paradigms: eq. 17 sums the reward
over all agents for CTCE, while CTDE and DTDE optimise each agent's own return
(eq. 19). Returns of the three paradigms are therefore on different scales
(register I-73). [P1] does not say how CTCE's reward is formed.

## 6. Only in one paper

| Only in [P1] | Only in [P2] |
|---|---|
| The market: orders and validation (eq. 2, 15), three-stage clearing, pricing mechanisms (eq. 9-11) | Algorithm objectives (eq. 11-15) and paradigm formulas (eq. 16-20) |
| The DSO: balance (eq. 7), fees (eq. 8a-8h) | The **Grid Balance Index $B_{\text{index}}$** (§4.3): "incorporates transmission losses and external grid reliance". Used as an evaluation metric, never defined, and absent from [P1] and from the code (register I-80) |
| Reputation (eq. 12) and the ledger | Agent responsiveness (§4.3): correlation between system signals and actions |
| Agent balance and profit (eq. 13-14), battery (eq. 16), profiles (eq. 17) | |
| Losses (eq. 18), zones, the grid update | |
| Reward log-compression (eq. 3), all reward weights and penalty values | |

## Case setups (not a method difference)

The two case studies differ, as expected for different experiments. The table is
here only so that numbers from one are not read as the other's:

| | [P1] §4 | [P2] §4, Tables 6-7 |
|---|---|---|
| Agents | 7, base capacity 60 kW | 8, 75-180 kW |
| Grid | Mesh, 1200 kW | IEEE 34-node, 1800 kW |
| Agents' policy | Zero intelligence (random bids) | Trained (3 paradigms × 3 algorithms) |
| Clearing mechanism | Bid-ask spread | Not stated |
| Price range | 35-280 \$/MWh | 20-600; DSO prices plotted in "\$/kWh" (Fig. 3) |
| Quantity range | 0.1-200 kWh | 0-180 kWh |
| Batteries | Ratio 0.5-1.2, $\eta$ 95 % | Ratio 0.5-1.0, $\eta$ 95 %, SoC 5-95 % |

The price units differ by a factor of 1000 between the papers (\$/MWh vs "\$/kWh"),
on top of the unit problems inside the code (register I-56).

## What the rebuild follows

- **Market layer (`marlem-clean`):** [P1] alone, since [P2] restates none of it.
  Its gaps are listed in the [market validation](market.md#problems-in-the-papers-market-method).
- **RL layer:** the reward must be chosen, because the papers give two. The choices
  to record:
  1. the overall form: [P1] eq. 4 (bonus inert as printed), the code's (what [P1]
     meant, $\ln(1 + f_{\text{coop}} \cdot f_{\text{contrib}}) / 5$) or [P2] eq. 3;
  2. whether to keep [P1]'s log compression, eq. 3;
  3. $f_{\text{contrib}}$'s grid part, a scored direction ([P1]) or a marginal effect ([P2]);
  4. $\gamma_{\text{DSO}}$, fixed or scaled by the imbalance;
  5. the trading weights.

  The KPIs, observation and paradigms can follow either paper, since they agree.
