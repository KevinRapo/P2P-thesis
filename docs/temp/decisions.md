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

### MP-5d: Order prices are rounded to whole cents

*31 Oct 2026*

Order prices are rounded to whole cents (`MarketSetup.price_decimals`, 2); reputation stays the double auction's tie-break between equal prices

**Why.** [P1] uses reputation as a secondary sorting criterion, and so does the original code, but with continuous prices exact ties almost never occur, so the rule had no effect. Rounding keeps the paper's rule and makes it apply. Trade prices are not rounded: the midpoint of two cents can be half a cent

**Evidence.** Discussion of 31 Oct 2026

**Implemented in.** [lem.py](../../core/market/lem.py) (`_validate`), [scenario.py](../../core/config/scenario.py)

### MP-1e: Energy no trade covers is settled at retail

*4 Nov 2026*

Energy no trade covers is **settled at retail** (without grid fees until 11 Nov 2026; they apply since, MP-1f): an untraded import at the step's utility price, an untraded export at its feed-in tariff, in `net_bill` (the bill reward and every reported bill). Before, an untraded export earned nothing ("spilled")

**Why.** The surplus is not spilled physically: the power flow exports it anyway, since injections follow what the participants did, not their trades. Paying it nothing made `zero` worse than a household outside any market (by 94.67 EUR on 14 July days) and pushed agents to order a sale only to reach the feed-in tariff, paying the DSO's fees for it. Retail settlement is how P2P pilots work: each household keeps its supply contract for what it does not trade, and the market's fees are the cost of using the market. A peer trade then pays off only between the two tariffs. An order that clears with the DSO pays the same tariff plus its fees, so ordering costs something when it finds no peer; naming the DSO as partner becomes pointless (RP-1h)

**Evidence.** Discussion of 4 Nov 2026; [market_ceiling.ipynb](../../notebooks/market/market_ceiling.ipynb) (the gap between `zero` and non-P2P)

**Implemented in.** [reward.py](../../core/env/reward.py) (`net_bill`), `tests/market/test_market_env.py`, `tests/market/test_time_of_use.py`; [Reward](../methodology/environment/reward.md)

### MP-4e: The graph model is removed

*11 Nov 2026*

The graph model ([P1] §3.5) is **removed**; the power flow is the only grid the market reads, and the options around it (loss allocation, fee signals from measured loading and voltages) are developed instead of keeping a second grid method compatible. The fee options (`dso.voltage_drop`, `dso.losses`, eq. 18) stay: they are [P1]'s fee formulas, not the graph model

**Why.** (1) Not bounded by physical reality: the capacity split gives each edge a share of one total in inverse proportion to its length, but on a radial feeder every line on the main path carries the whole downstream load, so capacity is not additive; on IEEE-34 with [P2]'s own 1800 kW the split gives 7.5 / 44 / 185 kW per line (min / median / max) while the head line carries the full feeder load, and with the release's default of 1e6 kW nothing ever congests. (2) Awkward to compare: it sees only the trades (no background, no untraded energy, no direction), so every comparison needed extra choices (the total capacity, ratings, the voltage drop by distance) and would measure those choices rather than a method. (3) Keeping both costs effort in every new feature for no research value: on a network with real ratings and an AC power flow it adds nothing the power flow does not measure better

