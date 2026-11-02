# The observation vector

What each agent observes in marlem-v2: the paper's 42 signals in its three groups
([P1] Table 2), then the other agents' reputations. MARLEM's own definitions, from
the original code, are listed in
[Learning layer §1.2](../marlem/learning.md#the-42-signals-as-marlem-defines-them);
this page has the same rows, as this implementation computes them.

Two places compute it:

- **[`signals.py`](../../core/market/signals.py)**: each signal as a plain function
  of the market's data, in three dictionaries (`KPIS`, `MARKET_SIGNALS`,
  `AGENT_SIGNALS`). A value with nothing to measure is NaN.
- **[`MarketEnv._observe`](../../core/env/market_env.py#L663-L689)**: puts them in order,
  scales each ([`_obs_scales`](../../core/env/market_env.py#L604-L661)), turns NaN into
  0 and clips to $[-10, 10]$.

The observation is computed for the step about to be played, $t$. "The last step"
is $t - 1$, the one just played.

The `observation` setting chooses which signals the agents see: `"paper"` (the
default) gives all 42, and `"pruned"` the 22 of
[`PRUNED_OBS`](../../core/market/signals.py), to compare the two. Every signal is still
computed either way, so a reward can read one the agents do not see, and the partner
block follows both.

## Notation

$T$ is the number of steps in a day (24 hourly, 96 quarter-hourly) and $N$ the
number of agents. $\mathcal{T}_{t-1}$ is the set of trades of the last step, and
$\mathcal{T}^{\text{P2P}}_{t-1}$ its trades between agents (clearing stages 1 and 2).
$\mathcal{H}$ is the set of steps played so far today. $V^{\text{buy}}$ and
$V^{\text{sell}}$ are the energy the DSO bought and sold in the last step.
$p_{\text{FiT}}$ and $p_{\text{util}}$ are the DSO's feed-in tariff and utility
price, and $\Delta p = p_{\text{util}} - p_{\text{FiT}}$ is their spread.

Each entry is scaled before it reaches the network. $E$ is `energy_scale`, the
largest generation or demand of any participant in any step of the training days.
$R$ is `reward_scale`, $p_{\text{util}} \cdot E$.

## What the reward reads

The last column of the three tables below shows which signals the `"salazar"` reward
([`SalazarReward.agent_reward`](../../core/env/reward.py#L367-L441), the original
code's) also uses, so that the observational ones stand apart. It describes that
reward only: the `"bill"` reward calls none of these signals, though it reads three of
the same quantities from the step's record: `utility_price`, the step's `profit` and
`deferred_demand_kwh`.

| In the reward | Signals | Meaning |
|---|---|---|
| a weight | 10 | every KPI, through `signals.kpis` and [`cooperation_factor`](../../core/env/reward.py#L205-L217): its weight in $f_{\text{coop}}$ ([`COOPERATION_WEIGHTS`](../../core/env/reward.py#L65-L76), adding up to 56), and $1 - x$ where lower is better |
| a term | 14 | the signal is not called, but the term named reads the same quantity from the step's record |
| — | 18 | observational only |

The terms are the five parts of $R_{\text{base}}$ ($r_{\text{grid}}$, $r_{\text{res}}$,
$r_{\text{trade}}$, $r_{\text{stab}}$, $r_{\text{econ}}$), the contribution factor
$f_{\text{contrib}}$ and the penalties $\gamma_{\text{DSO}}$ and $\gamma_{\text{UD}}$.
"Own" marks a term that reads agent $i$'s part of a figure the signal gives for all
agents.

The reward for step $t$ reads step $t$, which the observation shows at $t + 1$, unless
the row says otherwise. The KPIs too: over $\mathcal{H}$ with step $t$ included, and
raw, not scaled (E-13, E-20). A step in which the agent trades nothing pays only the
no-trades penalty and reads none of this (E-19).

## Market signals (16, the same for every agent)

| # | Entry | Definition | Scaled as | In the reward |
|---|---|---|---|---|
| 1-2 | `hour_sin`, `hour_cos` | $\sin$ and $\cos$ of $2\pi t / T$ (in place of MARLEM's step and time of day) | as is | — |
| 3 | `clearing_price` | $\sum_{\mathcal{T}^{\text{P2P}}} p\,q \,/\, \sum_{\mathcal{T}^{\text{P2P}}} q$ of the last step with peer trades; the tariffs' midpoint before any | $(p - p_{\text{FiT}}) / \Delta p$ | $r_{\text{stab}}$, $r_{\text{econ}}$, $f_{\text{contrib}}$ |
| 4 | `clearing_volume` | $\sum_{\mathcal{T}_{t-1}} q$, the DSO's trades included | $/\, E N$ | own trades: $r_{\text{res}}$, $\gamma_{\text{DSO}}$ |
| 5 | `grid_balance` | $B_{\text{grid}}$ before the DSO clears ([P1] eq. 20): energy offered minus asked | $/\, E N$ | $r_{\text{grid}}$, $r_{\text{stab}}$, $f_{\text{contrib}}$, $\gamma_{\text{DSO}}$ |
| 6 | `dso_buy_volume` | $V^{\text{buy}}$ | $/\, E N$ | — |
| 7 | `dso_sell_volume` | $V^{\text{sell}}$ | $/\, E N$ | — |
| 8 | `dso_total_volume` | $V^{\text{buy}} + V^{\text{sell}}$ | $/\, E N$ | own `dso_kwh`: $r_{\text{trade}}$, $\gamma_{\text{DSO}}$ |
| 9 | `p2p_volume` | $V^{\text{P2P}} = \sum_{\mathcal{T}^{\text{P2P}}_{t-1}} q$ | $/\, E N$ | own `local_kwh`: $r_{\text{trade}}$, $\gamma_{\text{DSO}}$ |
| 10 | `dso_trade_ratio` | $(V^{\text{buy}} + V^{\text{sell}}) / \sum_{\mathcal{T}_{t-1}} q$ | as is | own share: $\gamma_{\text{DSO}}$ |
| 11 | `net_grid_import` | $V^{\text{sell}} - V^{\text{buy}}$ | $/\, E N$ | as row 5 with the sign flipped: the DSO clears every open order, so this is $-B_{\text{grid}}$ |
| 12 | `dso_buy_price` | $p_{\text{FiT}}$ | $(p - p_{\text{FiT}}) / \Delta p$ | $r_{\text{econ}}$ on a sell; the same step's value, seen before it is played |
| 13 | `dso_sell_price` | $p_{\text{util}}$ | $(p - p_{\text{FiT}}) / \Delta p$ | $r_{\text{econ}}$ on a buy; the same step's value, seen before it is played |
| 14 | `mean_local_price` | $\bar{p}^{\text{P2P}} = \sum_{\mathcal{T}^{\text{P2P}}_{t-1}} p\,q \,/\, V^{\text{P2P}}$ | $(p - p_{\text{FiT}}) / \Delta p$ | as row 3 in a step with peer trades; without any the reward has the carried-over price, this signal NaN |
| 15 | `price_spread` | $\Delta p$ | $/\, \Delta p$ | — |
| 16 | `local_price_advantage` | $\tfrac{1}{2}(p_{\text{FiT}} + p_{\text{util}}) - \bar{p}^{\text{P2P}}$, all of the last step | $/\, \Delta p$ | — |

## Agent signals (16, the agent's own)

For agent $i$; the sums over $\tau \in \mathcal{H}$ run over the steps played so
far. $x^{\text{def}}_{i,\tau}$ is the energy no trade or battery covered: the
demand drawn untraded from the upstream grid, or the surplus spilled. It is what
settlement leaves after generation, trades and the battery
([`ParticipantOutcome`](../../core/market/agent/der.py#L31-L82)).

| # | Entry | Definition | Scaled as | In the reward |
|---|---|---|---|---|
| 1 | `generation` | $G_{i,t}$, the true value | $/\, E$ | — |
| 2 | `demand` | $D_{i,t}$, the true value | $/\, E$ | $\gamma_{\text{UD}}$, the day's total: only the sum $\sum_{\tau=0}^{T-1} D_{i,\tau}$ is read, at the day's last step |
| 3 | `cumulative_demand_satisfied` | $\sum_{\tau \in \mathcal{H}} (D_{i,\tau} - D^{\text{def}}_{i,\tau})$ | $/\, E T$ | $\gamma_{\text{UD}}$, at the day's last step |
| 4 | `cumulative_demand_deferred` | $\sum_{\tau \in \mathcal{H}} D^{\text{def}}_{i,\tau}$ | $/\, E T$ | $\gamma_{\text{UD}}$: the unmet demand, at the day's last step |
| 5 | `remaining_demand` | $\sum_{\tau = t}^{T-1} D_{i,\tau}$, the true future | $/\, E T$ | $\gamma_{\text{UD}}$, the day's total: the same as this signal only at $t = 0$ |
| 6 | `cumulative_supply_satisfied` | $\sum_{\tau \in \mathcal{H}} (G_{i,\tau} - G^{\text{def}}_{i,\tau})$ | $/\, E T$ | — |
| 7 | `cumulative_supply_deferred` | $\sum_{\tau \in \mathcal{H}} G^{\text{def}}_{i,\tau}$ | $/\, E T$ | — |
| 8 | `remaining_supply` | $\sum_{\tau = t}^{T-1} G_{i,\tau}$, the true future | $/\, E T$ | — |
| 9 | `mean_profit` | $\frac{1}{\lvert\mathcal{H}\rvert} \sum_{\tau \in \mathcal{H}} \pi_{i,\tau}$, the profit of [P1] eq. 14 | $/\, R$ | — |
| 10 | `reputation` | $r_i$ ([P1] eq. 12) | as is | — |
| 11 | `battery_energy` | $E_i$ | $/\, E$ | — |
| 12 | `battery_soc` | $E_i / C_i$, $C_i$ the capacity | as is | — |
| 13 | `available_charge` | what the battery can still take this step ([P1] eq. 15d) | $/\, E$ | — |
| 14 | `available_discharge` | what it can still give ([P1] eq. 15c) | $/\, E$ | — |
| 15 | `cumulative_charge` | energy charged so far today | $/\, E T$ | — |
| 16 | `cumulative_discharge` | energy discharged so far today | $/\, E T$ | — |

$D^{\text{def}}$ and $G^{\text{def}}$ are the two sides of $x^{\text{def}}$. An agent
without a battery has 0 in rows 11-16.

## Implicit-cooperation KPIs (10, the same for every agent)

Over the day so far, $\mathcal{H}$ (`# OPEN E-10`: the papers give no window).
$\mathcal{O}$ and $\mathcal{T}$ are the orders and trades of those steps.

| # | Entry | Definition | Scaled as | In the reward |
|---|---|---|---|---|
| 1 | `social_welfare` | $\sum_{\mathcal{T}} p\,q$ (E-09: turnover, not surplus) | $/\, R N T$ | weight 7 |
| 2 | `liquidity` | $\sum_{\mathcal{T}} q$, the DSO's trades included | $/\, E N T$ | weight 1.5 |
| 3 | `bid_ask_spread` | $\operatorname{mean}_{\mathcal{O}}(p \mid \text{sell}) - \operatorname{mean}_{\mathcal{O}}(p \mid \text{buy})$ ([P1] eq. 23) | $/\, \Delta p$ | weight 1.5, as $1 - x$ |
| 4 | `price_volatility` | standard deviation of the clearing price over $\mathcal{H}$ | $/\, \Delta p$ | weight 3, as $1 - x$ |
| 5 | `supply_demand_imbalance` | $\sum_{\tau} \lvert Q^{\text{buy}}_\tau - Q^{\text{sell}}_\tau \rvert \,/\, \sum_{\tau} (Q^{\text{buy}}_\tau + Q^{\text{sell}}_\tau)$, with $Q$ a step's ordered energy (E-08, E-11) | as is | weight 10, as $1 - x$ |
| 6 | `grid_congestion` | mean over $\mathcal{H}$ of the mean line loading $F_e / \max(C_e)$ ([P1] eq. 19), as the fees saw it | as is | weight 9, as $1 - x$ |
| 7 | `coordination_score` | one minus row 5 ([P1] eq. 27) | as is | weight 5 |
| 8 | `coordination_convergence` | $1 - \min(1, \sigma / \mu)$ of the traded energy of the last three steps, 0 before the third (the original's; [P1] gives no formula) | as is | weight 8 |
| 9 | `der_self_consumption` | $\sum_{\mathcal{T}^{\text{P2P}}} q \,/\, \sum_{\mathcal{T}} q$ ([P1] eq. 25; E-12) | as is | weight 5 |
| 10 | `flexibility_utilization` | $\sum_{\mathcal{T}^{\text{P2P}}} q \,/\, \sum_{\mathcal{O}} (q \mid \text{sell})$: the share of the energy offered that found a peer | as is | weight 6 |

## Partner block

`partner_rep_1` … `partner_rep_{N-1}`: the other agents' reputations ([P1] eq. 12)
after the last step, in the agent's candidate order (`MarketEnv.partners`). [P1]
adds every agent's reputation when partner preference is on; the partner action
indexes the same order. With five agents the observation has $42 + 4 = 46$ entries.

## Missing values

Before the first step there is no last step, and without peer trades there is no
local price. Such a signal is NaN in `signals.py` and 0 in the observation, as in
MARLEM. For `mean_local_price` and `local_price_advantage`, 0 after scaling is also
a real value (a trade at the feed-in tariff, no advantage), so the two cases cannot
be told apart. This is open (`# OPEN E-07` in `_observe`).

## How it differs from MARLEM

| Row | marlem-v2 | MARLEM |
|---|---|---|
| Market 1-2 | sin and cos of the hour | the step and the hour as numbers |
| Market 3 | peer trades only, carried over without any | the DSO's trades included (M-15), the tariffs' midpoint without any |
| Market 5 | before the DSO clears | after it clears |
| Market 12, 13, 15 | the step about to be played | the step just played |
| Agent 3-4, 6-7 | the battery counts | the battery left out |
| Agent 9 | the mean | the sum |
| KPI 3 | ask minus bid, as eq. 23 | bid minus ask |
| KPI 4 | over the peer clearing price, every step | over the clearing price with the DSO's trades, those above 0 |
| KPI 5, 7 | over the orders | over the trades, divided by $C_{\text{grid}}$ (E-08) |
| KPI 6 | mean line loading, as eq. 19 | the DSO's congestion level |
| KPI 10 | over the energy offered | over each agent's surplus or deficit plus its battery |
| KPIs 1, 2, 3, 5, 6, 7, 9, 10 | over the day so far | over the last step |
| All | scaled to about $[-1, 1]$ | raw (E-06) |
