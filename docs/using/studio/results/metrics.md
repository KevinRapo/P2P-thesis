# Metrics

> Every number the Results page can show, once, in five groups. A row gives the
> column name, what it is, the time resolutions it exists at and the tab that shows
> it. Code: [`indicators.py`](../../../../core/runner/indicators.py) (`INDICATORS`) and
> [`ceiling.py`](../../../../core/runner/ceiling.py) for the references.

The groups answer different questions, and only the first is a verdict:

| Group | Question | Role |
|---|---|---|
| [A. Headline](#a-headline) | How good is the system? | The thesis's comparison: normalised, cited (Zhou et al. 2018) |
| [B. Money](#b-money) | What are the headline numbers made of? | The same outcome in EUR, against each baseline |
| [C. Market behaviour](#c-market-behaviour) | How did the result come about? | Explanation, not a score: more peer energy is not better in itself |
| [D. Salazar's KPIs](#d-salazars-kpis) | What does the paper report? | Description only: the `salazar` reward pays for some of them, so they cannot be evidence of success |
| [E. Grid](#e-grid) | What did the network see? | The power flow's view; the grid-method comparison |

**Resolution**: *step* (in the step tables, shown in *Step by step*), *day* (an
indicator: one number per run, policy and test day), *period* (the whole test period,
shown on each of its days, so a mean over the days is the period's value). Group A's
period values are the Validation overview's columns; their values per day are the
metrics of its *On the test days* chart. [Results](index.md#time-resolution) says why the
ratios have no step value.

**Rows**: the Validation overview has one column per *headline* indicator (marked ★);
every indicator of a tab is a *Metric* of its *On the test days* chart.

## A. Headline

Zhou et al. (2018) §4: three economic and three technical indices, each normalised so
that higher is better (except the peak-to-average ratio, before their normalisation).
Their weighted overall index is not computed: its weights are arbitrary, and it would
hide the trade-offs the six show.

| Index | Column | Definition | Resolution | Tab |
|---|---|---|---|---|
| Value tapping ★ | `vti`, `vti_day` | $\frac{\text{team money} - \text{non-P2P}}{\text{ceiling} - \text{non-P2P}}$, their eq. 17. 0: everyone on their own; 1: the most the horizon allows; below 0: worse than on their own | period, day | Validation |
| Participation ★ | `pi`, `pi_day` | Share of participants whose money beats their own non-P2P money, eq. 18: would they stay? | period, day | Validation |
| Equality ★ | `ei`, `ei_day` | $1 - \frac{\sum_n \sum_m \lvert x_n - x_m \rvert}{2N \sum_n \lvert x_n \rvert}$ on the **gains** $x_n$ over each participant's own non-P2P money ([`equality`](../../../../core/runner/indicators.py)). 1: the gain shared evenly. *Ours*: the paper's eq. 19-21 takes the Gini of income **levels**, shifted up to be positive, which mostly measures what the households own; equal losses also score 1 here, so read it with the VTI | period, day | Validation |
| Energy balance ★ | `energy_balance_index`, `..._period` | $1 - \frac{\sum_t \lvert \text{net}_t \rvert}{\text{consumption} + \text{production}}$, eq. 22-23: how little the community exchanged with the upstream grid, both ways | day, period | Validation, Grid |
| Peak-to-average ★ | `peak_to_average`, `..._period` | $\max_t \lvert \text{net}_t \rvert / \text{mean}_t \lvert \text{net}_t \rvert$ (EPARI, eq. 24); lower is flatter. Their power flatness index divides it by the worst of the runs compared | day, period | Validation, Grid |
| Self-sufficiency ★ | `self_sufficiency_index`, `..._period` | $1 - \frac{\sum_t \max(\text{net}_t, 0)}{\text{consumption}}$, eq. 26-28 | day, period | Validation, Grid |

$\text{net}_t$ is the participants' netted consumption at step $t$: their demand and
charging less their generation and discharging, summed over all of them, without the
network's other loads. Consumption and production are its two sides summed over the
horizon. The references are in [Results](index.md#baselines-and-references).

## B. Money

All in EUR, positive earned. A participant's money is its `bill`
([`net_bill`](../../../../core/env/reward.py)): its trades' profit after fees, its untraded
surplus at the feed-in tariff and its untraded deficit at the utility price (MP-1e).

| Metric | Column | Definition | Resolution | Tab |
|---|---|---|---|---|
| Team money ★ | `team_money` | The participants' `bill` summed | step, day | Validation |
| Gain over net position ★ | `gain_net_position` | Team money minus the run's own `net_position`, same day | day | Validation |
| Gain over zero | `gain_zero` | The same against `zero` | day | Validation (*On the test days*) |
| Stored change ★ | `stored_change_kwh` | kWh left in the batteries against the start of the day. Money alone favours draining them, so it stands next to team money | step, day | Validation |
| Better off than zero | `participants_better` | Participants whose `bill` beats their `zero` bill that day | day | Validation |
| Worst participant's gain | `worst_participant_gain` | The lowest of the participants' gains over `zero` | day | Validation |
| Fees, peer charge | `fees`, `peer_charge` | Eq. 8 grid fees, and the charge per peer kWh | step, day | Market |
| Buyers' and sellers' gain | `buyer_gain`, `seller_gain` | What the peer trades were worth against the tariffs: the buyer's utility price minus what it paid (net of the peer charge), the seller's price minus the feed-in tariff | day | Market |
| DSO money | `dso_money` | The DSO's energy money: its trades, the untraded energy at retail, every fee | day | Market |
| Share of the reachable gain | `reachable_share` | Gain over zero over what netting alone could add, without batteries: a rough, older VTI | day | the notebook only |

## C. Market behaviour

| Metric | Column | Definition | Resolution | Tab |
|---|---|---|---|---|
| Peer energy ★ | `p2p_kwh` | Energy traded between participants, stages 1 and 2 | step, day | Validation, Market |
| Stage 1 energy | `preference_kwh` | Of it, the pairs who named each other | step, day | Market |
| Bought from / sold to the DSO | `bought_from_dso_kwh`, `sold_to_dso_kwh` | Stage 3 | step, day | Market |
| Trading ratio ★ | `trading_ratio` | Energy bought and sold over what the participants needed to get or get rid of; above 1 is energy traded back and forth | day | Validation, Market |
| Unmet demand ★, spilled supply | `unmet_kwh`, `spilled_kwh` | Demand and surplus left untraded, settled at retail | step, day | Validation, Market |
| Local coverage | `local_coverage` | Share of the needed energy not taken from the DSO, capped at each participant's need at each step | day | Market |
| Self-sufficiency | `self_sufficiency` | Per participant, demand not supplied from the DSO, summed: unlike the index in A, without netting between participants | day | Market |
| Peer trades, mean trade, concentration | `peer_trades`, `mean_trade_kwh`, `market_concentration` | Number and mean size of peer trades; Herfindahl index of the sellers' shares | day | Market |
| Mean peer price, its place in the band | `mean_peer_price`, `peer_price_position` | Volume-weighted peer price; the same between the feed-in tariff (0) and the utility price (1) | step, day | Market |
| Battery throughput | `battery_throughput_kwh` | Energy into and out of the batteries | step, day | Market |
| Order shares | `no_order_share`, `buy_share`, `sell_share` | What the participants did, as a share of their steps | step, day | Market |
| Reputation at the end | `end_reputation` | Mean reputation after the day's last step | step, day | Market |

## D. Salazar's KPIs

The ten of [P1] eq. 19-27, from `signals.kpis`, the same function the observation and
the `salazar` reward read ([definitions](../../../methodology/environment/observation.md)).
Their labels can say more than the quantity: the register entries name the gap.

| KPI | Column | What is computed | Caveat |
|---|---|---|---|
| Social welfare | `social_welfare` | Turnover $\sum p \cdot q$, not surplus | [E-09](../../../original/issues/register.md#E-09) |
| Liquidity | `liquidity` | Energy traded, the DSO's trades included | MP-6a |
| Bid-ask spread | `bid_ask_spread` | Mean ask minus mean bid | |
| Price volatility | `price_volatility` | Standard deviation of the clearing price | [E-10](../../../original/issues/register.md#E-10): the window |
| Supply-demand imbalance | `supply_demand_imbalance` | Share of unmatched energy, over the orders | [E-08](../../../original/issues/register.md#E-08) |
| Grid congestion | `grid_congestion` | Mean line loading the fees used | |
| Coordination score | `coordination_score` | 1 minus the imbalance | |
| Coordination convergence | `coordination_convergence` | Stability of the last three steps' traded energy | |
| DER self-consumption | `der_self_consumption` | The peer share of the energy traded, not self-consumption | [E-12](../../../original/issues/register.md#E-12) |
| Flexibility utilisation | `flexibility_utilization` | Peer energy over the energy offered; $q_\text{available}$ undefined | MP-6a |

Resolution: step and day; tab: Market (*On the test days*).

## E. Grid

From the AC power flow of what the participants physically did, the whole network
included, whichever `grid.method` set the fees; a flow that did not converge counts 0.

| Metric | Column | Definition | Resolution | Tab |
|---|---|---|---|---|
| Highest line loading ★ | `highest_line_loading` | Worst line, worst step of the day, % | step, day | Validation, Grid |
| Hours over a limit ★ | `hours_over_limit` | Hours with a voltage or loading limit broken | step, day | Validation, Grid |
| Highest transformer loading | `highest_trafo_loading` | % | step, day | Grid |
| Lowest, highest voltage | `lowest_voltage`, `highest_voltage` | Worst bus and step, pu | step, day | Grid |
| Mean line loading | `mean_line_loading` | % | step, day | Grid |
| Upstream import, export | `grid_import_kwh`, `grid_export_kwh` | Energy from and to the upstream grid | step, day | Grid |
| Peak import, export | `peak_import_kw`, `peak_export_kw` | The highest of them, kW | day | Grid |
| Load factor | `load_factor` | Mean import over peak import | day | Grid |
| Peak reduction | `peak_reduction_kw` | `zero`'s peak import minus the policy's | day | Grid |
| Losses, trade losses, their ratio | `grid_losses_kwh`, `trade_losses_kwh`, `trade_loss_ratio` | The power flow's losses; [P1] eq. 18's estimate for the trades; that estimate per kWh traded | step, day | Grid |
| Fee signal error | `fee_error_mean`, `fee_error_worst` | Fee loading minus measured loading, percentage points: the grid-method comparison in one number | step, day | Grid |
| Flows not converged | `not_converged` | Steps whose power flow did not converge | step, day | Grid, a warning on Validation |
