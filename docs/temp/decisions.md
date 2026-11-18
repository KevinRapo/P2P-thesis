# Decision log

The reasons behind the decisions whose reason needs more than a line. The question and
its status are in [Open items](open.md); this log keeps why it was decided so.
Each entry says what was decided, *why*, the *evidence* (the check, run or probe that
informed it) and where it is *implemented* (the code and the
[full cycle](../methodology/full-cycle.md) section, or "no code change"). The order
of the work: [Work plan](index.md).

## Market (`MP-`)

### MP-0b: Time-of-use tariffs in the reference scenario

*26 Oct 2026*

The DSO's utility price is time-of-use in the reference scenario: 0.20 from 22:00 to 07:00, 0.30 from 07:00 to 17:00, 0.40 from 17:00 to 22:00 (synthetic); the feed-in tariff stays flat at 0.08. Tariffs are a scenario setting: `DsoSetup.prices` names a file in `config/data/` with one price per market step (`synthetic_day.json` hourly, `synthetic_day_15min.json` quarter-hourly; `None`: flat); a series that does not match `step_hours` is refused

**Why.** With flat tariffs energy is worth the same at every hour, so a battery can only raise self-consumption and the hour carries no price signal; a time-of-use price gives the agents something to learn over the day. [P1] §3.4.4 lets the tariffs change per step. Synthetic, not measured data: a simple, explainable shape; real day-ahead prices remain an option

**Evidence.** Discussion of 26 Oct 2026

**Implemented in.** [synthetic_day.json](../../config/data/synthetic_day.json), [scenario.py](../../core/config/scenario.py) (`load_prices`, `price_at`), [dso.py](../../core/market/dso.py) (`set_hour`, `tariff_range`), [lem.py](../../core/market/lem.py), [market_env.py](../../core/env/market_env.py), [validate_market.json](../../config/scenarios/validate_market.json), `tests/market/test_time_of_use.py`

### MP-1c: Stored energy is worth nothing at midnight, for the policies and the references alike

*17 Nov 2026*

Energy left in a battery at midnight is **worth nothing**: every day, in training and in the held-out evaluation, starts from the scenario's initial state (batteries at their initial charge, reputations at their start value), and the references play the same game: each held-out day is its own linear program, its batteries start at the initial charge and may end the day emptier (`ceiling` and `non_p2p` with `daily`, `keep_end` off). The held-out evaluation plays each day on its own (`heldout_carry` false, the default from 17 Nov 2026); carrying the batteries over inside a test period stays a setting

**Why.** The thesis's episode is one day (RP-1f). An evaluation that carries the batteries over scores a policy on a game it was never trained on, and the references with `keep_end` forbade what the policies may do (empty the battery by midnight), so a per-day VTI could exceed 1 or punish a policy for using its stored energy. With the same rule on both sides, the VTI compares like with like. Valuing the energy at midnight (`terminal_value`) needs a price for it that the scenario does not give (the feed-in tariff undervalues it, the utility price overvalues it); it stays an optional variant of the base configuration. Accepted: the 50 % initial charge is free energy every day for every policy and reference alike, and the agents learn to use it before midnight

