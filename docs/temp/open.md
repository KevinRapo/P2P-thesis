# Open items

The one list of every question about V2, open or decided. A decided item stays in its
section, with its status changed; a question that turns out not to be one is removed. A status is `inbox`
(noticed, not yet looked at), `open`, `parked` (on purpose, for later) or
`decided → ...`: what was chosen, with a link to where it is implemented or to the
[decision log](decisions.md) row that gives the reason. The order of the work and the
rules for markers are on the [work plan](index.md).

An ID is a register ID (`E-`, `M-`, `L-`), or `MP-` (market), `RP-` (RL and results)
or `TH-` (thesis). A row with two IDs is one question known under both. A new question
takes the next free letter of its topic and is marked *(proposed)* until its section is
worked on.

The sections are ordered by how much they change the thesis's results, most first. *(run setting)* marks a question that an experiment's configuration answers, with no change to the code.

## 1. The grid-method comparison

What decides the thesis's main result; settled together with a check without learning.

| ID | Question | Where | Status | Added |
|---|---|---|---|---|
| MP-4i (proposed) | The grid stress: on SimBench's networks no fee is charged (line loading peaks at 38 % in June and July), so the comparison needs a stressed scenario. How: decided (10 Nov 2026), three factors on the whole network's power, participants included (`grid.load_scale`, `generation_scale`, `storage_scale`). Open: the level | [Grid methods experiment](../experiments/thesis/grid-methods.md#consistency-between-the-arms) | open | 2026-11-10 |
| MP-4e | The graph model's parameters on SimBench: the total capacity of the split by length or the lines' ratings, $f_\text{volt}$, the voltage-drop cap, the transformer | [Grid methods](../methodology/market/grid-methods.md), [Grid methods experiment](../experiments/thesis/grid-methods.md#parameters) | open | 2026-10-22 |
| MP-4f | The fee factors' and thresholds' values ([P1] gives none; the release's are used) *(run setting)* | [Market step, 6. Fees](../methodology/market/step.md#6-fees) | open | 2026-10-22 |
| MP-1c | The end-of-day value of stored energy: worth nothing at midnight now, because the next day starts at the initial charge. Keep, value it (`terminal_value`), or carry the charge over (`episode_days`, `truncate_episode`) *(run setting)* | [Reward](../methodology/environment/reward.md#the-rewards-to-choose-from), [day_end.json](../../config/experiments/day_end.json) | open | 2026-10-22 |
| MP-4h | The peer charge: 0 in the main runs, or a referenced value (§42c 0.2294, Austria-like about 0.14) as main setting or arm *(run setting)* | [Tariffs and the peer charge](../methodology/market/tariffs.md#the-decision-mp-4h) | open | 2026-11-03 |
| MP-4j, M-40, M-41 | Who pays the network's losses with the power flow: eq. 18 per trade (kappa times distance times quantity, whatever the lines carry), or the measured losses shared out | [losses.py](../../core/grid/losses.py), [Adding an option](../methodology/architecture/development/options.md) | decided → [Market step, 6. Fees](../methodology/market/step.md#6-fees): `dso.losses`; the power-flow arms share the measured losses by branch currents (BCDLA), each participant paying its share at the step's utility price, credits paid back; the graph arms keep eq. 18 (10 Nov 2026) | 2026-11-10 |
| MP-0a | The scenario and days of the experiments, hourly or 15-minute steps. Its batteries are decided (10 Nov 2026): every battery has a power limit *(run setting)* | [thesis_rural3_p13.json](../../config/scenarios/thesis_rural3_p13.json), [Market runs](../experiments/market-s3.md) | open | 2026-10-22 |
| MP-0b | The DSO's tariffs: flat or changing over the day | [Tariffs](../methodology/market/tariffs.md) | decided → [decision log](decisions.md): a price per step from a file (now `de_2024`) | 2026-10-22 |
| M-28, MP-4a | The transmission fee $F_\text{trans}$ (no formula in [P1]) | [M-28](../original/issues/register.md#M-28) | decided → [Market step, 6. Fees](../methodology/market/step.md#6-fees): the loss at the trade price | 2026-11-03 |
| M-30, MP-4b | Which DSO trade could help the balance (imbalance fee) | [M-30](../original/issues/register.md#M-30) | decided → [Market step, 6. Fees](../methodology/market/step.md#6-fees): charged when the DSO trade worsens the balance | 2026-11-03 |
| M-31 | DSO trades and the grid | [M-31](../original/issues/register.md#M-31) | decided → [Market step, 6. Fees](../methodology/market/step.md#6-fees): the path to the transformer | 2026-11-03 |
| M-32, MP-4c | The thermal fee's threshold (0.2) far below the congestion one (0.8) | [M-32](../original/issues/register.md#M-32) | decided → [Market step, 6. Fees](../methodology/market/step.md#6-fees): kept at 0.2, its own setting; its value may change with MP-4f | 2026-11-03 |
| M-33, M-34, MP-4d | Zones as feeders and the zone bonus | [M-33](../original/issues/register.md#M-33), [M-34](../original/issues/register.md#M-34) | decided → [Market step, 6. Fees](../methodology/market/step.md#6-fees): zones are feeders, bonus 0.15; its value may change with MP-4f | 2026-11-03 |
| M-19 | Battery power from SimBench or set by hand | [M-19](../original/issues/register.md#M-19) | decided → [Market step, 2. Orders](../methodology/market/step.md#2-orders): the power from SimBench | 2026-11-03 |
| MP-1d | Why does a battery without a power limit return `inf` for its power cap? | [battery.py](../../core/market/agent/battery.py#L66-L86) | decided → [Battery](../../core/market/agent/battery.py#L66-L86): no unlimited battery any more; `max_power_kw` is required, and every step is bounded by both the stored energy and the power limit over the step (10 Nov 2026) | 2026-11-03 |
| MP-2d | Should the order bound (net position) also include the battery's power constraint? | [der.py](../../core/market/agent/der.py#L178-L192) | decided → [Market step, 2. Orders](../methodology/market/step.md#2-orders): already included: the bound adds the battery's chargeable or dischargeable energy, which the power limit caps | 2026-11-03 |
| M-23 | Demand satisfied and the battery's discharge | [M-23](../original/issues/register.md#M-23) | decided → [Market step, 4. Settlement](../methodology/market/step.md#4-settlement): discharge counts towards demand | 2026-11-03 |

## 2. Learning on the market

What decides whether the mixed action learns the market: what an agent may do, what it
is paid, what it sees, and how PPO trains it.

| ID | Question | Where | Status | Added |
|---|---|---|---|---|
| RP-1h | Drop the DSO as a partner choice | [Action](../methodology/environment/action.md) | decided → [Action](../methodology/environment/action.md#the-mixed-action): dropped; the partner is a peer or nobody, since an order without a peer clears with the DSO anyway (10 Nov 2026) | 2026-11-03 |
| RP-1a | "No order": the 0.05 quantity threshold (now) or a third `side` category | [Action](../methodology/environment/action.md) | open | 2026-10-22 |
| RP-2b | The policy is factorised: it cannot name a partner conditionally on the side (an autoregressive policy only if probe 9 and the first market runs show it is needed) | [Probes](../methodology/validation/probes.md) | open | 2026-10-22 |
| MP-2c | Selling from the battery while the household itself has a deficit: eq. 15 allows it. Keep, or let a household sell only after its own load is covered | [Market step, 2. Orders](../methodology/market/step.md#2-orders) | decided → [Market step, 2. Orders](../methodology/market/step.md#2-orders): no: the battery covers the household's own deficit first, only the rest is for sale (10 Nov 2026) | 2026-10-22 |
| MP-5b | Reputation's start value and horizon: 0.5 every day (now), or carried over between days; whether one day is long enough for it to mean anything *(run setting)* | [Market step, 8. Reputation](../methodology/market/step.md#8-reputation-and-advance) | open | 2026-10-22 |
| MP-5c | Reputation's weights (0.3 / 0.2 / 0.5) and the three scores' formulas | [Market step, 8. Reputation](../methodology/market/step.md#8-reputation-and-advance) | open | 2026-10-22 |
| RP-1d | The reward's scale (Salazar's divided by 20, the bill's by the 99th percentile) *(run setting)* | [Reward](../methodology/environment/reward.md#the-rewards-to-choose-from) | open | 2026-10-22 |
| RP-1i (proposed) | The observation set: pruned plus day-ahead utility prices, the paper's 42 for the Salazar arm | [Observation](../methodology/environment/observation.md) | open | 2026-11-03 |
| RP-1k (proposed) | The grid in the observation: an agent sees nothing of the grid where it is, only the mean loading over all lines (`grid_congestion`) and $B_\text{grid}$; the fees reach it only through the reward. A signal for the loading on its own path, read from what the fees read | [signals.py](../../core/market/signals.py#L94-L101), [Observation](../methodology/environment/observation.md) | open | 2026-11-10 |
| RP-1l (proposed) | What an agent knows of its peers for the partner choice: only their reputations, not who has a surplus or a deficit now. Add the peers' last net positions, or state that the choice is learned blind, as in [P1] | [market_env.py](../../core/env/market_env.py) | open | 2026-11-10 |
| RP-1j (proposed) | γ over a 24-step day: 0.99 (now, almost undiscounted) or 1.0 *(run setting)* | [rl_defaults.py](../../core/rl_defaults.py) | open | 2026-10-22 |
| RP-3a | The entropy term: 0.01 × the sum over the action parts (4 per agent, 4N in CTCE); or divided by N in CTCE, 0, or per-part weights | [rl_defaults.py](../../core/rl_defaults.py) | decided → [config.py](../../core/rl/config.py): `entropy_coeff` is per agent; CTCE divides it by N (10 Nov 2026) | 2026-10-22 |
| RP-3b | CTCE's group reward: the sum of the agents' rewards (now) or their mean | [ctce.py](../../core/rl/ctce.py) | decided → [ctce.py](../../core/rl/ctce.py): the sum stays (10 Nov 2026) | 2026-10-22 |
| RP-3c | The value scale: no value normalisation, advantages standardised per module (now); or value normalisation (PopArt) | [config.py](../../core/rl/config.py) | open | 2026-10-22 |
| RP-3d | One Adam and one gradient clip (0.5) over actor and critic (now), or separate ones | [config.py](../../core/rl/config.py) | open | 2026-10-22 |
| RP-3g | The clip range ε: 0.2 per agent and one joint ratio in CTCE (now); keep and state its dependence on N | [rl_defaults.py](../../core/rl_defaults.py) | open | 2026-10-22 |
| RP-5a | Whether the full action stays the thesis's action, or a simpler one (side from the net position, or no partner) with a stated reason, if the first market runs do not beat the rule | [Action](../methodology/environment/action.md) | open | 2026-10-22 |
| RP-8a (proposed) | The CTCE update size (KL 0.1 to 0.17) for the reference experiment *(run setting)* | [Training cycle](../methodology/learning/index.md) | open | 2026-11-03 |
| RP-6c (proposed) | Ray's start-up occasionally fails when memory is short (several runs in parallel each start their own Ray) | [Resources and parallelism](../using/running/hpc/resources.md) | open | 2026-11-03 |
| RP-1b | The action's price range | [Action](../methodology/environment/action.md) | decided → [Action](../methodology/environment/action.md): [FiT, utility] | 2026-10-22 |
| RP-1c | The action's quantity | [Action](../methodology/environment/action.md) | decided → [Action](../methodology/environment/action.md): a share of the eq. 15 bound | 2026-10-22 |
| RP-1f | The end of an episode: terminated at midnight, or truncated | [market_env.py](../../core/env/market_env.py) | decided → [decision log](decisions.md): terminated; the alternatives are settings | 2026-10-22 |
| RP-2a | When the learner counts as ready for the market | [Probes](../methodology/validation/probes.md#results) | decided → [decision log](decisions.md): the probe criteria, met 26 Oct 2026 | 2026-10-22 |
| RP-3e | Parameter sharing | [config.py](../../core/rl/config.py) | decided → [decision log](decisions.md): none, one actor and one critic per agent | 2026-10-22 |
| RP-3h | The continuous parts' log std | [modules.py](../../core/rl/modules.py) | decided → [decision log](decisions.md): one learned log std per part, the mean through tanh | 2026-10-26 |
| RP-4a | Logging the KL of every update | [rl_defaults.py](../../core/rl_defaults.py) | decided → [decision log](decisions.md): logged with weight 0 | 2026-10-25 |
| RP-6b | PPO's training settings | [rl_defaults.py](../../core/rl_defaults.py) | decided → [decision log](decisions.md): lr 3e-4, batch 500, minibatch 64, 10 epochs | 2026-10-26 |
| M-02, MP-2a | Invalid orders in general: cut, reject or penalise | [M-02](../original/issues/register.md#M-02) | decided → [Market step, 2. Orders](../methodology/market/step.md#2-orders): limited, not raised | 2026-11-03 |
| M-11, MP-3b | Weighting of the rule-based partner choice | [M-11](../original/issues/register.md#M-11) | decided → [Market step, 2. Orders](../methodology/market/step.md#2-orders): weighted score, weight 0.5 | 2026-11-03 |
| MP-3c | Scale the two parts of the rule-based partner score, or not? | [der.py](../../core/market/agent/der.py#L195-L234) | decided → [Market step, 2. Orders](../methodology/market/step.md#2-orders): both parts rescaled over the candidates (M-11) | 2026-11-03 |
| MP-1e, MP-1b | Untraded energy: what it costs or earns, and whether fees apply to it | [Settlement](../methodology/market/step.md#4-settlement) | decided → [decision log](decisions.md): settled at retail, without fees | 2026-10-22 |
| MP-5d | Reputation's role in the clearing | [Market step, 3. Clearing](../methodology/market/step.md#3-clearing) | decided → [decision log](decisions.md): prices in whole cents, reputation the tie-break | 2026-10-22 |
| E-05, RP-1e | True future demand and generation in the observation, without the paper's forecast error | [signals.py](../../core/market/signals.py#L280-L297) | decided → [The environment step](../methodology/environment/index.md#the-environment-step): the true future by default; `forecast_error` adds [P2]'s error (up to 30 %) as an option | 2026-11-03 |
| M-43, MP-5a | Reputation decay | [M-43](../original/issues/register.md#M-43) | decided → [Market step, 8. Reputation](../methodology/market/step.md#8-reputation-and-advance): a constant decay per hour, 0.8 | 2026-11-03 |
| M-45 | All agents start with the same reputation | [M-45](../original/issues/register.md#M-45) | decided → [Market step, 0. Reset](../methodology/market/step.md#0-before-the-day-reset): everyone starts at 0.5; the horizon is MP-5b | 2026-11-03 |

## 3. The evaluation protocol

How a result is measured, compared and trusted; needed before the final runs.

| ID | Question | Where | Status | Added |
|---|---|---|---|---|
| L-03 | How returns are compared across paradigms | [L-03](../original/issues/register.md#L-03) | decided → [Metrics](../methodology/evaluation/metrics.md#a-headline): never returns; held-out team money and the VTI, the same for every paradigm | 2026-11-03 |
| L-17 | Evaluation protocol and the number of seeds *(run setting)* | [L-17](../original/issues/register.md#L-17) | open | 2026-11-03 |
| L-02 | CTCE as a centralised-information baseline, not an upper bound | [L-02](../original/issues/register.md#L-02) | open | 2026-11-03 |
| L-01, RP-3f | The CTDE critic's input: $[o_i, o_1 \dots o_N]$ (now) or a pruned global state | [ctde.py](../../core/rl/ctde.py) | open | 2026-10-22 |
| RP-7c | Training and test days (now June and 1-14 July 2016): whether one season is enough *(run setting)* | [Days](../using/running/config.md#days) | open | 2026-10-22 |
| RP-7h | `difference()` pairs runs without regard to the participants | [results.py](../../core/runner/results.py) | decided → [indicators.py](../../core/runner/indicators.py): runs pair only with the same participants (`participant_set`), also for the baselines (10 Nov 2026) | 2026-11-03 |
| RP-7l | The last additions to what a run saves: the raw action outputs (what the policy asked for without an order), reputation's three parts, the code's `git diff` | [Files](../methodology/evaluation/files.md) | decided → [Files](../methodology/evaluation/files.md#heldout_agent_stepscsv): the raw action parts in every step row; no code diff, since a cluster run starts only from a clean commit (10 Nov 2026) | 2026-11-10 |
| RP-7m (proposed) | Replay a finished run's held-out evaluation from its checkpoint (a policy under the other grid method or prices) | [Files](../methodology/evaluation/files.md) | open | 2026-11-10 |
| MP-6d (proposed) | Market probes M5-M9 (M1-M4 are built, with the Studio's page) | [probes.py](../../core/market/probes.py) | open | 2026-10-26 |
| RP-7a | The team's score | [Metrics](../methodology/evaluation/metrics.md#a-headline) | decided → [Metrics](../methodology/evaluation/metrics.md#a-headline): the held-out team money, the participants' bills summed, with the VTI | 2026-10-22 |
| RP-7b | The statistic over seeds | [indicators.py](../../core/runner/indicators.py) | decided → [indicators.py](../../core/runner/indicators.py): below 5 seeds the mean and every seed; from 5 the mean with a 95 % percentile bootstrap over seeds; no IQM | 2026-10-22 |
| RP-7d, MP-6b | The baselines, and the reference for "good" | [Three yardsticks](../methodology/evaluation/index.md#three-yardsticks) | decided → [Three yardsticks](../methodology/evaluation/index.md#three-yardsticks): `net_position` (margin 0.3, no noise) played; the ceiling and `non_p2p` calculated; `zero` dropped (11 Nov 2026) | 2026-10-22 |
| RP-7f | Evaluation in three levels | [Files](../methodology/evaluation/files.md#three-levels) | decided → [Files](../methodology/evaluation/files.md#three-levels): saved, indicator, comparison | 2026-11-03 |
| RP-7g | The VTI ceiling: the end condition of the batteries and whether fees count | [The ceiling](../methodology/evaluation/index.md#the-ceiling) | decided → [The ceiling](../methodology/evaluation/index.md#the-ceiling): every battery ends at least as full as it started; fees count as nothing | 2026-11-03 |
| MP-6c | Battery self-consumption in the non-P2P baseline | [The floor](../methodology/evaluation/index.md#the-floor-non_p2p) | decided → [decision log](decisions.md) (with MP-1e: non-P2P is `zero`, its batteries following each owner's balance) | 2026-11-03 |

## 4. The `salazar` reward and the paper's 42 signals

Only matters if the reward and observation experiment stays in the thesis.

| ID | Question | Where | Status | Added |
|---|---|---|---|---|
| E-13, E-20 | The KPIs enter the reward raw; no source gives the ranges that would keep them in [0, 1] | [reward.py](../../core/env/reward.py#L213) | open | 2026-11-03 |
| RP-1g (proposed) | The grid capacity $C$ of the `salazar` reward: SimBench has no single one, so a run must state it | [reward.py](../../core/env/reward.py#L337) | open | 2026-11-03 |
| E-10 | The KPIs' window: the day so far (now); the papers give none | [market_env.py](../../core/env/market_env.py#L725), [reward.py](../../core/env/reward.py#L343), [signals.py](../../core/market/signals.py#L85); [Observation](../methodology/environment/observation.md#implicit-cooperation-kpis-10-the-same-for-every-agent) | open | 2026-11-03 |
| E-07 | A signal with nothing to measure enters as 0, which is also a real value for the local price and its advantage | [market_env.py](../../core/env/market_env.py#L738); [Observation](../methodology/environment/observation.md#missing-values) | open | 2026-11-03 |
| E-08, E-11 | Supply-demand imbalance over each step's orders, with the order volume standing in for $C_\text{grid}$ | [signals.py](../../core/market/signals.py#L36) | open | 2026-11-03 |
| RP-1m (proposed) | `coordination_score` is 1 − `supply_demand_imbalance`: the paper's observation holds one signal twice | [signals.py](../../core/market/signals.py#L104-L105) | open | 2026-11-10 |
| E-09 | Social welfare as the sum of $p \cdot q$ (turnover), not surplus | [signals.py](../../core/market/signals.py#L66) | open | 2026-11-03 |
| E-12 | DER self-consumption as the peer share of the energy traded | [signals.py](../../core/market/signals.py#L121) | open | 2026-11-03 |
| MP-6a, RP-7e | Which KPIs are reported next to the bill; the DSO's trades in them, $q_\text{available}$, the DSO's balance | [signals.py](../../core/market/signals.py#L71) | open | 2026-10-22 |
| E-16 | The grid terms read $B_\text{grid}$ before the DSO clears (the original's was always 0) | [reward.py](../../core/env/reward.py#L392) | decided → [The environment step](../methodology/environment/index.md#the-environment-step): the reward is the net bill; the `salazar` reward keeps it | 2026-11-03 |

## 5. Housekeeping

No effect on the results.

| ID | Question | Where | Status | Added |
|---|---|---|---|---|
| MP-2b, MP-2e | The market's own price bounds: [0, 1] now, or the tariffs' band; and whether an order's price is clamped to the step's peer ceiling or to the static `max_price` | [Market step, 2. Orders](../methodology/market/step.md#2-orders) | open | 2026-10-22 |
| MP-3d (proposed) | `BID_ASK_SPREAD` and `NASH_BARGAINING` give the same price as `average` at factor 0.5 | [clearing_price.py](../../core/market/clearing_price.py#L54-L58) | open | 2026-11-03 |
| MP-4g | Is the `GridModel` protocol still a point to use? | [contract.py](../../core/grid/contract.py) | decided → removed: nothing used it, and `GraphGrid` did not follow it (10 Nov 2026) | 2026-11-03 |
| TH-1 (proposed) | Thesis: which parts belong in the main text and which in the appendices | workspace `AGENTS.md`, Open points | open | 2026-11-03 |

## Parked

| ID | Question | Where | Status | Added |
|---|---|---|---|---|
| RP-7i (proposed) | A time-resolution control on Market and Grid (step, hour of day, day, period), and a cumulative VTI curve: the step's gain over `non_p2p` divided by the period's reach, adding up to the VTI | [Results: time resolution](../methodology/evaluation/metrics.md#time-resolution) | parked | 2026-11-04 |
| RP-7j (proposed) | A scorecard heatmap at the top of Market and Grid: a row per run, a column per indicator in its group, coloured by better or worse than `net_position` | [Metrics](../methodology/evaluation/metrics.md) | parked | 2026-11-04 |
| RP-7k (proposed) | An average day on Market and Grid (24 hours, each step averaged over the test days, a line per run), and a duration curve of the line and transformer loading on Grid | [Market](../using/studio/experiments/results/market.md), [Grid](../using/studio/experiments/results/grid.md) | parked | 2026-11-04 |
| RP-9a (proposed) | SAC with the mixed action, as a second algorithm | top-level `AGENTS.md` | parked | 2026-10-22 |
| RP-9b (proposed) | A shared central critic estimating each agent's own value, or one policy per kind of household (selective parameter sharing), against the per-agent critics of RP-3e | [config.py](../../core/rl/config.py) | parked | 2026-10-24 |
