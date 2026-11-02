# Results plan

How a run's results are saved, compared and shown: thesis objective 3, "determine the
form in which the tool must present and output the simulation results". It settles
[RP-7](rl.md) and [MP-6a](market.md). What is saved and shown today is in
[Results](../config/results/index.md); this page is what changes.

**Status: built, not committed.** Stages 1 to 4 are in the code, reviewed by the reward
session. As built, `bought_kwh` and `sold_kwh` stay, with the peers' part next to them;
`charge_kwh` and `discharge_kwh` were added; the losses' share was dropped for want of a
sound denominator; `overview` above is `side_by_side` in the code; there are nine
headlines, and no direction per indicator, since no tab reads one.

## The idea

Results live on three levels. Each number sits on the lowest level that can hold it, and
only the first is permanent.

| Level | What it is | Computed | Example |
|---|---|---|---|
| 1 Saved | Raw tables of one run | During the run | `demand_kwh` per step and participant |
| 2 Indicator | One number per run, policy and test day | When read | Team money, highest loading |
| 3 Comparison | Runs side by side, or their difference | When read | Pruned minus paper, within each reward |

So stage 1 must be right before a run; stages 2 and 3 can change later and still apply
to the runs already made.

## Stage 1: what is saved

Every test day is kept step by step, for every policy. `results_detail` and `trace_days`
go, so there is one format. The periodic evaluation stays per day.

| Change | Table | Why |
|---|---|---|
| Rename `heldout_trace_steps`, `heldout_trace_agents` to `heldout_steps`, `heldout_agent_steps` | | They are no longer a special case |
| `random` on the test days | All held-out tables | RP-7d; the floor of the comparison |
| `feed_in_tariff`, `utility_price` | Steps | Prices stay on disk by name, and mean peer price needs them |
| `peer_price`, the step's traded mean, empty without a peer trade | Steps | `clearing_price` carries over when nothing trades, so it cannot be averaged |
| `max_trafo_loading_percent` | Steps | The power flow gives it and it is dropped |
| `voltage_violations`, `line_violations` in place of the sum | Steps, days | One count hides which limit broke |
| `demand_kwh`, `generation_kwh` | Agent steps | Coverage, trading ratio and the reference need them; only what was left over is saved |
| `peer_bought_kwh`, `peer_sold_kwh`, `dso_bought_kwh`, `dso_sold_kwh` in place of `bought_kwh`, `sold_kwh` | Agent steps, days | A participant's peer and DSO trades are merged today |
| `fees` | Agent steps, days | A participant's money cannot be split without them |
| The ten KPIs, from `signals.kpis` | Days | One definition; they need the orders, which no table holds |
| Reward parts, by a `Reward.parts` hook: empty for the bill; for Salazar the five `R_base` parts, the boost, the DSO and demand penalties | Agent steps | Nothing else can explain a Salazar result; they cannot be recomputed later |

Left out: values per line and bus, large and not needed by any indicator; the
participants' share of the upstream exchange, which the power flow does not separate.

Size: 3.5 MB per run for the four policies, measured from the current tables, with the
new columns perhaps 4.5 MB; about 70 MB for 16 runs against 640 MB on the cluster. The
evaluation takes no longer, because every step is in memory already.

## Stage 2: the indicators

A new [`core/runner/indicators.py`](../../core/runner/), plain pandas, no Ray: one list
`INDICATORS`, one entry per indicator, with its name, unit, tab (`validation`, `market`,
`grid`), whether it is a `headline`, and the function that
computes it from a day's tables. `day_indicators(results)` gives one long table: run,
policy, day, indicator, value. The adapter caches it by the files' times, since 16 runs
are read by every tab. The tabs read this list, so `MARKET_METRICS` and `GRID_METRICS`
go. A day with a non-converged flow is marked, because such a step counts 0 and a peak
would read low.

