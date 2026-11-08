# Open items

The single list of everything that is undecided in V2. Nothing is deleted from it:
an item stays when it is decided, with its status changed. A status is one of
`inbox` (noticed, not yet looked at), `open`, `parked` (on purpose, for later) or
`decided → [decision log](decisions.md)` (with the log row it went to). The
[plans](index.md) only list these IDs in their stages. In the code an open question is
a marker `# OPEN <ID>: question` whose ID is in this table, and a quick reminder is
`# ! note`, which is triaged into this list at the end of a session
([Markers](index.md#markers-the-plans-are-big-everything-else-is-small)).

An ID is a register ID (`E-`, `M-`, `L-`), a plan ID (`MP-`, `RP-`) or, for a thesis
question, `TH-`. An ID marked *(proposed)* is not yet in a plan: it takes the next free
letter of the stage it fits, and becomes a plan decision when its stage poses it.

| ID | Question | Where | Status | Stage | Added |
|---|---|---|---|---|---|
| E-10 | The KPIs' window: the day so far (now); the papers give none | [market_env.py:718](../../core/env/market_env.py#L718), [reward.py:338](../../core/env/reward.py#L338), [signals.py:84](../../core/market/signals.py#L84); [Observation](../methodology/environment/observation.md#implicit-cooperation-kpis-10-the-same-for-every-agent) | open | — | 2026-11-03 |
| E-07 | A signal with nothing to measure enters as 0, which is also a real value for the local price and its advantage | [market_env.py:729](../../core/env/market_env.py#L729); [Observation](../methodology/environment/observation.md#missing-values) | open | — | 2026-11-03 |
| E-05 | True future demand and generation in the observation, without the paper's forecast error | [signals.py:281](../../core/market/signals.py#L281), [signals.py:294](../../core/market/signals.py#L294) | open | — | 2026-11-03 |
| E-08, E-11 | Supply-demand imbalance over each step's orders, with the order volume standing in for $C_\text{grid}$ | [signals.py:35](../../core/market/signals.py#L35) | open | — | 2026-11-03 |
| E-09 | Social welfare as the sum of $p \cdot q$ (turnover), not surplus | [signals.py:65](../../core/market/signals.py#L65) | open | — | 2026-11-03 |
| E-12 | DER self-consumption as the peer share of the energy traded | [signals.py:120](../../core/market/signals.py#L120) | open | — | 2026-11-03 |
| E-13, E-20 | The KPIs enter the reward raw; no source gives the ranges that would keep them in [0, 1] | [reward.py:208](../../core/env/reward.py#L208) | open | — | 2026-11-03 |
| E-16 | The grid terms read $B_\text{grid}$ before the DSO clears (the original's was always 0) | [reward.py:387](../../core/env/reward.py#L387) | open | — | 2026-11-03 |
| MP-6a | Which KPIs are reported next to the bill; the DSO's trades in them, $q_\text{available}$, the DSO's balance | [signals.py:70](../../core/market/signals.py#L70), [signals.py:125](../../core/market/signals.py#L125), [signals.py:162](../../core/market/signals.py#L162), [signals.py:200](../../core/market/signals.py#L200) | open | Market 6 | 2026-11-03 |
| RP-1g (proposed) | The grid capacity $C$ of the `salazar` reward: SimBench has no single one, so a run must state it | [reward.py:332](../../core/env/reward.py#L332) | open | — | 2026-11-03 |
| MP-4g (proposed) | Is the `GridModel` protocol still a point to use? | [contract.py:275](../../core/grid/contract.py#L275) | open | — | 2026-11-03 |
| MP-1d (proposed) | Why does a battery without a power limit return `inf` for its power cap? | [battery.py:69](../../core/market/agent/battery.py#L69) | open | — | 2026-11-03 |
| MP-2d (proposed) | Should the order bound (net position) also include the battery's power constraint? | [der.py:175](../../core/market/agent/der.py#L175) | open | — | 2026-11-03 |
| MP-3c (proposed) | Scale the two parts of the rule-based partner score, or not? | [der.py:227](../../core/market/agent/der.py#L227) | open | — | 2026-11-03 |
| MP-3d (proposed) | `BID_ASK_SPREAD` and `NASH_BARGAINING` give the same price as `average` at factor 0.5 | [clearing_price.py:54](../../core/market/clearing_price.py#L54), [clearing_price.py:58](../../core/market/clearing_price.py#L58) | open | — | 2026-11-03 |
| M-02 | Invalid orders in general: cut, reject or penalise | [validation/market.md](../original/issues/market.md); [M-02](../original/issues/register.md#M-02) | open | — | 2026-11-03 |
| M-11 | Weighting of the rule-based partner choice (50/50 now) | [validation/market.md](../original/issues/market.md); [M-11](../original/issues/register.md#M-11) | open | — | 2026-11-03 |
| M-19 | Battery power from SimBench or set by hand | [validation/market.md](../original/issues/market.md); [M-19](../original/issues/register.md#M-19) | open | — | 2026-11-03 |
| M-23 | Demand satisfied and the battery's discharge | [validation/market.md](../original/issues/market.md); [M-23](../original/issues/register.md#M-23) | open | — | 2026-11-03 |
| M-28 | The transmission fee $F_\text{trans}$ (no formula in [P1]) | [validation/market.md](../original/issues/market.md); [M-28](../original/issues/register.md#M-28) | open | — | 2026-11-03 |
| M-30 | Which DSO trade could help the balance (imbalance fee) | [validation/market.md](../original/issues/market.md); [M-30](../original/issues/register.md#M-30) | open | — | 2026-11-03 |
| M-31 | DSO trades and the grid | [validation/market.md](../original/issues/market.md); [M-31](../original/issues/register.md#M-31) | open | — | 2026-11-03 |
| M-32 | The thermal fee's threshold | [validation/market.md](../original/issues/market.md); [M-32](../original/issues/register.md#M-32) | open | — | 2026-11-03 |
| M-33, M-34 | Zones as feeders and the zone bonus | [validation/market.md](../original/issues/market.md); [M-33](../original/issues/register.md#M-33), [M-34](../original/issues/register.md#M-34) | open | — | 2026-11-03 |
| M-43 | Reputation decay | [validation/market.md](../original/issues/market.md); [M-43](../original/issues/register.md#M-43) | open | — | 2026-11-03 |
| M-45 | Whether one day is long enough for reputation to mean anything | [validation/market.md](../original/issues/market.md); [M-45](../original/issues/register.md#M-45) | open | — | 2026-11-03 |
| L-01 | The CTDE critic's input | [validation/rl.md](../original/issues/rl.md); [L-01](../original/issues/register.md#L-01) | open | — | 2026-11-03 |
| L-02 | CTCE as a centralised-information baseline, not an upper bound | [validation/rl.md](../original/issues/rl.md); [L-02](../original/issues/register.md#L-02) | open | — | 2026-11-03 |
| L-03 | How returns are compared across paradigms | [validation/rl.md](../original/issues/rl.md); [L-03](../original/issues/register.md#L-03) | open | — | 2026-11-03 |
| L-14 | The training budget, counted in environment steps | [validation/rl.md](../original/issues/rl.md); [L-14](../original/issues/register.md#L-14) | open | — | 2026-11-03 |
| L-17 | Evaluation protocol and seeds | [validation/rl.md](../original/issues/rl.md); [L-17](../original/issues/register.md#L-17) | open | — | 2026-11-03 |
| RP-2b | The policy is factorised: it cannot name a partner conditionally on the side | [RL plan, stage 2](rl.md#stage-2-the-learner-on-known-answers-probes) | open | RL 2 | 2026-11-03 |
| RP-6a | The budget and the untuned market hyperparameters (`market_ppo.json` still gives batch 2400 and minibatch 240 over RP-6b's) | [RL plan, stage 6](rl.md#stage-6-budget-and-hyperparameters), [market_ppo.json](../../config/experiments/market_ppo.json) | open | RL 6 | 2026-11-03 |
| MP-4e | The graph model's parameters on SimBench (the comparison's second arm) | [Market plan, stage 4](market.md#stage-4-grid-and-fees), [grid methods](../methodology/market/grid-methods.md) | open | Market 4 | 2026-11-03 |
| TH-1 (proposed) | Thesis: which parts belong in the main text and which in the appendices | workspace `AGENTS.md`, Open points | open | — | 2026-11-03 |
| RP-1a | "No order": the 0.05 quantity threshold (now) or a third `side` category | [RL plan, stage 1](rl.md#stage-1-the-decision-problem-the-mdp), [Action](../methodology/environment/action.md) | open | RL 1 | 2026-11-03 |
| RP-6c (proposed) | Ray's start-up occasionally fails when memory is short (several runs in parallel each start their own Ray) | [Resources and parallelism](../using/hpc/resources.md) | open | — | 2026-11-03 |
| MP-1e | Settle untraded energy with the DSO, and whether fees apply to it (the fee asymmetry) | [Market plan, MP-1b](market.md#stage-1-energy-and-the-battery), [Settlement](../methodology/market/step.md#4-settlement) | decided → [decision log](decisions.md) | — | 2026-11-03 |
| MP-2e (proposed) | Clamp order prices to the step's peer ceiling or to the static `max_price` | [Market plan, MP-2b](market.md#stage-2-orders), [Orders](../methodology/market/step.md#2-orders) | open | — | 2026-11-03 |
| RP-1h (proposed) | Drop the DSO as a partner choice | [Action](../methodology/environment/action.md) | open | — | 2026-11-03 |
| RP-1d | The reward's scale (Salazar's divided by 20, the bill's by the 99th percentile) | [Reward](../methodology/environment/reward.md#the-rewards-to-choose-from), [RL plan, stage 1](rl.md#stage-1-the-decision-problem-the-mdp) | open | RL 1 | 2026-11-03 |
| MP-1c | The end-of-day value of stored energy (`terminal_value`), including the units fix in `Reward.stored_energy` | [Market plan, stage 1](market.md#stage-1-energy-and-the-battery), [Reward](../methodology/environment/reward.md#the-rewards-to-choose-from), [day_end.json](../../config/experiments/day_end.json) | open | Market 1 | 2026-11-03 |
| RP-1i (proposed) | The observation set: pruned plus day-ahead utility prices, the paper's 42 for the Salazar arm | [Observation](../methodology/environment/observation.md) | open | — | 2026-11-03 |
| RP-7f (proposed) | Evaluation in three levels, and the table of what each level is for | [Results plan](results.md) | open | — | 2026-11-03 |
| RP-7g (proposed) | The VTI ceiling: the end condition of the batteries and whether fees count | [Results plan](results.md) | open | — | 2026-11-03 |
| MP-6c (proposed) | Battery self-consumption in the non-P2P baseline | [Market plan, stage 6](market.md#stage-6-the-market-as-a-whole) | decided → [decision log](decisions.md) (with MP-1e: non-P2P is `zero`, its batteries following each owner's balance) | — | 2026-11-03 |
| RP-7h (proposed) | `difference()` pairs runs without regard to the participants | [results.py](../../core/runner/results.py) | open | — | 2026-11-03 |
| MP-4h (proposed) | The peer charge: 0 in the main runs, or a referenced value (§42c 0.2294, Austria-like about 0.14) as main setting or arm | [Tariffs and the peer charge](../methodology/market/tariffs.md#the-decision-mp-4h), [Market plan, stage 4](market.md#stage-4-grid-and-fees) | open | — | 2026-11-03 |
| RP-8a (proposed) | The CTCE update size (KL 0.1 to 0.17) for the reference experiment | [RL plan, stage 8](rl.md#stage-8-the-three-paradigms) | open | — | 2026-11-03 |
| RP-7i (proposed) | A time-resolution control on Market and Grid (step, hour of day, day, period), and a cumulative VTI curve: the step's gain over `non_p2p` divided by the period's reach, adding up to the VTI | [Results: time resolution](../using/studio/results/index.md#time-resolution) | parked | — | 2026-11-04 |
| RP-7j (proposed) | A scorecard heatmap at the top of Market and Grid: a row per run, a column per indicator in its group, coloured by better or worse than `zero` | [Metrics](../using/studio/results/metrics.md) | parked | — | 2026-11-04 |
| RP-7k (proposed) | An average day on Market and Grid (24 hours, each step averaged over the test days, a line per run), and a duration curve of the line and transformer loading on Grid | [Market](../using/studio/results/market.md), [Grid](../using/studio/results/grid.md) | parked | — | 2026-11-04 |
