# Reward and observation

> The original's reward and observation against ours. **Status: set up, not
> run;** to be outlined.

## Scenario

For now the thesis scenario,
[`thesis_rural3_p13.json`](../../../config/archive/scenarios/thesis_rural3_p13.json), on the
power flow:

| Setting | Value | Why |
|---|---|---|
| Network | `1-LV-rural3--2-sw`: 13 participants on 13 of its 43 prosumer buses; the other 30 buses follow their SimBench profiles as background | Large enough to learn reliably, and the background is part of what the power flow sees ([Market runs](../market-s3.md)) |
| Prices | `de_2024`: German day-ahead prices of 2024 as a dynamic tariff ([Prices](../../using/data/prices.md)) | Real prices that change every hour |
| Peer charge | 0: [P1]'s market | MP-4h is open ([Tariffs](../../methodology/market/tariffs.md#the-decision-mp-4h)) |
| Grid | AC power flow; voltage drop measured along the trade's path | The power flow is this thesis's grid ([Market step](../../methodology/market/step.md#5-grid)) |
| Days | Training on June 2016; held-out test on 1-14 July 2016 | Summer: PV, so surplus to trade |
| Learning | PPO with [RLlib defaults as changed here](../../methodology/learning/index.md#2-everything-we-change-in-rllibs-ppo), no tuning; 240k environment steps; 5 seeds (0-4) | The budget and seeds are provisional (L-14, L-17) |
| Evaluation | 10 points during training, 5 episodes each; every test day once at the end | Held-out bill per participant (`heldout_agents.csv`) |

Each run has 8 environment runners, on TalTech `blackwell1` (10 CPUs, 12 GB, 4 h).

## Arms and settings

[`thesis_reward_obs.json`](../../../config/archive/experiments/thesis_reward_obs.json):
4 arms × 2 paradigms (CTDE, DTDE) × 5 seeds = 40 runs, on the power flow.

**Question.** Do agents trained with our reward and observation do better for the
participants than with the original's?

| Arm | Reward | Observation |
|---|---|---|
| `salazar_paper` | the original code's ([Reward](../../methodology/environment/reward.md)) | the paper's 42 signals ([Observation](../../methodology/environment/observation.md)) |
| `salazar_pruned` | the original code's | the pruned 22 |
| `bill_paper` | the participant's own bill | the paper's 42 |
| `bill_pruned` | the participant's own bill | the pruned 22 |

The `salazar` reward needs a grid capacity: 400 kWh per step, the transformer's
0.4 MVA over one hour (RP-1g).

**What is compared.** The held-out bill per participant and the
[indices](../../methodology/evaluation/metrics.md) (VTI, PI, EI), never the
returns: each reward has its own units, and the `salazar` reward pays for trading
more than for money.

**Open before the run:**
- The reward's and observation's definitions: the KPI window (E-10), missing values
  as 0 (E-07), true values instead of forecasts (E-05), raw KPIs in the reward
  (E-13), the grid terms' timing (E-16), and the KPIs marked `# OPEN` in
  `core/market/signals.py` ([issue register](../../original/issues/register.md)).
- Paradigms, budget and seeds, after the RL stage.

**Results.** To come.