| Tab | Headline | Others |
|---|---|---|
| Validation | Team money; gain over `net_position`; stored change; participants better off than `zero` | Gain over `zero`; share of the reachable gain |
| Market | Peer kWh; trading ratio; unmet energy | Spilled energy, local coverage, mean peer price and its place in the band, fees, battery throughput, reputation at the day's end, no-order, buy and sell shares, the ten KPIs |
| Grid | Highest loading; hours over a limit | Upstream energy, peak import and export, transformer loading, voltage extremes, losses and their share, fee signal error |

At most eight headlines, a column each in the overview. Defined as:

- **Team money**: the participants' `bill` summed. Positive is earned.
- **Gain**: team money minus the baseline's, paired per day. `net_position` is the real
  bar; `zero` flatters, because selling to the DSO already beats it.
- **Stored change**: the energy left in the batteries against the start, shown next to
  money. Batteries carry across the test days and a stored kWh is worth 0, so money
  alone favours draining them. On `obs_reward` this does not change a ranking: valued at
  the mean utility price, no version overtakes another, and pruned minus paper moves by
  at most 0.2 EUR per day. So it stays a column, not a correction.
- **Share of the reachable gain**: gain over `zero` as a share of the gap to perfect
  hourly netting without batteries: the community's deficit at `p_utility` and its surplus
  at `p_FiT`, in closed form. A policy with batteries can exceed 1. Only for comparing
  across scenarios or price sets.
- **Trading ratio**: energy bought and sold over what participants needed to. Above 1
  is energy traded back and forth.
- **Fee signal error**: fee loading against measured loading, mean and worst step.

## Stage 3: the comparison

**Any runs can be compared.** No run is refused for differing in seed, days, scenario,
reward or anything else. How far a comparison can be trusted depends on what differs, so
the tool says what differs instead of deciding for the reader. There are three views of
the same table, from the freest to the strictest:

| View | Works on | Cell | Answers |
|---|---|---|---|
| Side by side | Any runs | The indicator's value | What did each one do? |
| Against its own baseline | Any runs | The value minus the run's own `net_position` or `zero` | Which beat its own bar by more? |
| Difference | Any runs; paired when they match | The value minus a reference | How much does this change make? |

### Side by side

The default, and the view of the overview table. `overview(indicators, rows)` gives a row
per group and a column per indicator. *A row per* picks the group: run, or version with
seeds pooled, or any setting that differs among the ticked runs (paradigm, reward,
observation, prices, grid method, experiment). Nothing is paired: each run's number is
the mean over its own test days.

Above the table, a line names what differs, from the existing `differing_settings`: "These
rows differ in: scenario, test days, prices". A run lacking a column, such as an older
run, leaves an empty cell.

Baselines depend on the days and the prices, so there is one baseline row per distinct
set of them, not one overall. Inside a set they are deterministic and have no spread.

### Against its own baseline

Every run plays its baselines on its own days and prices, so gain over its own
`net_position` needs no matching run: it is what makes two scenarios or price sets
comparable at all. A switch turns the cells of the money indicators into this gain, or
into the share of the reachable gain. *Per participant* divides by the number of
participants, for networks of different size.

### Difference

`difference(indicators, reference, by=None)`. The reference is any row of the table: the
cells become each row's difference from it. With `by="observation"` and
`reference="paper"` it works per factor instead: the difference from the reference level
inside every combination of the other settings. That is what shows pruned minus paper
within each reward side by side, and so the interaction.

Pairing is used where it can be, and shown:

| The two sides | Computed as | Shown as |
|---|---|---|
| Same days and prices | Per seed, the mean of the daily differences | Paired |
| Different days or prices | The difference of the two means | Unpaired |

A paired difference removes the large day-to-day variation. An unpaired one keeps it, so
its uncertainty is wider, and across different days or prices it says more about the
days than about the method. Both are computed; the label says which it is.

### Statistics

The same in all three views. One number per seed, each the mean over its days, then work
over seeds. Days are not independent, and seeds share them, so days never go into an
interval. Below 5 seeds: the mean and every seed's value. From 5: the mean with a
percentile bootstrap over seeds. No IQM: with 5 seeds on one task it trims little, and it
hides a failed seed. This settles RP-7b.

