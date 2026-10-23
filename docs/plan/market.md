# The market plan

> Status: plan, 22 Oct 2026. Scope: the V2 market step (`core/market/`, the grid
> in `core/grid/`) on `config/scenarios/validate_market.json`. It orders the work
> and names the decisions; it does not take them. Decisions go into the
> [decision log](decisions.md); how the pages fit together is in [Plans](index.md).
>
> Everything here is about **this implementation**. Each stage says what the V2
> code does now and links to it; what was wrong in the original MARLEM, and why
> V2 does it differently, stays in the MARLEM tab. Only questions still open in
> V2 are listed.

## Why the market first

The market decides what an agent *can* do (the order bounds, what the battery does
after a trade), what it *earns* (prices, fees, untraded energy) and what it can
*know* (reputation, prices). Each of these is a choice of the RL layer's action,
reward or observation. Settling the market first turns the [RL plan](rl.md)'s
first stage into reading off what this plan hands over.

**Rules for working through it** (the same as the RL plan's)

1. **One stage at a time.** Done when its check passes and its decisions are in
   the [decision log](decisions.md).
2. **Parking lot** at the end for anything that belongs to another stage.
3. **No RL during this plan.** The market is checked with its own bidding rule,
   by hand in the Studio's Step page, and in notebooks; never through a trained
   policy.
4. **Read the system from the [full cycle](../full-cycle.md).** Each stage names
   the phases it covers; a stage that changes code updates those phase cards.

## Overview

| # | Stage | Question it answers | Full cycle | Size | Status |
|---|---|---|---|---|---|
| 0 | The reference | Does the full cycle describe the V2 code, and on which scenario do we work? | all | S | not started |
| 1 | Energy and the battery | Does every kWh add up, and what should the battery do after a trade? | [0](../full-cycle.md#0-before-the-day-reset), [1](../full-cycle.md#1-inputs), [4](../full-cycle.md#4-settlement) | M | not started |
| 2 | Orders | Which orders can a participant place, and what happens to one it cannot? | [2](../full-cycle.md#2-orders) | S | not started |
| 3 | Clearing and prices | Who trades with whom, at which price? | [3](../full-cycle.md#3-clearing) | M | not started |
| 4 | Grid and fees | What does the grid cost a trade, under each grid method? | [5](../full-cycle.md#5-grid), [6](../full-cycle.md#6-fees) | L | not started |
| 5 | Reputation | Does reputation change anything within a day? | [8](../full-cycle.md#8-reputation-and-advance) | M | not started |
| 6 | The market as a whole | Over whole days: does it run clean, and how good are simple rules? | [7](../full-cycle.md#7-record) | M | not started |

Status is one of *not started*, *in progress (since date)* or *done (date)*.

The order follows the money: energy accounting first (every amount below depends
on it), then what may be ordered, then how orders are matched and priced, then
what the grid adds, then reputation (which reads trades and the grid), then whole
days.

---

## Stage 0: the reference

**Question.** Does the reference describe the code that runs, and on what do we
check it?

**Now.** The [full cycle](../full-cycle.md) still opens with a "V2 note": its
environment section describes V1's two-number action. The reference scenario is
`validate_market.json`: five households on `1-LV-rural1--0-sw`, P1 and P5 with
PV and a 10 kWh battery **without a power limit** (`max_power_kw: null`), hourly
steps, June 2016 to train, 1-14 July 2016 to test.

**Check.**

- The full cycle describes V2 (the note removed, the environment section with the
  mixed action, line links current).
- `python -m pytest tests/market` passes.
- One step in the Studio's Step page shows the phases in the full cycle's order
  with the same quantities.

**Decisions.**

- **MP-0a** The reference scenario and days. Its batteries: keep them unlimited,
  or give them SimBench's sizing (power = capacity ÷ 2 h,
  [`simbench_battery`](../../core/config/placement.py#L35-L40); a SimBench storage
  unit brings its own limit, [`storage_battery`](../../core/config/placement.py#L49-L58)).
  Hourly or 15-minute steps (both supported, `grid.step_hours`).

**Hands to RL.** The scenario and the days every RL stage uses.

---

## Stage 1: energy and the battery

**Question.** Does every kWh add up, per participant and for the network, and is
the battery's role the one we want?

**Now.** After the trades a participant has
$B = (G - D) + (\text{bought} - \text{sold})$ left at its bus
([`Participant.settle`](../../core/market/agent/der.py#L226-L260)). A surplus
charges the battery, a deficit discharges it, within its room and power limit
([`charge`, `discharge`](../../core/market/agent/battery.py#L121-L138)); the rest
is exchanged with the upstream grid untraded (`external`). The battery has no
decision of its own: the agent steers it only through its trade quantity
(selling beyond the surplus discharges it, buying beyond the deficit charges it,
trading exactly the net position leaves it alone). Untraded energy has no price in
the market's profit; the RL reward charges an untraded import at the utility price
([`MarketEnv.step`](../../core/env/market_env.py#L355-L358)). Every day starts at
the initial state of charge (0.5).

**Check.**

| Check | Pass when |
|---|---|
| Balance per participant and step | $G - D + \text{bought} - \text{sold} = \text{charge} - \text{discharge} + \text{external}$ for every participant and step of a day |
| Balance of the network | The participants' external exchange plus the background matches the power flow's upstream exchange, up to the line losses |
| A battery day by hand | One battery's state of charge over 24 steps, recomputed from its charges and discharges with the efficiencies |
| The settlement cases | The four cases above, and a household with a deficit that sells from its battery (it then imports its own load untraded) |

**Decisions.**

- **MP-1a** The battery as a passive buffer after the trades (now), or a decision
  of its own (charge or discharge independently of the trade).
- **MP-1b** Untraded energy: what an untraded import costs and an untraded export
  earns, in the market's profit and KPIs, not only in the RL reward. Today the
  market counts discharge towards "demand satisfied" and leaves the untraded
  import unpriced.
- **MP-1c** The battery at the end of the day: energy left at midnight is worth
  nothing, because the next day starts at 0.5 again. Keep, value the stored energy
  at the end, or carry the state of charge over between days.

**Hands to RL.** What the agent physically controls; the terms of the reward
(MP-1b); the end-of-day effect (MP-1c), which a learning agent will exploit if it
pays.

---

## Stage 2: orders

**Question.** Which orders can a participant place, and what happens to one it
cannot place?

**Now.** An intent is limited to eq. 15
([`max_sell_kwh`, `max_buy_kwh`](../../core/market/agent/der.py#L178-L184):
the surplus or deficit plus what the battery can give or take) and to the
scenario's price and quantity bounds; the cut is noted, an order at or below the
minimum quantity is dropped
([`_validate`](../../core/market/lem.py#L465-L490)). Submitting nothing is
allowed. The scenario's price bounds are 0 and 1, the tariffs 0.08 (FiT) and
0.30 (utility).

**Check.** An intent beyond eq. 15 is cut to the bound and noted; one below the
minimum is dropped; the recorded order is the submitted one, after the cut.

**Decisions.**

- **MP-2a** Infeasible orders in general: cut them to the bound (now), reject
  them, or penalise them.
- **MP-2b** The price bounds against the tariffs. A sell asking more than 0.30
  or a buy bidding less than 0.08 can never trade with a peer and goes to the DSO
  at its tariff; bound prices to [FiT, utility], or keep [0, 1].
- **MP-2c** Selling from the battery while the household itself has a deficit:
  eq. 15 allows it (a surplus of 0 plus the dischargeable energy). Keep, or let a
  household sell only after its own load is covered.

**Hands to RL.** The action's bounds and meaning: the quantity as a share of the
eq. 15 bound, the price range (MP-2b), what an out-of-range action does (MP-2a).

---

## Stage 3: clearing and prices

**Question.** Who trades with whom, in which stage, and at which price?

**Now** ([clearing.py](../../core/market/clearing.py)):

1. [**Preferences**](../../core/market/clearing.py#L110-L134): a buyer and a
   seller that named each other trade first, if bid ≥ ask. An order naming the
   DSO waits for stage 3.
2. [**Double auction**](../../core/market/clearing.py#L140-L170): bids from the
   highest price down, asks from the lowest up, ties broken by reputation, then
   arrival; pairs trade while bid ≥ ask.
3. [**DSO**](../../core/market/dso.py#L269-L290): every open order clears with
   the DSO, sells at FiT and buys at the utility price. Every order is therefore
   executed in full; only its price depends on the market.

A pair's price follows the scenario's mechanism (`average`: the midpoint of bid
and ask, [clearing_price.py](../../core/market/clearing_price.py)). The step's
clearing price is the volume-weighted price of the peer trades
([`_clearing_price`](../../core/market/lem.py#L524-L531)). Orders made by the
market's own rule name a partner by a 50/50 score of reputation and closeness
([`choose_partner`](../../core/market/agent/der.py#L187-L223)); an RL agent's
partner is never replaced.

**Check.** A small hand-cleared example per stage: two agents that name each
other, a double auction with partial fills, the rest to the DSO; each trade's
price; the step's clearing price.

**Decisions.**

- **MP-3a** The pricing mechanism for every experiment (`average` now; buyer,
  seller, bid-ask spread, Nash bargaining and proportional surplus exist).
- **MP-3b** The rule-based partner score: the weight of reputation against
  closeness (0.5 now).

**Hands to RL.** What a price and a partner choice earn; what `price_ref` (the
clearing price) means; that stage 1 needs mutual naming on opposite sides, the
coordination the partner action must learn.

---

## Stage 4: grid and fees

**Question.** What does the grid add to a trade, and how do the two grid methods
differ on the same step?

**Now.** After the trades, the AC power flow runs on what the participants
physically did. Every trade then pays eq. 8 on its path
([`Dso.fees_of`](../../core/market/dso.py#L161-L185),
[`Dso.charge`](../../core/market/dso.py#L238-L266)), split 50/50 between
buyer and seller for a peer trade:

| Part | V2 now | Scenario value |
|---|---|---|
| Congestion | above the threshold, on the highest loading along the path | factor 0.5, threshold 0.8 |
| Thermal | from its own threshold, capped | threshold 0.2, cap 0.3 |
| Voltage | $f_\text{volt} \cdot d_{ij}$, capped (`voltage_drop = "distance"`; `"measured"` uses the power flow's voltages) | factor 0.15, cap 0.05 |
| Transmission | the trade's loss $\kappa \cdot d_{ij} \cdot q$ at the trade price | κ 0.03 per km |
| Zone bonus | a discount when both ends hang on the same feeder | 0.15 |
| Imbalance | only trades with the DSO, only when they worsen $B_\text{grid}$ = offered − asked ([`imbalance_fee`](../../core/market/dso.py#L187-L200)) | 0.15 |

A trade with the DSO runs from the participant to the transformer's busbar. With
`grid.method = "graph"` the fees read the line loading of the paper's graph model
from the step's trades instead of the power flow's
([`_grid_signal`](../../core/market/lem.py#L565-L578),
[graph.py](../../core/grid/graph.py)); the power flow still runs and is recorded.

**Check.** A step with a loaded line by hand: each fee part of one trade; the
same step under both grid methods; a DSO trade's path and fee.

**Decisions.**

- **MP-4a** The transmission fee: the lost energy at the trade price (now), or a
  per-kWh-km network charge as in the P2P literature.
- **MP-4b** The imbalance fee. With $B_\text{grid}$ counted from the orders, a
  DSO trade worsens it only when an order on the short side found no peer
  (its price did not match); the DSO's ordinary trades never pay it. Keep it
  in that narrow role, define it differently, or drop it.
- **MP-4c** The thermal threshold (0.2) far below the congestion threshold (0.8):
  two charges for one loading, from different points.
- **MP-4d** Zones as feeders and the zone bonus (15 % off the trade value),
  which can outweigh every other fee on a small network.
- **MP-4e** The graph model's parameters (the comparison's second arm): capacity
  per line from a total spread by length, or from the lines' ratings.
- **MP-4f** The fee factors' values (the paper gives none).

**Hands to RL.** The fees in the reward (through the profit); whether an agent
can see anything of the grid (the observation has only the grid distances).

---

## Stage 5: reputation

**Question.** Does reputation change within a day enough to matter, and does it
change any outcome?

**Now** ([reputation.py](../../core/market/reputation.py)): after every step,
each participant's score is 0.3 · reliability (its order volume matched by peers)
\+ 0.2 · fairness (its peer prices against the clearing price) + 0.5 · grid
contribution (its trades against $B_\text{grid}$); reputation moves towards the
score with a constant decay of 0.8 per hour
([`update_reputation`](../../core/market/reputation.py#L119-L142)). Every
participant starts every day at 0.5. Reputation acts in two places only: as the
**tie-break** of the double auction (bids and asks at exactly the same price) and
in the market rule's partner score (MP-3b). The RL agents see every partner's
reputation.

**Check.** Each participant's reputation over a day under the market's rule;
how often it decides a tie in the auction; whether it changes any partner choice.

**Decisions.**

- **MP-5a** The decay (0.8 per hour: the old value halves in about 3 hours).
- **MP-5b** The start value and horizon: 0.5 every day (now), or carried over
  between days.
- **MP-5c** The weights (0.3 / 0.2 / 0.5) and the three scores' formulas.
- **MP-5d** Its role: a tie-break with continuous prices almost never applies.
  Keep it as is, give it more weight in the clearing (e.g. a priority within a
  price band), or keep it only as information.

**Hands to RL.** Whether the partners' reputations belong in the observation
($N - 1$ entries now) and whether the partner action has anything to learn from
them.

---

## Stage 6: the market as a whole

**Question.** Over whole days with the market's own rule: does everything stay
consistent, and how good can a simple rule be?

**Now.** The market's own bidding rule offers a surplus at FiT + 0.3 · spread and
asks for a deficit at utility − 0.3 · spread (each ± a jitter of 0.1), after
the battery has taken what it can ([rule_based_bid.py](../../core/market/agent/rule_based_bid.py)); the Studio's Summary page shows
a day.

**Check.**

| Check | Pass when |
|---|---|
| All training and test days with the rule | Every step: the stage 1 balances hold, the power flow converges (or the failure is recorded), prices within bounds, no NaN |
| KPIs | The paper's KPIs computed per day ([P1] §3.4.1, §3.8) |
| Headroom | The net-position rule swept over its price margin (and battery-first on/off): the best rule's bill on the test days, against never trading |

**Decisions.**

- **MP-6a** The KPIs reported next to the bill.
- **MP-6b** The reference for "good": the best rule from the sweep, not CTCE.

**Hands to RL.** The baselines and the headroom: how much a learned policy can
gain at most against simple rules. After this stage the market is frozen for the
[RL plan](rl.md).

---

## Parking lot

| Raised in | Question | Belongs to |
|---|---|---|
| 22 Oct | Partner choice conditional on the side (an autoregressive policy) | RL plan, only if needed |
| 22 Oct | Forecasts in the observation | RL plan stage 1 |
