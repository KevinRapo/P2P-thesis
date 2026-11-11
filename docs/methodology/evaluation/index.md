# How a run is judged

> What a trained policy is compared against, and how the two ends of the scale are
> calculated. The definitions of every number are in [Metrics](metrics.md), the
> files they come from in [What a run saves](files.md), and how the Studio shows
> them in [Results](../../using/studio/experiments/results/index.md).

## When results are made

A run produces numbers in three phases, and they answer different questions.

| Phase | When | Days played | Question |
|---|---|---|---|
| Training | Every iteration | Training days, sampled with exploration | Is the learner working? |
| Periodic evaluation | `eval_points` times, and at step 0 | Training days, on seeds training did not use | Is the policy improving? |
| Held-out evaluation | Once, after training | Every test day in order; batteries and reputations carry from day to day | How good is the final policy? |

**One set of scales per run.** The energy scale $E$ and the reward scale are worked
out once, on the training days
([`resolved_config`](../../../core/env/market_env.py#L366-L374)), recorded in
`run.json`, and reused by both evaluations
([`heldout_env_config`](../../../core/runner/launch.py#L406-L417)). Scales computed
on the test days would give observations and rewards a different meaning than in
training. Money and energy (profit, bill, kWh) are reported unscaled.

The thesis's results come from the held-out evaluation, in **money**: what the
participants paid and earned, fees included. Returns are in each reward's own units,
so they do not compare across rewards (RP-7a). On `obs_reward`, the policies with
the highest return were the ones that lost the most money:

| CTDE, test days | Team money per day, EUR | `team_return` |
|---|---|---|
| Bill reward | +0.77 | 0.09 |
| Salazar reward | −19.44 | 3175 |

## Three yardsticks

One **baseline** is a policy the evaluation plays on the same market and test days as
the trained one. Two **references** are calculated from the run's tables without
playing the market, so they have money only: no trades, fees or power flow.

| Name | Kind | What it is | Role |
|---|---|---|---|
| **`ceiling`** | calculated | One planner with perfect foresight for the whole community ([below](#the-ceiling)) | 1 on the VTI scale |
| **`non_p2p`** | calculated | Every participant alone with the retailer, its own battery timed with perfect foresight ([below](#the-floor-non_p2p)) | 0 on the VTI scale; each participant's own floor in PI and EI |
| **`net_position`** | played | The market's bidding rule ([`net_position_policy`](../../../core/env/market_env.py#L935-L974)): the battery first takes the surplus or covers the deficit it can; the rest is offered at $p_\text{FiT} + 0.3\,(p_\text{util} - p_\text{FiT})$ or asked for at $p_\text{util} - 0.3\,(p_\text{util} - p_\text{FiT})$, with no partner and no jitter | What learning has to beat |

Runs before 11 November 2026 also played `zero`, no orders at all. With the retail
settlement (MP-1e) it is `non_p2p` with passive batteries, and the rule moves the same
energy, so it added nothing the other three do not show; their `zero` rows are left
out when their tables are read.

- **`net_position` is the rule without its noise.** The rule for non-RL
  participants ([`rule_based_bid.net_position`](../../../core/market/agent/rule_based_bid.py#L64-L108))
  adds a price jitter and a preferred partner (`bid_jitter`, `partner_preference`).
  The baseline keeps the margin of 0.3 and drops both, so it is the same in every run.

## The ceiling

Money paid between peers stays inside the community: what one pays, another
receives. The community's money therefore depends only on what it buys from and
sells to the DSO. Generation and demand are fixed, so two things are left to choose:
**netting**, one participant's surplus covering another's deficit, and **when each
battery charges and discharges**. A planner who sees the whole period chooses both
with a linear program ([`optimise`](../../../core/runner/ceiling.py#L98-L227)):

$$
\begin{aligned}
\max\; & \sum_t \left( p_{\text{FiT},t}\, e_t - p_{\text{util},t}\, g_t \right) \\
\text{s.t.}\; & g_t - e_t + \sum_b \left( d_{b,t} - c_{b,t} \right) = -\sum_i \left( G_{i,t} - D_{i,t} \right) \\
& E_{b,t} = E_{b,t-1} + \eta_c\, c_{b,t} - d_{b,t} / \eta_d \\
& E_{b,\min} \le E_{b,t} \le E_{b,\max}, \qquad 0 \le c_{b,t},\, d_{b,t} \le P_b\, \Delta t \\
& g_t,\, e_t \ge 0, \qquad E_{b,T} \ge E_{b,0}
\end{aligned}
$$

where $g_t$ and $e_t$ are the community's import and export at step $t$; $c_{b,t}$
and $d_{b,t}$ the energy battery $b$ draws from and gives to its bus; $E_{b,t}$ its
stored energy, with [P1]'s efficiencies (eq. 16) and limits (eq. 15c-d); $G_{i,t}$
and $D_{i,t}$ participant $i$'s generation and demand. The last condition keeps the
planner from earning money by emptying the batteries.

**Why it is a bound.** Whatever the market does, its imports, exports and battery
moves satisfy these constraints: every outcome is one feasible point of the program.
Fees only lower the market's money, so no policy can make more, with two exceptions:

- the **zone bonus** is a negative fee and can lift the market's money above it;
- a **peer charge** makes netting cost money, which the program does not know. The
  bound still holds but can no longer be reached, so the VTI reads low. Before any
  run with a charge, the program has to charge peer netting too (RP-7g;
  [Tariffs](../market/tariffs.md#what-depends-on-it)).

The program also ignores the grid's limits and losses.

## The floor: `non_p2p`

The conventional case of Zhou et al. (2018, §3.1, §4.1): every participant on its
own with the retailer. It is the same program, solved **once per participant** with
only its own generation, demand and battery, and summed
([`alone_days`](../../../core/runner/ceiling.py#L364-L404)). Nobody nets with
anybody. A participant without a battery has nothing to choose: its surplus earns
$p_\text{FiT}$ and its deficit costs $p_\text{util}$.

The gap between floor and ceiling is exactly the value of netting, together with
what shared timing of the batteries adds to it. That gap is what a market can
capture at most.

## Two horizons

Each reference is calculated over two horizons:

- **The test period.** The batteries carry from day to day, as the evaluation plays
  them, and start where the evaluation started them
  ([`ceiling_days`](../../../core/runner/ceiling.py#L326-L361)).
- **Each test day.** Every day is its own horizon, as in Zhou et al.'s one-day
  cases: each battery starts the day at the scenario's initial charge and ends it at
  least as full ([`day_references`](../../../core/runner/ceiling.py#L407)).

The played policies' batteries carry over between days, so a day's value for them
also holds energy moved in from the day before, which that day's references cannot
use. Each policy's `stored_change_kwh` shows how much energy it left in the
batteries.

## From money to indices

From the money of a policy, the floor and the ceiling, three indices of Zhou et al.
(2018) judge a run ([Metrics](metrics.md#a-headline)):

$$
\text{VTI} = \frac{\text{team money} - \text{non-P2P}}{\text{ceiling} - \text{non-P2P}}
$$

- **VTI**, value tapping: the share of the reachable value the policy captured. 0 is
  everyone on their own, 1 the ceiling, below 0 worse than on their own.
- **PI**, participation: the share of participants whose money beats their own
  non-P2P money. Would they stay in the market?
- **EI**, equality: how evenly the gains over each participant's own non-P2P money
  are shared.

Each exists over the test period (`vti`, `pi`, `ei`) and per test day (`vti_day`,
`pi_day`, `ei_day`). The period value weights the days by what was at stake.
