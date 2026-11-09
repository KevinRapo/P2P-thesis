# Thesis experiments

> The runs the thesis reports. **Status: set up, not run.** Each experiment is
> fixed in a file, and the points still open are listed with it. A run starts
> once its open points are decided, and its results are added here.

Two experiments, on one shared setup:

1. **[Grid methods](#1-grid-methods)**: what changes when the fees see the grid
   through the AC power flow instead of [P1]'s graph model. The main result.
2. **[Reward and observation](#2-reward-and-observation)**: the original's
   reward and observation against ours.

## The shared setup

Both experiments start from one scenario,
[`thesis_rural3_p13.json`](../../config/scenarios/thesis_rural3_p13.json). What
they share:

| Setting | Value | Why |
|---|---|---|
| Network | `1-LV-rural3--2-sw`: 13 participants on 13 of its 43 prosumer buses; the other 30 buses follow their SimBench profiles as background | Large enough to learn reliably, and the background is what the graph model cannot see ([Market runs](market-s3.md)) |
| Prices | `de_2024`: German day-ahead prices of 2024 as a dynamic tariff ([Prices](../using/data/prices.md)) | Real prices that change every hour |
| Peer charge | 0: [P1]'s market | MP-4h is open ([Tariffs](../methodology/market/tariffs.md#the-decision-mp-4h)) |
| Grid | AC power flow; voltage drop measured along the trade's path | The power flow is this thesis's grid ([Grid methods](../methodology/market/grid-methods.md)) |
| Days | Training on June 2016; held-out test on 1-14 July 2016 | Summer: PV, so surplus to trade |
| Learning | PPO with [RLlib defaults as changed here](../methodology/learning/index.md#2-everything-we-change-in-rllibs-ppo), no tuning; 240k environment steps; 5 seeds (0-4) | The budget and seeds are provisional (L-14, L-17) |
| Evaluation | 10 points during training, 5 episodes each; every test day once at the end | Held-out bill per participant (`heldout_agents.csv`) |

Each run has 8 environment runners, on TalTech `blackwell1` (10 CPUs, 12 GB, 4 h).

## 1. Grid methods

[`thesis_grid_methods.json`](../../config/experiments/thesis_grid_methods.json):
4 arms × 5 seeds = 20 runs, CTDE, the bill as reward, the paper's observation.

**Question.** When agents learn under each grid method's fees, which one leads to
less physical stress on the real network, and which one's incentives follow that
stress?

| Arm | Line loading in the fees | Voltage drop in the fees | Fees paid |
|---|---|---|---|
| `no_fees` | power flow | measured | no: recorded only. The reference, showing whether any fee changes behaviour |
| `powerflow` | the path's measured loading | measured $\lvert V_a - V_b \rvert$ | yes |
| `graph` | trade flows ÷ [P1]'s capacity split by inverse line length (eq. 19) | $f_\text{volt}\, d_{ij}$ (eq. 8f) | yes |
| `graph_ratings` | trade flows ÷ each line's rating | $f_\text{volt}\, d_{ij}$ | yes |

**What is compared.** The power flow runs in every arm, so the physical outcome is
always measured the same way:
- **the grid:** hours with an overloaded line or transformer, highest and 95th
  percentile loading, voltage violations, line losses, energy through the
  transformer;
- **the market:** bill per participant, energy traded between peers, trade
  distances, fees by component;
- **how well each fee follows the grid,** without learning: the fee's line loading
  against the measured one, trade by trade, with the `net_position` rule.

**Open before the run:**
- The fee points of the market plan: M-28, M-31, M-32, M-33, M-34, M-41.
- **The network is lightly loaded.** Over June and July, line loading peaks at
  38 % (95th percentile 18 %) and the transformer at 40 %. The congestion fee
  (threshold 0.8) is never charged, and the thermal fee only a little. Two
  additions are proposed, both not built yet:
  - the transformer in the fees of trades that cross it;
  - a stress setting that scales the line ratings, run at 1.0 and, for example,
    0.5 as a second level.
- Paradigm, budget and seeds, after the RL stage.

**Results.** To come.

## 2. Reward and observation

[`thesis_reward_obs.json`](../../config/experiments/thesis_reward_obs.json):
4 arms × 2 paradigms (CTDE, DTDE) × 5 seeds = 40 runs, on the power flow.

**Question.** Do agents trained with our reward and observation do better for the
participants than with the original's?

| Arm | Reward | Observation |
|---|---|---|
| `salazar_paper` | the original code's ([Reward](../methodology/environment/reward.md)) | the paper's 42 signals ([Observation](../methodology/environment/observation.md)) |
| `salazar_pruned` | the original code's | the pruned 22 |
| `bill_paper` | the participant's own bill | the paper's 42 |
| `bill_pruned` | the participant's own bill | the pruned 22 |

The `salazar` reward needs a grid capacity: 400 kWh per step, the transformer's
0.4 MVA over one hour (RP-1g).

**What is compared.** The held-out bill per participant and the
[indices](../methodology/evaluation/metrics.md) (VTI, PI, EI), never the
returns: each reward has its own units, and the `salazar` reward pays for trading
more than for money.

**Open before the run:**
- The reward's and observation's definitions: the KPI window (E-10), missing values
  as 0 (E-07), true values instead of forecasts (E-05), raw KPIs in the reward
  (E-13), the grid terms' timing (E-16), and the KPIs marked `# OPEN` in
  `core/market/signals.py` ([issue register](../original/issues/register.md)).
- Paradigms, budget and seeds, after the RL stage.

**Results.** To come.
