# The reward

> What a played market step is worth to each agent. The default is the net bill;
> the original code's reward exists as an option. The reward only reads what the
> market did ([reward.py](../../../core/env/reward.py)); it changes nothing.

## E2. Reward

Per agent, from its `ParticipantOutcome`:

$$
r_i = \frac{\text{profit}_i + p_\text{FiT} \cdot \text{deferred supply}_i - p_\text{utility} \cdot \text{deferred demand}_i}{\text{scale}}, \qquad \text{scale} = \bar p_\text{utility} \cdot E
$$

where profit is eq. 14 net of fees; deferred demand and deferred supply are what its
trades and battery left uncovered and left over, exchanged untraded with the upstream
grid and settled at retail (MP-1e): bought at the step's utility
price $p_\text{utility}$, sold at its feed-in tariff $p_\text{FiT}$. That energy is
settled with the DSO and pays the fees of a DSO trade, which are in the profit
(MP-1f, 11 Nov 2026; runs before then had none). Runs before
4 Nov 2026 paid the deferred supply nothing. $\bar p_\text{utility}$ is the day's highest utility
price ([`Dso.tariff_range`](../../../core/market/dso.py#L125-L136)) and $E$ the
`energy_scale`, the largest generation or demand of any participant in any step of
the training days. Both scales are resolved once per run and reused for every later
environment of the run, held-out days included ([When results are made](../evaluation/index.md#when-results-are-made)).
CTCE's `CTCEEnv` sums the agents' rewards, $R = \sum_i r_i$; DTDE and CTDE keep
each agent's own.

## What the reward reads

The last column of the three signal tables in [Observation](observation.md) shows which signals the `"salazar"` reward
([`SalazarReward.agent_reward`](../../../core/env/reward.py#L372-L446), the original
code's) also uses, so that the observational ones stand apart. It describes that
reward only: the `"bill"` reward calls none of these signals, though it reads five of
the same quantities from the step's record: `utility_price`, `feed_in_tariff`, the
step's `profit`, `deferred_demand_kwh` and `deferred_supply_kwh`.

| In the reward | Signals | Meaning |
|---|---|---|
| a weight | 10 | every KPI, through `signals.kpis` and [`cooperation_factor`](../../../core/env/reward.py#L210-L222): its weight in $f_{\text{coop}}$ ([`COOPERATION_WEIGHTS`](../../../core/env/reward.py#L70-L81), adding up to 56), and $1 - x$ where lower is better |
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

## The rewards to choose from

The `reward` setting of the environment (`env_config`) names one of two rewards
([`REWARDS`](../../../core/env/reward.py)); both read the step's `StepRecord`.

| `reward` | Class | What it pays |
|---|---|---|
| `"bill"` (default) | [`NetBillReward`](../../../core/env/reward.py) | the net bill: `(profit + p_FiT · deferred_supply − p_utility · deferred_demand) / reward_scale`. What no trade covers is settled at retail, as a household's supply contract would (MP-1e): an untraded import at the step's utility price, an untraded export at its feed-in tariff, without grid fees. A trade then pays off only against these outside options, a peer trade at a price between the tariffs; an order that ends up with the DSO pays the same tariff plus its fees. Runs before 4 Nov 2026 paid untraded exports nothing |
| `"salazar"` | [`SalazarReward`](../../../core/env/reward.py) | the original code's reward as it ran there, with its constants (`W_GRID` and the other weights): the five parts of $R_{\text{base}}$ (grid, resource, trading, stability, economic), raised by the cooperation and contribution factors, minus the DSO penalty and, on the day's last step, the unmet-demand penalty; a step without trades pays only the no-trades penalty; the result is log-compressed ([P1] eq. 3). Its parts are kept per agent as `reward_*` entries of the step infos. It needs a `grid_capacity_kwh` and is not scaled by `reward_scale` |

`net_bill` stays the money an agent made whichever reward it learns from: the infos
and the results report it.

**`reward_scale`.** Defaults to $p_\text{utility} \cdot E$ with the day's highest
utility price: the bill for $E$ kWh bought from the DSO at its dearest, so a reward of
−1 is one such purchase. It is resolved once on the training days and reused
everywhere ([When results are made](../evaluation/index.md#when-results-are-made)).

**`terminal_value`.** With it, the last reward of the window adds the change of the
stored energy at `stored_kwh_value` per kWh, whichever the reward
([`Reward.stored_energy`](../../../core/env/reward.py)); `stored_kwh_value` is
needed with it. A one-day episode played with `options["day"]` is not changed by
it. [Episode end](index.md#the-environment-step) names the other day-end settings.

## The `salazar` reward

The papers give the reward in three forms: [P1] eq. 3-4, [P2] eq. 3, and the original
code, which is a third ([The two papers §3](../../original/issues/papers.md#3-reward)).
The environment offers **the code's form only**, not [P1] eq. 4 as printed (its
cooperation bonus is always 0 for factors in [0, 1], [E-14](../../original/issues/register.md#E-14))
and not [P2] eq. 3. For an agent that traded in the step
([`SalazarReward.agent_reward`](../../../core/env/reward.py#L372-L446)):

$$
\begin{aligned}
R_\text{base} &= 10\, r_\text{grid} + 1.5\, r_\text{res} + 5\, r_\text{trade} + 2\, r_\text{stab} + 3\, r_\text{econ} \\
\tilde R &= R_\text{base} \cdot \left(1 + \tfrac{1}{5} \ln\!\left(1 + f_\text{coop} \cdot f_{\text{contrib},i}\right)\right) \\
s &= 0.3 \cdot \max(\lvert \tilde R \rvert, 1) \\
x &= \tilde R - s \cdot \gamma_{\text{DSO},i} - s \cdot \gamma_{\text{UD},i} \\
r_i &= 20 \cdot \operatorname{sign}(x) \cdot \ln\!\left(1 + \lvert x \rvert / 20\right)
\end{aligned}
$$

The last line is [P1] eq. 3, the log compression. The parts, each with the function that
computes it:

| Part | Reads | Function |
|---|---|---|
| $r_\text{grid}$ | the agent's order against the market balance $B$ and the grid capacity $C$, the balance itself and the agent's effect on it | [`grid_balance_reward`](../../../core/env/reward.py#L133-L145) |
| $r_\text{res}$ | the share $x$ of the order executed: $x - 1.5\,(1 - x)$ | [`resource_reward`](../../../core/env/reward.py#L148-L153) |
| $r_\text{trade}$ | the order's fill by peers and by the DSO: $0.3 \cdot \text{local} + 0.3 \cdot \text{DSO}$ | [`trading_reward`](../../../core/env/reward.py#L122-L130) |
| $r_\text{stab}$ | the spread of its trade prices and how far its trades closed the balance: $0.3 \cdot \text{stability} + 0.7 \cdot \text{improvement}$ | [`stability_reward`](../../../core/env/reward.py#L156-L177) |
| $r_\text{econ}$ | its mean price against the clearing price and against the DSO's tariffs: $0.4 \cdot \text{efficiency} + 0.6 \cdot \text{gain}$ | [`economic_reward`](../../../core/env/reward.py#L180-L206) |
| $f_\text{coop}$ | the ten KPIs, weighted (they add up to 56), the same for every agent | [`cooperation_factor`](../../../core/env/reward.py#L210-L222) |
| $f_{\text{contrib},i}$ | its net trade against the balance (0.5), its prices against the clearing price (0.2), its share of trades with peers (0.3); 0.5 for an agent without trades | [`contribution_factor`](../../../core/env/reward.py#L225-L256) |
| $\gamma_{\text{DSO},i}$ | its share of energy traded with the DSO, times $15 \cdot \lvert B \rvert / C$ | [`dso_penalty`](../../../core/env/reward.py#L260-L267) |
| $\gamma_{\text{UD},i}$ | on the day's last step only: the squared share of its day's demand left unmet | [`demand_penalty`](../../../core/env/reward.py#L270-L278) |

A step in which the agent trades nothing skips all of this and pays $-5$ before the
compression, $-4.46$ after it ([E-19](../../original/issues/register.md#E-19)). The parts are
kept per agent as `reward_*` entries of the step infos.

**Where our version differs from the original code**, each marked in
[`reward.py`](../../../core/env/reward.py):

- the balance $B$ is the market's before the DSO clears. The original read a balance
  that is always 0 after clearing, so its grid terms never acted
  ([E-16](../../original/issues/register.md#E-16));
- the KPIs of $f_\text{coop}$ run over the day so far, as in the observation; the
  original took most of them over the step alone ([E-10](../../original/issues/register.md#E-10));
- the capacity $C$ is a setting (`grid_capacity_kwh`) that a run must give, since a
  SimBench network has no single one (RP-1g in the [open points](../../temp/open.md));
- the trading part's local weight is 0.3, as [P1] prints it; the original overwrote
  its 0.7 ([E-17](../../original/issues/register.md#E-17)).

Kept as in the original: the KPIs enter raw, so $f_\text{coop}$ is not in [0, 1]
([E-13](../../original/issues/register.md#E-13), [E-20](../../original/issues/register.md#E-20)),
and the unmet-demand penalty's constant is $p_\text{DSO}$, not [P1]'s
$p_\text{no\_trades}$ ([E-18](../../original/issues/register.md#E-18)); the code divides it
out again, so the penalty is $s$ times the squared unmet share.
