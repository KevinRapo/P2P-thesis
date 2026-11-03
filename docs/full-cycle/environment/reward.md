# The reward

> What a played market step is worth to each agent. The default is the net bill;
> the original code's reward exists as an option. The reward only reads what the
> market did ([reward.py](../../../core/env/reward.py)); it changes nothing.

## E2. Reward

Per agent, from its `ParticipantOutcome`:

$$
r_i = \frac{\text{profit}_i - p_\text{utility} \cdot \text{deferred demand}_i}{\text{scale}}, \qquad \text{scale} = \bar p_\text{utility} \cdot E
$$

where profit is eq. 14 net of fees, deferred demand is what its trades and battery
left uncovered (drawn untraded from the upstream grid, charged at the step's utility
price $p_\text{utility}$), $\bar p_\text{utility}$ is the day's highest utility
price ([`Dso.tariff_range`](../../../core/market/dso.py#L107-L113)) and $E$ the
`energy_scale`, the largest generation or demand of any participant in any step of
the training days. Both scales are resolved once per run and reused for every later
environment of the run, held-out days included ([The run contract](../../config/run-contract.md)).
CTCE's `CTCEEnv` sums the agents' rewards, $R = \sum_i r_i$; DTDE and CTDE keep
each agent's own.

## What the reward reads

The last column of the three signal tables in [Observation](observation.md) shows which signals the `"salazar"` reward
([`SalazarReward.agent_reward`](../../../core/env/reward.py#L367-L441), the original
code's) also uses, so that the observational ones stand apart. It describes that
reward only: the `"bill"` reward calls none of these signals, though it reads three of
the same quantities from the step's record: `utility_price`, the step's `profit` and
`deferred_demand_kwh`.

| In the reward | Signals | Meaning |
|---|---|---|
| a weight | 10 | every KPI, through `signals.kpis` and [`cooperation_factor`](../../../core/env/reward.py#L205-L217): its weight in $f_{\text{coop}}$ ([`COOPERATION_WEIGHTS`](../../../core/env/reward.py#L65-L76), adding up to 56), and $1 - x$ where lower is better |
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
| `"bill"` (default) | [`NetBillReward`](../../../core/env/reward.py) | the net bill: `(profit − p_utility · deferred_demand) / reward_scale`. Settlement leaves untraded energy unpriced, so an untraded import is charged at the step's utility price and an untraded export earns nothing; buying and selling then pay off only against these two outside options |
| `"salazar"` | [`SalazarReward`](../../../core/env/reward.py) | the original code's reward as it ran there, with its constants (`W_GRID` and the other weights): the five parts of $R_{\text{base}}$ (grid, resource, trading, stability, economic), raised by the cooperation and contribution factors, minus the DSO penalty and, on the day's last step, the unmet-demand penalty; a step without trades pays only the no-trades penalty; the result is log-compressed ([P1] eq. 3). Its parts are kept per agent as `reward_*` entries of the step infos. It needs a `grid_capacity_kwh` and is not scaled by `reward_scale` |

`net_bill` stays the money an agent made whichever reward it learns from: the infos
and the results report it.

**`reward_scale`.** Defaults to $p_\text{utility} \cdot E$ with the day's highest
utility price: the bill for $E$ kWh bought from the DSO at its dearest, so a reward of
−1 is one such purchase. It is resolved once on the training days and reused
everywhere ([The run contract](../../config/run-contract.md)).

**`terminal_value`.** With it, the last reward of the window adds the change of the
stored energy at `stored_kwh_value` per kWh, whichever the reward
([`Reward.stored_energy`](../../../core/env/reward.py)); `stored_kwh_value` is
needed with it. A one-day episode played with `options["day"]` is not changed by
it. [Episode end](index.md#the-environment-step) names the other day-end settings.