**Evidence.** The annotated tag [`v2-graph-model`](https://github.com/KevinRapo/P2P-thesis/tree/v2-graph-model) (commit 2fa9296, `git show v2-graph-model`) keeps the last version with both methods

**Implemented in.** `core/grid/graph.py`, `grid.method`, `graph_capacity`, `graph_total_kw`, `StepRecord.signal` and the Studio's fields removed; the DSO always observes the power flow ([Market step, 5. Grid](../methodology/market/step.md#5-grid)). Old scenario and run files that carry the keys still load

### MP-1f: Untraded energy pays the DSO's grid fees

*11 Nov 2026*

Everything a participant settles with the DSO pays the same grid fees: its **stage-3 trades and its untraded energy**. The untraded energy is an implicit trade with the DSO (stage 4) at the tariff it is settled at, along the participant's path to the transformer, and the participant pays the whole fee, as for a DSO trade (`fees_charged` off: 0). Peer trades keep their path fees. Supersedes MP-1e's "without fees"

**Why.** The same kWh ordered to the DSO in stage 3 paid congestion, thermal, voltage and transmission fees, and the same kWh left untraded paid none, so with fees on, not ordering was the cheapest way to use the grid (a surplus orders nothing and is paid the feed-in tariff in full). The power flow carries both alike, since injections follow what the participants did, not their trades, so the fee should not depend on whether an order was placed. The incentive that makes a peer trade pay is unchanged: a peer trade avoids the DSO's tariff spread and the path to the transformer

**Evidence.** [`_untraded_trades`](../../core/market/lem.py#L702-L726) in the dry run of one midday step: P3's 4.15 kWh deficit untraded and ordered to the DSO pay the same fee, part by part (`tests/market/test_untraded_fees.py`). Rural1, 11-17 June 2016, `net_position` baseline: the stage-3 trades paid 13.4 EUR (1.3 % of their value) before MP-4l and MP-1f, and 137.0 EUR (13.0 %) after; that week no energy was untraded (the rule orders its whole net position), so the effect shows under no-order policies and RL

**Implemented in.** [`_charge_fees`](../../core/market/lem.py#L679-L700), `StepRecord.untraded`, `Dso.settle`, the baseline's and the trade tables' fee columns; [Market step, 6c](../methodology/market/step.md#6-fees). The calculated references `non_p2p` and the ceiling stay before-fees (the ceiling is still an upper bound: no fee is below 0, MP-4n)

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

*11 Nov 2026*

The imbalance fee ([P1] eq. 8b, 8h) is **off in the thesis scenario** (`imbalance_factor` 0 in `thesis_rural1.json`); the code stays, marked `# OPEN MP-4m`. Whether to keep it off, or replace it, stays open

**Why.** The release never charged it (M-30: $F_\text{imb}$ is 0 in every run), so off is its observable behaviour. Our reading of 8b/8h charges the side of a DSO trade that worsens the order book's balance $B$ (offered minus asked), scaled by $\min(q/\lvert B \rvert, 1)$: (1) the scale saturates near a balanced book, so a change of 0.02 kWh in $B$ moves 15 % of a trade's value from the buyer (about 1.35 EUR) to the seller (about 0.36 EUR) of the same step, and a bigger imbalance means a smaller fee; (2) $B$ is a sum over all orders that no actor sees before acting, so under DTDE and CTDE the fee is unpredictable for the actors and under CTCE, which sets every order, it is not: a bias in the comparison of the paradigms; (3) the price spread and the DSO path fees already make the DSO costly. Alternatives for later: a flat charge on the DSO-routed quantity, or a fee on $\min(q, \lvert B \rvert)$ (continuous, but still unobservable)

**Evidence.** Worked examples with the release's code (matching.py:319, dso.py:226, 247) and ours in the discussion of 11 Nov 2026; the week of 11-17 June 2016 paid no imbalance fee with the factor at 0.15, as the rule's orders are all on one side

**Implemented in.** `thesis_rural1.json`, [`imbalance_fee`](../../core/market/dso.py#L247-L273)

### MP-4n: A trade's fee is never below 0

*11 Nov 2026*

A trade's fee is **never below 0**: the zone bonus (eq. 8e) cancels the other parts but never pays out, so it is capped at their sum

**Why.** A negative fee paid a trade for existing: with no other fee a same-zone trade was paid 15 % of its value by the DSO. It also let the money ceiling's condition "fees count as nothing" (`ceiling.py`) hold only by assumption

**Evidence.** `tests/market/test_untraded_fees.py`: no trade of a played day has a negative fee

**Implemented in.** [`fees_of`](../../core/market/dso.py#L199-L245)

### MP-4f: Thermal threshold 0.8 in the thesis scenario

*11 Nov 2026*

The thesis scenario's `thermal_threshold` is **0.8**, the same as the congestion threshold (the code's default stays 0.2, the paper's). A first, untuned choice: the fee levels remain open

**Why.** With the transformer counted in $C_t$ (MP-4l) the paper's 0.2 charged every DSO settlement above 20 % transformer loading, and capped at 30 % of the value from 44 %: on rural1 the thermal part was 96.5 EUR of the 137 EUR the DSO trades paid in a June week

**Evidence.** Rural1, 11-17 July 2016, `net_position` and non-P2P with their fees on the same days: fees 90.6 to 23.9 EUR and 254.8 to 102.8 EUR with the slack reference (MP-4l) and 0.8 together

**Implemented in.** `thesis_rural1.json`; [open items](open.md) MP-4f

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

## RL (`RP-`)

### RP-3e: CTDE: own reward, a critic and an actor per agent

*24 Oct 2026*

CTDE uses each agent's own reward, one central critic per agent (input $[o_i, o_1, \dots, o_N]$) and one actor per agent (input $o_i$); no parameter sharing for now. A team-reward CTDE, a shared critic and group-wise policy sharing are in the parking lot

**Why.** The households are self-interested, each paying its own bill, and [P2] defines CTDE on each agent's own return (eq. 18-19). With individual rewards every critic learns a different value function, so nothing is duplicated; the per-agent central critic for agents with their own rewards is MADDPG's design (Lowe et al. 2017). A shared critic would cost the same operations per step and could only gain data efficiency, at the risk of interference between different households

**Evidence.** Discussion of 24 Oct 2026 (MAPPO's shared critic assumes a team reward, Yu et al. 2022 §3)

**Implemented in.** no code change: [ctde.py](../../core/rl/ctde.py), [config.py](../../core/rl/config.py)

### RP-4a: Logging the KL with weight 0

*25 Oct 2026*

The KL between the collecting and the updated policy is computed and logged (`mean_kl_loss`) with weight 0 in the loss: `use_kl_loss=True`, `kl_coeff=0.0`

**Why.** PPO's most direct measure of each update's size; RLlib computes it only with `use_kl_loss=True`, and with coefficient 0 its adaptive weight stays 0. L-07's risk (a non-finite KL making the loss NaN unnoticed) is covered: training stops on any non-finite metric

**Evidence.** Discussion of 24-25 Oct 2026; probe 9's frozen level, where the update size is the question

**Implemented in.** [rl_defaults.py](../../core/rl_defaults.py), [config.py](../../core/rl/config.py)

### RP-1f: The market day stays terminated

*26 Oct 2026*

By default the market day stays **terminated**; `episode_days`, `truncate_episode` and `terminal_value` (31 Oct 2026) make the alternatives an experiment, `day_end.json`: each day is a task of its own, the return ends at midnight. Truncating it (bootstrapping into the next day) was implemented and reverted the same day

**Why.** Truncation is only consistent if the critic learns the value of the states it bootstraps from; with every day starting fresh (battery at its initial charge, reputation 0.5) it would estimate a continuation the environment never plays. The consistent alternatives (a random state at reset, or several consecutive days per episode with the state carried over) change how training and evaluation are organised: kept for after the simple system works. Accepted limitation: the agents optimise one day, and energy left in the battery at midnight is worth nothing to them (MP-1c)

**Evidence.** Discussion of 26 Oct 2026

**Implemented in.** [market_env.py](../../core/env/market_env.py) (`step`, docstring "Episodes")

### RP-2a: When the RL layer counts as ready for the market

*26 Oct 2026*

The RL layer counts as ready for the market when, with the market's network and default settings: probes 1-3, 8a and 10 pass in every paradigm and seed; the learning probes 4, 5, 6, 7 and 9 pass in CTDE and DTDE for at least 2 of 3 seeds within 4 times their budget; CTCE either does too or its shortfall is measured and documented; 8b is measured, not judged; the KL per update stays in a usual range

**Why.** A fixed target for the probe work: what the probes can show (the plumbing and the learner work, with exact answers) and what they cannot (the market's optimum). CTDE and DTDE carry the thesis's comparison; CTCE's joint ratio and summed reward (L-02) make it slower by design

**Evidence.** Met on 26 Oct 2026 with RP-3h and RP-6b: CTDE and DTDE 29 of 30 on the learning probes (probe 7 DTDE 2 of 3), every plumbing probe in every paradigm and seed, median KL 0.005. CTCE: 8 of 15 at 4 times the budget, not converging at 8 times on probes 5 and 6 (`runs/@taltech/probes_screen_3e-4_500_64_10/`)

**Implemented in.** [docs/methodology/validation/probes.md](../methodology/validation/probes.md)

### RP-6b: PPO's training settings

*26 Oct 2026*

PPO's training settings: learning rate 3e-4, batch 500 environment steps, minibatches of 64, 10 epochs (160 gradient steps per 1,000 environment steps); the rest unchanged (grad_clip 0.5, entropy 0.01, clip 0.2)

**Why.** Market steps are expensive (a power flow each), so the settings that learn most per sample are the ones to use. The original's lr 1e-5 with one minibatch of 4000 and 5 epochs moved the policy almost nothing (median KL 0.0014, log std unchanged); lr 1e-3 on the 2 x 256 network was too aggressive (KL 0.016, log std collapsing to -3.7); every batch of 2000 or 4000 made too few updates in the probes' budgets. These are Stable-Baselines3's PPO defaults (lr 3e-4, minibatch 64, 10 epochs) with a batch of 500. A larger batch may still learn at the market's budget (more updates, less noise): not tested

**Evidence.** Screen of 26 Oct 2026: 8 settings x probes 4-7, 9 x 3 paradigms x 3 seeds, market network with SM, 4 times each probe's budget in environment steps (`runs/@taltech/probes_screen_*/`): 3e-4/500/64/10 passes 29 of 30 in CTDE/DTDE; the original's 3 of 30

**Implemented in.** [rl_defaults.py](../../core/rl_defaults.py)

### RP-3h: The continuous action parts: log std and mean

*26 Oct 2026*

The continuous action parts: one learned log std per part for every state (MAPPO's `DiagGaussian`), and each part's mean through tanh (`free_log_std_parts`, `bound_mean` in [rl_defaults.py](../../core/rl_defaults.py)); no bounds on the log std

**Why.** RLlib's state-dependent log std shrank faster than the categorical part it depends on was decided, after which the mean could not reach its target (probe 9: log std to −5.5, the level stuck at 0.1–0.35). The state-independent log std moves at most about the learning rate per step, slow enough for the mean to follow; the bounded mean keeps it inside the action's bounds, where the clipped reward is not flat. Bounding the log std alone (variant A) did not help

**Evidence.** Probe comparison of 26 Oct 2026, fast preset, 3 seeds (`runs/@taltech/probe_methods_scores.csv`): probe 9 in CTDE/DTDE 0/6 (RLlib) → 6/6 (SM); CTDE/DTDE 47/60 → 56/60 overall. Not solved by any variant: probe 6, CTCE

**Implemented in.** [modules.py](../../core/rl/modules.py), [rl_defaults.py](../../core/rl_defaults.py)

### RP-3a: CTCE's entropy bonus is divided by the number of agents

*10 Nov 2026*

`entropy_coeff` is **per agent**, and CTCE divides it by the number of agents $N$ (13: 0.01 becomes 0.00077) in [`build_config`](../../core/rl/config.py), as MAPPO averages over agents. The summed group reward stays (RP-3b). A setting that wants the old joint bonus writes 0.13 (0.01 × 13). Before this change CTCE trained with the full 0.01 on the joint entropy, so CTCE results from before 10 Nov 2026 and after it are not comparable.

**Why.** CTCE's one joint policy has the action parts of all $N$ agents, so its entropy is a sum over $4N$ parts, while PPO's surrogate has one standardised advantage per step and clips one joint ratio. With one coefficient the bonus weighed about $N$ times what it does for one DTDE agent, and nothing clips it, so it kept pushing the policy's spread up. Dividing by $N$ gives each agent's parts the weight they have in DTDE. PPO's clip widened by $\sqrt{N}$ (27 Oct 2026) was tried as a probe and experiment variant only, and is not in the defaults: `clip_param` is 0.2 in every paradigm.

**Evidence.** The experiment `ctce_entropy` (26 Oct 2026, TalTech; market_s2, CTCE, 13 agents, one seed, 240k steps; `runs-old/old/ctce_entropy`). With the joint 0.01 the group's entropy rose from 80 to 130 and the team return stayed below 0 (−1.0 at the end, between −1.3 and −0.1 over the last six evaluations). With 0.01 / 13 the entropy fell to 45 and the return reached 1.6; with 0 it fell to 38 and the return was 1.2. One seed, and not the thesis scenario. On the probes (3 agents) the entropy was not why CTCE misses probes 4 to 6 ([probes](../methodology/validation/probes.md#why-ctce-misses-probes-4-6-26-october-2026)). Since this change every CTCE run has trained with the divided value: `combo_ctce` records `entropy_coeff` 0.00077 in its `run.json`

**Implemented in.** [config.py](../../core/rl/config.py) (`build_config`), `tests/rl/test_6_ctde_structure.py` (`test_ctce_weighs_the_entropy_per_agent`), commit `2e0d907`; [learning](../methodology/learning/index.md#ctce) (the paradigms) and C5 of [the iteration](../methodology/learning/examples/iteration.md)

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