Seeds of a row can be anything: a row pooling different days or scenarios is allowed,
and the line above the table says so. Different seed counts per row are allowed too;
each cell shows its own.

### What a table cannot show

A day's shape or a loading curve belongs to the step views. The notebook calls the same
functions for the thesis's figures.

## Stage 4: the tabs

Four tabs, each with one job, sharing one selection: version, seed, policy and day.
Picking in one tab keeps the selection in the next, so there are no links to maintain.

| Tab | Days | Shows |
|---|---|---|
| Validation, opened first | Test | The overview of any ticked runs: *A row per*, a column per headline, the line naming what differs, one baseline row per set of days and prices; the switch to own baseline; the reference picker for differences; the gain per day in money |
| Learning | Training | Training return with the evaluation curve in return and in money (`evaluation_agents.csv` has the bill per point); the learner panels; the action parts |
| Market | Test | The daily panel of its indicators, per version and per participant; then the selected run, step by step: market energy, prices, orders, partners, batteries |
| Grid | Test | The same daily panel; then the selected run, step by step: loading, fee loading against measured, voltages, exchange |

A row can pool seeds, so the step views default to its median seed by team money, with
a seed picker. Market and Grid share one daily-panel component, driven by the
indicators' `tab`, and one step chart.

| Removed | Because |
|---|---|
| Explore | The other tabs cover what is needed |
| *During training* on Market and Grid | They have no step data, and "did it learn?" is Learning's question |
| *During training* on Validation | Moved to Learning |
| Return columns of the run table | Replaced by team money, the measure that compares across rewards |
| `heldout_days`, the phase handling | Replaced by the indicators |

Later, if the time is there: the panels of Learning's missing list, such as speed.

### Live view

The live view keeps working, and the new tables do not change what it transfers during
training. Measured on `obs_reward` (16 runs, 37 MB) from this PC:

| Step | Cost |
|---|---|
| One refresh with nothing new | 0.7 s |
| Bringing an empty copy up to date, all 145 files | 6.7 s, about 5.5 MB/s |
| New rows per refresh, 8 runs training, at 30 s | About 50 KB |
| `learner_metrics` on this PC, 16 runs, files already read | 3.6 s, at every refresh of Learning |

So the link is not the limit; the limit is `learner_metrics` building a table of 2 million
rows at each refresh. Two changes follow: refresh every 30 s instead of 10, and build
only the runs whose `metrics.csv` changed.

`heldout_steps` and `heldout_agent_steps` join the followed files. They are written once,
when a run ends, so each arrives whole, a few MB at this size. On a much larger run a
refresh could outlast its 60 s limit, but the files finished by then stay and the next
refresh goes on from there, so it only delays them.

## Stage 5: the last look at what is saved

**Status: proposed, not built.** A final pass over stage 1, against the original's
figures and against what a network replay needs, so that what is saved stops changing.

The test: a table is saved if a question in the thesis needs it, it cannot be computed
from what is saved without reimplementing a market rule, and it does not slow training.
Everything here is written only by the held-out evaluation. Reviewed by the reward
session; its changes are in.

| Add | One row per | Holds | Needed for | Size per run |
|---|---|---|---|---|
| `heldout_trades.csv.gz` | policy, day, step, trade | Buyer, seller, price, kWh, stage, distance, loss, buyer and seller fee, and the fee's parts (`GridFees`) | Who traded with whom, trade prices, how each fee term acts: the mechanism by which a grid method changes behaviour | At most 1.5 MB, estimated |
| `heldout_grid.csv.gz` | policy, day, step | Voltage per bus, measured loading per line, loading per transformer; with `grid.method = "graph"` also the fees' loading per line | The network replay; which line is congested; the graph model against the power flow on every line | 2.3 MB measured before compression |
| Two columns of `heldout_agent_steps` | | `action_quantity`, `action_price`: the raw network outputs | What the policy asked for without an order: the no-order threshold is an open choice | 0.3 MB, estimated |
| Three columns of `heldout_agent_steps` | | `reputation_reliability`, `reputation_fairness`, `reputation_grid` | Whether reputation means anything (M-45) | 0.4 MB, estimated |