**Evidence.** Discussion of 17 Nov 2026 (the thesis's base configuration); `tests/market/test_ceiling.py::test_daily_references_play_each_day_on_its_own_and_may_empty_the_battery`, `tests/runner/test_runner.py::test_test_periods_leave_training_and_carry_only_when_asked`

**Implemented in.** [`ceiling.py`](../../core/market/ceiling.py) (`daily`, `day_references(keep_end)`), [`results._references`](../../core/runner/results.py) (reads `heldout_carry` from the run's `experiment.json`; a run saved before the field carried), [`spec.py`](../../core/runner/spec.py) (`heldout_carry`, `heldout_options`)

### MP-1e: Energy no trade covers is settled at retail

*4 Nov 2026*

Energy no trade covers is **settled at retail** (without grid fees until 11 Nov 2026; they apply since, MP-1f): an untraded import at the step's utility price, an untraded export at its feed-in tariff, in `net_bill` (the bill reward and every reported bill). Before, an untraded export earned nothing ("spilled")

**Why.** The surplus is not spilled physically: the power flow exports it anyway, since injections follow what the participants did, not their trades. Paying it nothing made `zero` worse than a household outside any market (by 94.67 EUR on 14 July days) and pushed agents to order a sale only to reach the feed-in tariff, paying the DSO's fees for it. Retail settlement is how P2P pilots work: each household keeps its supply contract for what it does not trade, and the market's fees are the cost of using the market. A peer trade then pays off only between the two tariffs. An order that clears with the DSO pays the same tariff plus its fees, so ordering costs something when it finds no peer; naming the DSO as partner becomes pointless (RP-1h)

**Evidence.** Discussion of 4 Nov 2026; [market_ceiling.ipynb](../../notebooks/market/market_ceiling.ipynb) (the gap between `zero` and non-P2P)

**Implemented in.** [reward.py](../../core/env/reward.py) (`net_bill`), `tests/market/test_market_env.py`, `tests/market/test_time_of_use.py`; [Reward](../methodology/environment/reward.md)

### MP-1f: Untraded energy pays the DSO's grid fees

*11 Nov 2026*

Everything a participant settles with the DSO pays the same grid fees: its **stage-3 trades and its untraded energy**. The untraded energy is an implicit trade with the DSO (stage 4) at the tariff it is settled at, along the participant's path to the transformer, and the participant pays the whole fee, as for a DSO trade (`fees_charged` off: 0). Peer trades keep their path fees. Supersedes MP-1e's "without fees"

**Why.** The same kWh ordered to the DSO in stage 3 paid congestion, thermal, voltage and transmission fees, and the same kWh left untraded paid none, so with fees on, not ordering was the cheapest way to use the grid (a surplus orders nothing and is paid the feed-in tariff in full). The power flow carries both alike, since injections follow what the participants did, not their trades, so the fee should not depend on whether an order was placed. The incentive that makes a peer trade pay is unchanged: a peer trade avoids the DSO's tariff spread and the path to the transformer

**Evidence.** [`_untraded_trades`](../../core/market/lem.py#L702-L726) in the dry run of one midday step: P3's 4.15 kWh deficit untraded and ordered to the DSO pay the same fee, part by part (`tests/market/test_untraded_fees.py`). Rural1, 11-17 June 2016, `net_position` baseline: the stage-3 trades paid 13.4 EUR (1.3 % of their value) before MP-4l and MP-1f, and 137.0 EUR (13.0 %) after; that week no energy was untraded (the rule orders its whole net position), so the effect shows under no-order policies and RL

**Implemented in.** [`_charge_fees`](../../core/market/lem.py#L679-L700), `StepRecord.untraded`, `Dso.settle`, the baseline's and the trade tables' fee columns; [Market step, 6c](../methodology/market/step.md#6-fees). The calculated references `non_p2p` and the ceiling stay before-fees (the ceiling is still an upper bound: no fee is below 0, MP-4n)

### MP-2b: The market has no order price bounds of its own

*17 Nov 2026*

`min_price` and `max_price` are **removed** (with MP-2e). An order's price is not limited by the market: it is rounded to whole cents (MP-5d), and an order priced outside the tariff band is kept as given and clears with the DSO at the tariff. The reconstructed `salazar` reward's economic term divides both gains by the tariff band instead of by $p_\text{utility} - p_\text{min}$ and $p_\text{max} - p_\text{FiT}$ (`# DEVIATION MP-2b` in [reward.py](../../core/env/reward.py))

**Why.** The bounds never bind: the RL decoding maps the price into the step's tariff band and the bidding rule prices inside it, so [P1] eq. 2's $[p_\text{min}, p_\text{max}]$ is that band here. Static bounds of [0, 1] were a second range that no participant of the framework reaches, two arbitrary settings in every scenario. Setting kept only because nothing calls it today is clutter (the guide's rule on settings outside the rule-based and RL paths)

**Evidence.** Discussion of 17 Nov 2026; `tests/market/`; [market_2_step.ipynb](../../notebooks/market/market_2_step.ipynb) (127 of 127 checks, an out-of-band order kept as given)

**Implemented in.** `MarketSetup`, [`_validate`](../../core/market/lem.py), `rule_based_bid.net_position`, `economic_reward`, the Studio's Scenario and Summary pages, the scenarios in `config/`

### MP-2f: A household's own surplus counts against its battery room

*11 Nov 2026*

A household's **own surplus counts against the battery room** it may buy: $q_\text{buy,max} = \max(0, D - G) + \max(0, E_\text{chargeable} - \max(0, G - D))$

**Why.** [P1] eq. 15b adds the whole room to a household that already has a surplus: it could order to buy room that its own surplus fills first (eq. 16), so the order exceeded what the battery takes

**Evidence.** `tests/market/test_untraded_fees.py` (the limit for a deficit, none, a partial and a full surplus)

**Implemented in.** [`max_buy_kwh`](../../core/market/agent/der.py#L199-L209)

### MP-2g: The order-quantity floor is 0.001 kWh

*11 Nov 2026*

The order-quantity floor is the scenario's `min_quantity`, 0.001 kWh in the thesis scenario (the default stays 0, with the code's 1e-9 guard)

**Why.** An order of 1e-7 kWh, numerical dust from a profile, entered the order book, the auction and the reputation as a full order

**Evidence.** `tests/market/test_thesis_rural1.py`

**Implemented in.** `thesis_rural1.json`, [`_validate`](../../core/market/lem.py#L561)


### MP-4e: The graph model is removed

*11 Nov 2026*

The graph model ([P1] §3.5) is **removed**; the power flow is the only grid the market reads, and the options around it (loss allocation, fee signals from measured loading and voltages) are developed instead of keeping a second grid method compatible. The fee options (`dso.voltage_drop`, `dso.losses`, eq. 18) stay: they are [P1]'s fee formulas, not the graph model

**Why.** (1) Not bounded by physical reality: the capacity split gives each edge a share of one total in inverse proportion to its length, but on a radial feeder every line on the main path carries the whole downstream load, so capacity is not additive; on IEEE-34 with [P2]'s own 1800 kW the split gives 7.5 / 44 / 185 kW per line (min / median / max) while the head line carries the full feeder load, and with the release's default of 1e6 kW nothing ever congests. (2) Awkward to compare: it sees only the trades (no background, no untraded energy, no direction), so every comparison needed extra choices (the total capacity, ratings, the voltage drop by distance) and would measure those choices rather than a method. (3) Keeping both costs effort in every new feature for no research value: on a network with real ratings and an AC power flow it adds nothing the power flow does not measure better

**Evidence.** The annotated tag [`v2-graph-model`](https://github.com/KevinRapo/P2P-thesis/tree/v2-graph-model) (commit 2fa9296, `git show v2-graph-model`) keeps the last version with both methods

**Implemented in.** `core/grid/graph.py`, `grid.method`, `graph_capacity`, `graph_total_kw`, `StepRecord.signal` and the Studio's fields removed; the DSO always observes the power flow ([Market step, 5. Grid](../methodology/market/step.md#5-grid)). Old scenario and run files that carry the keys still load

### MP-4f: Fees that cannot saturate

*17 Nov 2026* (the form); *11 Nov 2026* (the first threshold, below)

No fee part saturates. $C_t$ is the highest loading on the trade's path as a ratio, **not capped at 1**; the congestion part is $f_\text{cong} \max(C_t - C_\text{th}, 0)\, qp$, linear above its threshold without limit; the voltage part is $V_\text{drop}\, qp$, without [P1]'s cap $V_\text{th}$; [P1]'s thermal part (8d, 8g) is **dropped**. The thesis scenario has $C_\text{th} = 0.8$ and $f_\text{cong} = 2.0$: 40 % of the trade's value at the rated loading, what the two capped parts gave together before, and rising beyond it (100 % of the value at 130 %). Whether a cap is wanted after all (e.g. at the trade's value) and the factor values stay open (MP-4f in [open items](open.md))

**Why.** With the capped parts the fee reached its ceiling at 86 % loading (thermal at its 0.3 cap) and 100 % (congestion, with $C_t$ capped at 1): a line at 101 % and one at 160 % cost the same, so the fee stopped signalling exactly where the limits are broken, and the development runs found that the fees barely change what is learned. The thermal part read the same loading as the congestion part a second time, with another slope and a cap. A fee may now exceed the trade's value: on a badly overloaded path a trade stops paying

**Evidence.** Discussion of 17 Nov 2026; [edge_cases.ipynb](../../notebooks/market/illustration/edge_cases.ipynb) §4 (the thermal part at its cap from 44 % loading with the paper's threshold); `tests/market/test_fees_timing.py`, `test_untraded_fees.py`, `test_voltage_drop.py`; [market_1_formulas.ipynb](../../notebooks/market/market_1_formulas.ipynb), [market_2_step.ipynb](../../notebooks/market/market_2_step.ipynb)

**Implemented in.** [`Dso.congestion`, `fees_of`](../../core/market/dso.py), `GridFees` (no `thermal`), `DsoSetup` (no `thermal_threshold`, `thermal_cap`, `voltage_threshold`), `thesis_rural1.json`, the Studio's Scenario and Summary pages

**Before (11 Nov 2026): thermal threshold 0.8 in the thesis scenario.** The thesis scenario's `thermal_threshold` is **0.8**, the same as the congestion threshold (the code's default stays 0.2, the paper's). A first, untuned choice: the fee levels remain open

**Why.** With the transformer counted in $C_t$ (MP-4l) the paper's 0.2 charged every DSO settlement above 20 % transformer loading, and capped at 30 % of the value from 44 %: on rural1 the thermal part was 96.5 EUR of the 137 EUR the DSO trades paid in a June week

**Evidence.** Rural1, 11-17 July 2016, `net_position` and non-P2P with their fees on the same days: fees 90.6 to 23.9 EUR and 254.8 to 102.8 EUR with the slack reference (MP-4l) and 0.8 together

**Implemented in.** `thesis_rural1.json`; [open items](open.md) MP-4f

### MP-4k: BCDLA shares only the current-dependent loss

*11 Nov 2026*

BCDLA shares **only the current-dependent loss**: a line's measured loss, a transformer's copper loss $v_{kr}/100 \cdot S_n (I_\text{LV}/I_\text{rated})^2$. The transformer's no-load (iron) loss stays with the DSO and is reported as `LossShares.residual_kw`

**Why.** BCDLA splits $R_b \lvert I_b \rvert^2$ by $\operatorname{Re}(I_e \overline{I_b}) / \lvert I_b \rvert^2$ (Carpaneto et al. 2006). Applied to the transformer's measured loss, which also holds its constant no-load loss, the shares are many times the loss near a balanced transformer: with a load and PV of 30 kW each on a small feeder the PV got about −88 kW and the load +89 kW out of a loss of about 1 kW. The no-load loss is what the transformer costs while energised, caused by no participant

**Evidence.** pandapower's `pl_mw` less the copper loss is 0.483 kW on rural1 (= $p_{fe} V^2$, 0.46 kW at 1.025 pu) at every loading from 0 to 4 times rated, within 0.01 kW. Rural1, 11-17 June 2016: the median per-step share fell from 0.176 to 0.026 kWh, the loss charge from 70.0 to 38.4 EUR; the DSO keeps 81.2 kWh. That week never came near balance (largest share 1.85 to 1.70 kWh), the blow-up is the unit test

**Implemented in.** [`BranchCurrentDecomposition.shares`](../../core/grid/losses.py#L153-L175), [`trafo_copper_losses_kw`](../../core/grid/losses.py#L246-L273), `tests/market/test_losses.py`; [Market step, 5](../methodology/market/step.md#5-grid)

### MP-4l: Fees that see rural1's binding limits

*11 Nov 2026*

Fees that see rural1's binding limits. **Measured voltage**: $V_\text{drop} = \max \lvert V - V_\text{slack} \rvert$ over the path's buses (`GridPath.buses`), with $V_\text{slack}$ the external grid's set point (`GridAssessment.slack_voltage_pu`; first $\max \lvert V - 1 \rvert$, amended the same day), not $\lvert V_a - V_b \rvert$ between its ends; eq. 8c's form $\min(V_\text{drop}, V_\text{th})\, q\, p$ unchanged, eq. 8f (`"distance"`) unchanged. **Transformer**: for a trade or settlement with the DSO the congestion $C_t$ of the congestion and thermal fees is the largest of the path's lines and the transformer's loading (`Dso.observe` keeps it); peer trades unchanged

**Why.** On rural1 the limits that bind are the voltage (up to 1.057 pu against 1.05) and the transformer (up to 114 %), while the lines peak at 37 %. A difference between two ends is 0 for two neighbours at the same high voltage, and a fee that reads only line loading never sees the transformer

**Evidence.** Rural1, 11-17 June 2016: 12 steps over the voltage limit and 9 over the transformer's, no line above 37 %. The week's fee parts, before to after: voltage 2.6 to 35.1 EUR, congestion 0 to 10.5, thermal 14.0 to 99.4, zone -3.4 to -0.7 (MP-4n). Two consequences, both resolved the same day: from nominal 1 pu the voltage fee was positive at every step, since the external grid sits at 1.025 pu (2.5 % of value at least), so the reference is the slack's set point and a quiet network pays 0 (`tests/market/test_voltage_drop.py`); and the thermal part (threshold 0.2, cap 0.3) reached 30 % of a DSO trade's value whenever the transformer was above 20 %, so the thesis scenario's `thermal_threshold` is 0.8 (MP-4f, below)

**Implemented in.** [`voltage_drop_of`](../../core/market/dso.py#L166-L179), [`congestion`](../../core/market/dso.py#L181-L196), `GridPath.buses`; `tests/market/test_voltage_drop.py`, `tests/market/test_untraded_fees.py`

### MP-4m: The imbalance fee is off in the thesis scenario

*17 Nov 2026* (decided); *11 Nov 2026* (off, open as a design)

**Decided: off, not replaced.** What the fee targets ([P1] eq. 8b, 8h) is a participant settling with the DSO when a peer on the other side was available: a missed match. In this market that happens only when the prices do not cross or an agent orders too little (choosing the DSO as a partner no longer exists, RP-1h), and the tariff spread already prices it on **both** sides: the buyer pays $p_\text{utility}$ instead of a peer price and the would-be seller gets $p_\text{FiT}$, so the pair loses the whole spread on that kWh and each bill feels its share. The power flow nets the buyer's draw against the local surplus whatever the contracts say, so the missed match is purely economic. A fee on the same event would add to an incentive that exists rather than create one (an existing incentive, not an identical learning effect; and the implemented fee reads the sign of the book, not whether a compatible peer existed); [P1] itself argues that the market price already makes the DSO the costlier choice. A charge on the energy that actually leaves the feeder (the community's net exchange, settled pro rata to the settlements in its direction) was considered and dropped: it is an upstream network tariff, a different instrument, not this fee. The mechanism stays in the code as [P1]'s (`imbalance_factor`), 0 in the thesis scenario

**Before (11 Nov 2026).** The imbalance fee ([P1] eq. 8b, 8h) is **off in the thesis scenario** (`imbalance_factor` 0 in `thesis_rural1.json`); the code stays, marked `# OPEN MP-4m`. Whether to keep it off, or replace it, stays open

**Why.** The release never charged it (M-30: $F_\text{imb}$ is 0 in every run), so off is its observable behaviour. Our reading of 8b/8h charges the side of a DSO trade that worsens the order book's balance $B$ (offered minus asked), scaled by $\min(q/\lvert B \rvert, 1)$: (1) the scale saturates near a balanced book, so a change of 0.02 kWh in $B$ moves 15 % of a trade's value from the buyer (about 1.35 EUR) to the seller (about 0.36 EUR) of the same step, and a bigger imbalance means a smaller fee; (2) $B$ is a sum over all orders that no actor sees before acting, so under DTDE and CTDE the fee is unpredictable for the actors and under CTCE, which sets every order, it is not: a bias in the comparison of the paradigms; (3) the price spread and the DSO path fees already make the DSO costly. Alternatives for later: a flat charge on the DSO-routed quantity, or a fee on $\min(q, \lvert B \rvert)$ (continuous, but still unobservable)

**Evidence.** Worked examples with the release's code (matching.py:319, dso.py:226, 247) and ours in the discussion of 11 Nov 2026; the week of 11-17 June 2016 paid no imbalance fee with the factor at 0.15, as the rule's orders are all on one side

**Implemented in.** `thesis_rural1.json`, [`imbalance_fee`](../../core/market/dso.py#L247-L273)

### MP-4n: A trade's fee is never below 0

*11 Nov 2026*

A trade's fee is **never below 0**: the zone bonus (eq. 8e) cancels the other parts but never pays out, so it is capped at their sum

**Why.** A negative fee paid a trade for existing: with no other fee a same-zone trade was paid 15 % of its value by the DSO. It also let the money ceiling's condition "fees count as nothing" (`ceiling.py`) hold only by assumption

**Evidence.** `tests/market/test_untraded_fees.py`: no trade of a played day has a negative fee

**Implemented in.** [`fees_of`](../../core/market/dso.py#L199-L245)

### MP-4o: The zone bonus is off in the thesis scenario

*17 Nov 2026*

`zone_factor` is **0** in `thesis_rural1.json`; the bonus ([P1] eq. 8e, capped by MP-4n) stays in the code

**Why.** With the fees read along a trade's contract path, the bonus let a trade cancel its whole stress fee by naming a counterparty on the same feeder, with no change in any injection: locality has no physical benefit when the injections are fixed. With partners learned, part of what PPO learns would be this tariff arbitrage, not grid-friendly behaviour. Real local schemes discount same-feeder trades, but not by cancelling a congestion charge. The path-based fees remain a contractual network tariff that reads the measured network state (not an allocation of physical responsibility), so cheaper partner choices are still not evidence of grid improvement; that is judged by loading, voltage and losses

**Evidence.** Discussion of 17 Nov 2026 ([capacity and fees](../discussions/2026-11-17-capacity-and-fees.md))

**Implemented in.** `thesis_rural1.json`

### MP-5d: Order prices are rounded to whole cents

*31 Oct 2026*

Order prices are rounded to whole cents (`MarketSetup.price_decimals`, 2); reputation stays the double auction's tie-break between equal prices

**Why.** [P1] uses reputation as a secondary sorting criterion, and so does the original code, but with continuous prices exact ties almost never occur, so the rule had no effect. Rounding keeps the paper's rule and makes it apply. Trade prices are not rounded: the midpoint of two cents can be half a cent

**Evidence.** Discussion of 31 Oct 2026

**Implemented in.** [lem.py](../../core/market/lem.py) (`_validate`), [scenario.py](../../core/config/scenario.py)

## RL (`RP-`)

### RP-1f: The market day stays terminated

*26 Oct 2026*

By default the market day stays **terminated**; `episode_days`, `truncate_episode` and `terminal_value` (31 Oct 2026) make the alternatives an experiment, `day_end.json`: each day is a task of its own, the return ends at midnight. Truncating it (bootstrapping into the next day) was implemented and reverted the same day

**Why.** Truncation is only consistent if the critic learns the value of the states it bootstraps from; with every day starting fresh (battery at its initial charge, reputation 0.5) it would estimate a continuation the environment never plays. The consistent alternatives (a random state at reset, or several consecutive days per episode with the state carried over) change how training and evaluation are organised: kept for after the simple system works. Accepted limitation: the agents optimise one day, and energy left in the battery at midnight is worth nothing to them (MP-1c)

**Evidence.** Discussion of 26 Oct 2026

**Implemented in.** [market_env.py](../../core/env/market_env.py) (`step`, docstring "Episodes")

### RP-1g: The `salazar` reward's C is a reference energy scale

*17 Nov 2026*

[P1]'s grid capacity $C$ is resolved from the scenario when a run does not state it: the **99th percentile over the training steps of $\max(\sum_i \bar q^\text{sell}_{i,t}, \sum_i \bar q^\text{buy}_{i,t})$**, the larger side of the order book the participants could fill, with each participant's eq. 15 bounds (MP-2c, MP-2f) from its profiles and its battery's largest one-step charge and discharge, independent of its state of charge. Recorded in the run's `resolved_config` and reused for validation and the held-out days, like the bill's scale. On `thesis_rural1.json` over 2016: 404 kWh per step at PV ×1, 460 at ×1.25, 517 at ×1.5. "Grid balance" in [P1] is the **order book's** balance $B$ (offered minus asked before stage 3); the docs and the thesis call it that

**Why.** In the reward $C$ only scales $B$ and the order's quantity (`r_grid`, weight 10, and $\gamma_\text{DSO}$); it is not a network capacity, and SimBench has none: the transformer's rating would be wrong (peers trading inside the feeder never reach it). Normalising by the step's own order volume instead was rejected: it rewards relative balance (a one-sided 1 kWh and 100 kWh book score alike) and agents move the denominator, a further change of the objective. A policy-independent envelope of the scenario is reproducible and keeps sensitivity to absolute imbalance. Two properties to state with it: before clipping, the imbalance penalty outweighs the contribution term by $10\lvert B\rvert/q$, which $C$ cannot change; and the "impact" term compares $B$ with the agent's previous-step net trade, not its current order's effect. The `salazar` arm is a reconstructed Salazar configuration (E-16 already changes the original's effective reward)

**Evidence.** Discussion of 17 Nov 2026 ([capacity and fees](../discussions/2026-11-17-capacity-and-fees.md)); `tests/market/test_market_env.py`

**Implemented in.** [`MarketEnv._reference_capacity`](../../core/env/market_env.py), `resolved_config`

### RP-2a: When the RL layer counts as ready for the market

*26 Oct 2026*

The RL layer counts as ready for the market when, with the market's network and default settings: probes 1-3, 8a and 10 pass in every paradigm and seed; the learning probes 4, 5, 6, 7 and 9 pass in CTDE and DTDE for at least 2 of 3 seeds within 4 times their budget; CTCE either does too or its shortfall is measured and documented; 8b is measured, not judged; the KL per update stays in a usual range

**Why.** A fixed target for the probe work: what the probes can show (the plumbing and the learner work, with exact answers) and what they cannot (the market's optimum). CTDE and DTDE carry the thesis's comparison; CTCE's joint ratio and summed reward (L-02) make it slower by design

**Evidence.** Met on 26 Oct 2026 with RP-3h and RP-6b: CTDE and DTDE 29 of 30 on the learning probes (probe 7 DTDE 2 of 3), every plumbing probe in every paradigm and seed, median KL 0.005. CTCE: 8 of 15 at 4 times the budget, not converging at 8 times on probes 5 and 6 (`runs/@taltech/probes_screen_3e-4_500_64_10/`)

**Implemented in.** [docs/methodology/validation/probes.md](../methodology/validation/probes.md)

### RP-3a: CTCE's entropy bonus is divided by the number of agents

*10 Nov 2026*

`entropy_coeff` is **per agent**, and CTCE divides it by the number of agents $N$ (13: 0.01 becomes 0.00077) in [`build_config`](../../core/rl/config.py), as MAPPO averages over agents. The summed group reward stays (RP-3b). A setting that wants the old joint bonus writes 0.13 (0.01 × 13). Before this change CTCE trained with the full 0.01 on the joint entropy, so CTCE results from before 10 Nov 2026 and after it are not comparable.

**Why.** CTCE's one joint policy has the action parts of all $N$ agents, so its entropy is a sum over $4N$ parts, while PPO's surrogate has one standardised advantage per step and clips one joint ratio. With one coefficient the bonus weighed about $N$ times what it does for one DTDE agent, and nothing clips it, so it kept pushing the policy's spread up. Dividing by $N$ gives each agent's parts the weight they have in DTDE. PPO's clip widened by $\sqrt{N}$ (27 Oct 2026) was tried as a probe and experiment variant only, and is not in the defaults: `clip_param` is 0.2 in every paradigm.

**Evidence.** The experiment `ctce_entropy` (26 Oct 2026, TalTech; market_s2, CTCE, 13 agents, one seed, 240k steps; `runs-old/old/ctce_entropy`). With the joint 0.01 the group's entropy rose from 80 to 130 and the team return stayed below 0 (−1.0 at the end, between −1.3 and −0.1 over the last six evaluations). With 0.01 / 13 the entropy fell to 45 and the return reached 1.6; with 0 it fell to 38 and the return was 1.2. One seed, and not the thesis scenario. On the probes (3 agents) the entropy was not why CTCE misses probes 4 to 6 ([probes](../methodology/validation/probes.md#why-ctce-misses-probes-4-6-26-october-2026)). Since this change every CTCE run has trained with the divided value: `combo_ctce` records `entropy_coeff` 0.00077 in its `run.json`

**Implemented in.** [config.py](../../core/rl/config.py) (`build_config`), `tests/rl/test_6_ctde_structure.py` (`test_ctce_weighs_the_entropy_per_agent`), commit `2e0d907`; [learning](../methodology/learning/index.md#ctce) (the paradigms) and C5 of [the iteration](../methodology/learning/examples/iteration.md)

### RP-3e: CTDE: own reward, a critic and an actor per agent

*24 Oct 2026*

CTDE uses each agent's own reward, one central critic per agent (input $[o_i, o_1, \dots, o_N]$) and one actor per agent (input $o_i$); no parameter sharing for now. A team-reward CTDE, a shared critic and group-wise policy sharing are in the parking lot

**Why.** The households are self-interested, each paying its own bill, and [P2] defines CTDE on each agent's own return (eq. 18-19). With individual rewards every critic learns a different value function, so nothing is duplicated; the per-agent central critic for agents with their own rewards is MADDPG's design (Lowe et al. 2017). A shared critic would cost the same operations per step and could only gain data efficiency, at the risk of interference between different households

**Evidence.** Discussion of 24 Oct 2026 (MAPPO's shared critic assumes a team reward, Yu et al. 2022 §3)

**Implemented in.** no code change: [ctde.py](../../core/rl/ctde.py), [config.py](../../core/rl/config.py)

### RP-3h: The continuous action parts: log std and mean

*26 Oct 2026*

The continuous action parts: one learned log std per part for every state (MAPPO's `DiagGaussian`), and each part's mean through tanh (`free_log_std_parts`, `bound_mean` in [rl_defaults.py](../../core/rl_defaults.py)); no bounds on the log std

**Why.** RLlib's state-dependent log std shrank faster than the categorical part it depends on was decided, after which the mean could not reach its target (probe 9: log std to −5.5, the level stuck at 0.1–0.35). The state-independent log std moves at most about the learning rate per step, slow enough for the mean to follow; the bounded mean keeps it inside the action's bounds, where the clipped reward is not flat. Bounding the log std alone (variant A) did not help

**Evidence.** Probe comparison of 26 Oct 2026, fast preset, 3 seeds (`runs/@taltech/probe_methods_scores.csv`): probe 9 in CTDE/DTDE 0/6 (RLlib) → 6/6 (SM); CTDE/DTDE 47/60 → 56/60 overall. Not solved by any variant: probe 6, CTCE

**Implemented in.** [modules.py](../../core/rl/modules.py), [rl_defaults.py](../../core/rl_defaults.py)

### RP-4a: Logging the KL with weight 0

*25 Oct 2026*

The KL between the collecting and the updated policy is computed and logged (`mean_kl_loss`) with weight 0 in the loss: `use_kl_loss=True`, `kl_coeff=0.0`

**Why.** PPO's most direct measure of each update's size; RLlib computes it only with `use_kl_loss=True`, and with coefficient 0 its adaptive weight stays 0. L-07's risk (a non-finite KL making the loss NaN unnoticed) is covered: training stops on any non-finite metric

**Evidence.** Discussion of 24-25 Oct 2026; probe 9's frozen level, where the update size is the question

**Implemented in.** [rl_defaults.py](../../core/rl_defaults.py), [config.py](../../core/rl/config.py)

### RP-6b: PPO's training settings

*26 Oct 2026*

PPO's training settings: learning rate 3e-4, batch 500 environment steps, minibatches of 64, 10 epochs (160 gradient steps per 1,000 environment steps); the rest unchanged (grad_clip 0.5, entropy 0.01, clip 0.2)

**Why.** Market steps are expensive (a power flow each), so the settings that learn most per sample are the ones to use. The original's lr 1e-5 with one minibatch of 4000 and 5 epochs moved the policy almost nothing (median KL 0.0014, log std unchanged); lr 1e-3 on the 2 x 256 network was too aggressive (KL 0.016, log std collapsing to -3.7); every batch of 2000 or 4000 made too few updates in the probes' budgets. These are Stable-Baselines3's PPO defaults (lr 3e-4, minibatch 64, 10 epochs) with a batch of 500. A larger batch may still learn at the market's budget (more updates, less noise): not tested

**Evidence.** Screen of 26 Oct 2026: 8 settings x probes 4-7, 9 x 3 paradigms x 3 seeds, market network with SM, 4 times each probe's budget in environment steps (`runs/@taltech/probes_screen_*/`): 3e-4/500/64/10 passes 29 of 30 in CTDE/DTDE; the original's 3 of 30

**Implemented in.** [rl_defaults.py](../../core/rl_defaults.py)

### RP-6d: The thesis experiments' learning rate, budget and scoring, fixed before the runs

*17 Nov 2026, before any Step 2 result existed*

**Selection (Step 2).** For each learning rate (3e-4, 1e-3), the mean over its three seeds of the validation VTI after fees over all 28 validation days (`results.validation_scores`, period `all`) at every evaluation point (240k, 480k, ..., 1.92M environment steps). The rate's budget is the first point after which that mean rises by less than 0.01 at every point of the next 480k steps; the last point (1.92M) if none. The rate chosen is the one with the higher mean at its own budget; within 0.01 of each other, the one with the smaller budget. Every arm of the experiments is cut at the chosen rate's budget (`analysis/heldout_at.py`, from the run's `checkpoints/<steps>`).

**Runs in parallel, not in sequence.** The arms (base seeds 3-4, E1, E2, E3) are trained at both learning rates to 1.92M, alongside Step 2, with a checkpoint at every evaluation point; the arms of the rate Step 2 does not choose are not reported. PPO's learning rate is constant, so a run cut at a budget is the run that budget would have trained. The base arm's seeds 0-2 are Step 2's runs of the chosen rate (the same settings and seeds; disclosed: they are the selection runs, so the base arm's interval is conditional on the selected configuration).

**Amended 18 Nov 2026, 00:15.** The cluster ran only 12 of the 60 runs at once (fair-share priority), so all would have taken several waves of about 11 h. The arms at lr 3e-4 are held back and run only if Step 2 chooses 3e-4; the arms at 1e-3 run now (the development runs had 1e-3 at its level by 960k steps and 3e-4 still rising at 2.88M, so 1e-3 is the likelier choice within 1.92M; the rule decides). E3's CTCE arm runs on blackwell1 in the short partition (`thesis_e3_ctce`), where it fits the 4 h limit

**Amended 18 Nov 2026, 00:50: the primary set on blackwell1.** A throughput check (`speed_blackwell`, DTDE, 96k steps) gave 150, 189 and 208 environment steps per second with 8, 16 and 24 samplers, against about 40 on the green nodes. With 14 samplers a 1.92M-step run takes about 3.5 h with its evaluations, inside the short partition's 4 h; a run that still reaches the limit keeps its checkpoints, and every arm is read at Step 2's budget anyway. So every run of Step 2 and of the arms at lr 1e-3 runs again there (`bw_step2`, `bw_base`, `bw_e1_agent`, `bw_e1_market`, `bw_e2`, `bw_e3`: 33 runs, all with 14 samplers), and these are the reported results. The runs on the green nodes (8 samplers, same seeds and settings) continue as a replication: the number of samplers changes how a batch of 4000 steps is gathered, not the algorithm's settings. `thesis_e3_ctce` (8 samplers) was stopped

**Amended again 18 Nov 2026, 01:45: back to the green set.** None of the 31 runs on blackwell1 got past building its algorithm in 85 minutes (no step-0 evaluation written; three had failed at start with Ray's "Resource temporarily unavailable"): 31 Ray instances with 14 samplers each exceed the cluster's per-user thread limit on one node (4096), which the three-run throughput check did not reach. The `bw_*` experiments were stopped. The runs on the green nodes (8 samplers), started at 23:57 and 00:20 and about 10 h long, are the reported set again; E3's CTCE arm runs on blackwell1 as `thesis_e3_ctce` (5 runs, 8 samplers, as before). Lesson for later runs: on blackwell1 the number of runs at once is bounded by threads, not CPUs (about 5-6 runs of 8-14 samplers)

**Step 2's result and the choice, 18 Nov 2026, 10:30.** The six runs finished (8.8-10.6 h). Mean validation VTI after fees over three seeds, at 240k ... 1.92M steps: lr 1e-3 0.097, 0.415, 0.474, 0.548, 0.567, 0.575, 0.582, 0.592; lr 3e-4 -0.009, 0.349, 0.492, 0.537, 0.564, 0.575, 0.603, 0.591 (`analysis/out/step2_curves.csv`; `net_position` -0.210). Applied as fixed: lr 1e-3 still rises by 0.010 or more within 480k of every point, so its budget is 1.92M (0.592); lr 3e-4 does not rise after 1.68M (0.603). The two differ by 0.011, just over the 0.01 tie margin, so **lr 3e-4 at 1.68M** is chosen. The choice is close: the two rates are practically level from 1.2M on, which the thesis states

**Consequences.** The arms at lr 3e-4, held back by the first amendment, run now, trained directly to 1.68M (constant learning rate: the same policy as a 1.92M run cut there; 7 evaluation points of 240k): `thesis_base_lr3e4` (seeds 3-4), `thesis_e1_agent_lr3e4`, `thesis_e1_market_lr3e4`, `thesis_e2_lr3e4`, `thesis_e3_ctde_lr3e4` pinned to the idle green4-7, `thesis_e3_ctce_lr3e4` on blackwell1. The base arm's seeds 0-2 are `base_step2`'s lr 3e-4 runs cut at 1.68M. The arms at lr 1e-3, already trained (all to 1.92M, which is that rate's own budget by the rule), are reported as a **secondary set**: the same comparisons at the rate not chosen, a check that the E1-E3 conclusions do not hang on a choice made by 0.011. This replaces "not reported" of the first amendment; it was decided before any test-week VTI was computed. (The runner's automatic end-of-training evaluation on the test days shows a mean return, in reward units, in `status`; it was not used and no test VTI was computed before this choice.)

**Corrected 18 Nov 2026, 11:40: the plateau window must be trained in full.** The Codex review of stage 2 ([discussion](../discussions/2026-11-17-overnight-experiments.md)) found that `analysis/thesis_results.py` accepted a plateau on a window shorter than the rule's 480k: at 1.68M only one later point (1.92M) exists. The rule says "every point of the next 480k steps", so a point qualifies only if the whole window was trained (at most 1.44M here); the script was wrong, not the rule. Applied as written: neither rate has a plateau by 1.44M (lr 3e-4 rises by 0.028 after it, lr 1e-3 by 0.017), so both budgets are 1.92M, where the means are 0.5917 (1e-3) and 0.5914 (3e-4): within 0.01 at the same budget, a case the tie-break (the smaller budget) does not settle. An additional tie-break, adopted after the validation results and not part of the frozen rule, settles it by the higher mean: **lr 1e-3 at 1.92M** (`select` now does this, and refuses to choose unless every rate has three seeds at every point). The two rates are practically tied on validation (a difference of 0.0003), which the thesis states; the intervals of the base arm are conditional on this selected configuration, since its seeds 0-2 informed the selection. The lr 1e-3 arms, all trained to 1.92M, are the primary set. The lr 3e-4 arms, started at 11:00 to 1.68M as `thesis_*_lr3e4`, were stopped after about 20 minutes and run again to 1.92M as the **secondary set** (`sec_*_lr3e4`; base seeds 0-2 are `base_step2`'s lr 3e-4 runs), declared after the validation choice, as a sensitivity check of E1-E3 to the learning rate: every comparison is reported in both sets, whatever its direction. **Test exposure, disclosed:** while monitoring, the `status` output's held-out column showed each finished lr 1e-3 run's mean return on the test days in reward units (for the bill reward, scaled net money, closely related to the primary indicator). No test VTI was computed before these choices and neither choice used test information, but the arms' test returns were visible before the secondary set was declared

**Scoring (test weeks).** Primary indicator: the VTI after fees over the 28 test days, each day on its own (MP-1c). Per arm the mean over five seeds with a 95 % percentile bootstrap over seeds (RP-7b); between arms the paired difference per seed (the same seed in both), its mean and bootstrap interval. Grid outcomes (hours over a loading or voltage limit, their peaks) and the energy-money VTI, participation and equality are reported beside it. A run that fails is restarted once with the same seed; a second failure is reported and the arm has four seeds

**Why.** The thesis's Step 2 named the quantities but not the order of the choices; fixing it before any result is seen keeps the validation choice from being tuned to the outcome. Training the arms at both rates in parallel costs compute but not a second night: with Step 2 first, the arms would start only after its slowest run (about 11 h on the cluster's `common` nodes)

**Evidence.** Codex review of stage 1 ([discussion](../discussions/2026-11-17-overnight-experiments.md))

**Implemented in.** `config/experiments/base_step2.json`, `thesis_base.json`, `thesis_e1e2.json`, `thesis_e3.json`; [`train.py`](../../core/rl/train.py) (`checkpoints/`), [`launch.heldout_at`](../../core/runner/launch.py), `analysis/heldout_at.py`

### RP-7c: Training, validation and test days

*17 Nov 2026*

2016 is split three ways: **validation** weeks 11-17 January, 11-17 April, 11-17 July and 10-16 October (the four weeks the development runs were scored on; they informed configuration choices, so they choose settings and are not test data); **test** weeks 15-21 February, 16-22 May, 15-21 August and 14-20 November (Monday to Sunday, one per season, a month after each validation week, not looked at before the final runs); **training**: every other day from 1 January to 30 December (309 days). An experiment's `validation_periods` are left out of training like its `test_periods`, and at every evaluation point the trained policy plays each validation day on its own (`validation*.csv`); `results.validation_scores` gives the VTI over them, which chooses the learning rate and the budget of the base configuration (thesis §4.5, Step 2)

**Why.** Settings chosen on the days that are then reported are optimistically biased; the four development weeks were already used for choices, so they become the validation set, and the test weeks are new. One week per season keeps the year's range of PV and demand in each set

**Evidence.** The thesis's experiment design (17 Nov 2026), reviewed with Codex ([discussion](../discussions/2026-11-17-experiment-plan-review.md))

**Implemented in.** [`spec.py`](../../core/runner/spec.py) (`validation_periods`), [`train.py`](../../core/rl/train.py) (`validation`), [`results.validation_scores`](../../core/runner/results.py); `config/experiments/base_step2.json`

### RP-7n: The VTI two ways: on energy money and after fees

*11 Nov 2026*

The VTI is computed **two ways, both kept**: `vti` on **energy money** (the bill before grid fees and loss charge, the references' money) and `vti_after_fees` on `team_money` (after them), the same references in both; likewise per day (`vti_day`, `vti_day_after_fees`). `team_money` stays the money after fees, and `gain_net_position` and `participants_better` use it. The peer charge counts with the fees, not with energy money

**Why.** The ceiling and `non_p2p` are programs on energy, with no fee in them. With fees on, a VTI of after-fee money against fee-free references mixes coordination with grid cost, and a run with the fees (base) cannot be compared with one without (`no_fees`). Energy money is the same on both sides; the second column says how much the fees take off, `vti - vti_after_fees` being (fees + loss charge) over the gap between the references

**Evidence.** Rural1, 11-17 July 2016, `net_position`: VTI 0.273 before fees and 0.216 after, 0.149 with the paper's thermal threshold and nominal voltage (the energy money does not move with the fee settings)

**Implemented in.** [`indicators.py`](../../core/market/indicators.py) (`day_table`, `_period_scores`, `_day_scores`), `tests/market/test_ceiling.py`, `tests/market/test_reference_flows.py`; [Metrics](../methodology/evaluation/metrics.md)

### RP-7o: References on the power flow, non-P2P with its fees

*11 Nov 2026*

The references run on the market's own **power flow**, and the non-P2P reference pays the **fees**: a schedule (the participants' generation and demand, what each battery charges and discharges) fixes every bus's injection, so `ceiling` and `non_p2p` go through `LocalEnergyMarket.assess_outcomes` per test step (same network, background, scales, loss rule, DSO). `non_p2p` is charged exactly like untraded energy (every participant's exchange is a settlement with the DSO, transformer in $C_t$, MP-1f) and its participants' bills are after fees. The ceiling gets the flow and the loss charge but no fees: it nets the whole community, so who traded with whom is undefined (`fees`, `team_money` NaN). `core/runner/ceiling.py` and `indicators.py` moved to `core/market/`

**Why.** A reference without a grid hides what it does to the network: on rural1 the ceiling loads the transformer to 213 % (a week in July) and breaks a voltage limit for 8 hours, the money-only optimum is not grid-feasible. Charging non-P2P like the market charges the same energy makes the participants' comparison (PI, EI, `participants_better`) one of real money on both sides. The ceiling and the indicators are market scoring, not orchestration, and nothing in `core/market` imports the runner, env or rl (`tests/market/test_layers.py`)

**Evidence.** Without batteries the non-P2P reference reproduces the market with nobody ordering to the cent, in fees, loss charge, losses and bills (`tests/market/test_reference_flows.py`); the references use the evaluation's days, participants and battery start states, and the batteries end at least as full as they started where the evaluation lets them end anywhere

**Implemented in.** [`ceiling.py`](../../core/market/ceiling.py), `LocalEnergyMarket.assess_outcomes`, [`results.py`](../../core/runner/results.py) (`_references`); [The ceiling](../methodology/evaluation/index.md#the-ceiling)