`run.json` gains nothing, but a run also saves `git diff` beside it, so a run with
uncommitted changes can be rebuilt. With these a run keeps about 10 MB, about 170 MB for
16 runs, less when compressed; a 43-participant 15-minute run should be measured before
this is called settled. Not added: step tables of
the periodic evaluation, which nothing would read; the observation, which is computed
from what is saved in all that a thesis question needs; anything per step in training.

### What to take from the original

[P1] shows four results figures, all from non-learning agents, and the original's
`plotter.py` has more.

| Original | Take? | As |
|---|---|---|
| Fig. 5: distribution of clearing prices and trade volumes | Yes | Market: a box per version of trade sizes and of prices as a place in the tariffs' band, because with day-varying tariffs a raw price shows the spot price |
| Fig. 6: grid balance over time | Yes | Market, step by step: offered minus asked |
| Fig. 7: peer-to-peer ratio over time | Yes | Market, step by step |
| Fig. 8: trading network | Yes | Grid replay: the trades on the real network |
| `spatial_heatmap`: agent-to-agent trading matrix | Yes | Market: the common heatmap, which works at 43 participants, unlike a network drawn from trades |
| Market concentration | Yes | Market indicator, from traded energy |
| Welfare Gini | No, as written | Bills change sign and sum near 0, and mainly measure who owns PV. Worst participant's gain instead |
| Load factor, peak reduction | Yes | Grid indicators: mean over peak import, and peak against `zero`, labelled as batteries' doing (see below) |
| Self-sufficiency | Yes, as its own | Share of demand met by own generation, peers and batteries; not the same as `local_coverage` |
| DSO dependency, avoided DSO cost | Already covered | DSO energy, the gain over `zero` |
| Summary dashboards of bars | No | The overview table does this |
| Composite scores: stability index, emergent efficiency, strategy alignment and the like | No | Weighted mixes of the numbers above, with no definition in the papers |
| Trend slopes; KDE, CDF and histogram variants | No | Same information as the box and the curves |

### Replay from a checkpoint

A runner command plays a finished run's held-out evaluation again from its checkpoint,
and checks that it reproduces the saved team money. That is what lets the saved tables
stop changing: anything missed can be produced later, without training. It also gives
what no table can: a policy trained under one grid method played under the other, or on
other prices. Checkpoints are not synced, so they must be kept on the cluster, about
50 MB per run.

### What the grid tables can show

A participant's injection is built from its generation, demand and battery, never from
its trades ([`der.py`](../../core/market/agent/der.py)). So peer trades change no flow:
only battery dispatch does, and only 5 of 13 participants have one. Versions differ in
the replay only through batteries, and a grid method reaches the network only that way;
its effect on behaviour is in the fees of `heldout_trades`. Spilled surplus still flows.

### What the reader adds

- **The network replay**, on Grid: the real network with lines coloured by loading, buses
  by voltage, participants ringed and the step's trades drawn, stepped by a slider or
  played through a day, for any run and policy. It reuses `NetworkChart`, and needs line
  colours added.
- **The mean day**, in the step views: *All days* in the day selector, the mean of each
  step over the test days, so that a fortnight has a shape, not only a day.

## Order

| Stage | Before tomorrow's runs? | Done when |
|---|---|---|
| 1 Saved | Yes: it cannot be added to a finished run | A short cluster run writes every new column for every policy |
| 2 Indicators | No | The `obs_reward` numbers come out of `day_indicators` |
| 3 Comparison | No | It reproduces the pruned minus paper table, and shows two experiments with different days side by side |
| 4 Tabs | No | Validation shows the overview for `obs_reward` |

`obs_reward` keeps its format and gets no special reader: indicators it has no columns
for are simply empty. Its checkpoints stay on the cluster, so its held-out evaluation can
be played again later if its step tables are wanted.
