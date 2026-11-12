# Experiment diary

> What was run, when and why, and what it showed: one section per day, newest last.
> Each experiment is a file in [config/experiments/](../../config/experiments/); its
> runs are in `runs/@taltech/<experiment>/`. The timeline at the end lists every
> experiment with its start date and time.

## How to read the figures

Unless an entry says otherwise:

- **Scenario**: `thesis_rural1` (the 13 participants of `1-LV-rural1--2-sw`) with the AC
  power flow, PV scaled x1.5, all DSO fees on. Trained on 2016, evaluated on four held-out
  weeks: 11-17 Jan, 11-17 Apr, 11-17 Jul, 10-16 Oct (28 test days).
- **Training**: PPO, CTDE, paper observation (42 signals), 480k env steps; lr 3e-4,
  gamma 0.99, lambda 0.95, clip 0.2, entropy 0.01, grad clip 0.5, batch 4000, minibatch
  500, 10 epochs, 8 env runners. On blackwell1 (10 CPUs, 12 GB per run).
- **VTI**: (energy money - non_p2p) / (ceiling - non_p2p), summed over the 28 test days.
  0 is every participant alone with its own battery (`non_p2p`), 1 is the money-optimal
  community (`ceiling`, a copper-plate LP: not grid-feasible, up to 288 % transformer
  loading at PV x1.5). Energy money adds the fees back; "after fees" is what the team
  pays. Both references end every test week with batteries at least as full as they began
  (`keep_end` on; see 12 Nov).
- **Hours over the loading limit**: test-day hours above the DSO's thermal threshold (0.8).

## 2026-11-11 (Wed)

**Market fixes before the experiments** (commits 5aab799, 23:37, and 644bbee, 00:04 on
12 Nov). Agreed in the session before; every run below uses them:

- the loss allocation; fees on untraded energy; the fees read rural1's own limits
  (voltage and transformer); the slack voltage as the voltage reference;
  `thermal_threshold` 0.8;
- imbalance charge off (`# OPEN MP-4m`);
- `ceiling.py` and `indicators.py` moved to `core/market`; VTI before and after fees.

## 2026-11-12 (Thu)

### Night audit, 00:11-16:12: 111 runs on blackwell1

Question: do the market changes behave on real training runs, and how hard should the
grid be stressed to make a good test bed? Can agents learn to relieve a baseline
overload? Do the MAPPO paper's PPO findings hold here?

**Short answers**

- **Test bed: PV x1.5.** At PV x1 the rule-based baseline overloads the transformer (16 h
  over the loading limit on the test weeks) and trained agents remove it completely. At
  x1.5 the overload is clear (62 h) and the policies differ in how much they remove
  (27-45 h left). At x2 the batteries cannot absorb it (84-97 h left).
- **Agents relieve the overload, with and without fees.** Charging the batteries from the
  neighbours' midday PV is both cheap and what the transformer needs. Every trained
  policy loads the transformer less than the ceiling.
- **Fees at their current strength do not change what is learned.** At lr 3e-4 fees
  helped on all five paired seeds; at lr 1e-3 the gap is gone (0.65 vs 0.66): a
  learning-speed effect. Fees three times as strong move the grid hours a little (39 vs
  42.5 h at lr 1e-3, one seed).
- **PPO is under-trained at the old settings.** Learning rate, epochs and minibatches all
  point the same way: more optimisation per sample is better, up to lr 2e-3. Best:
  **lr 1e-3 with 960k steps** (CTDE 0.73, DTDE 0.74).
- **The observation can be reduced at a small cost**: the 22-signal `pruned` set is 0.02-0.03
  below the paper's 42 at lr 1e-3; the 9-signal `minimal` loses about 0.08 (at 3e-4).
- **CTCE relieves the transformer most** (27 h vs about 40) at a similar VTI.

**Stress levels: the rule-based baseline over all of 2016** (bidding rule, 8760 h)

| Load | PV | Hours with a violation | Transformer overload h (max) | Overvoltage h | Highest line loading |
|---:|---:|---:|---:|---:|---:|
| x1 | x1 | 379 | 251 (136 %) | 374 | 40 % |
| x1 | x1.5 | 967 | 804 (209 %) | 957 | 62 % |
| x1 | x2 | 1463 | 1274 (282 %) | 1442 | 84 % |
| x1.5 | x1 | 290 | | | |
| x2 | x1 | 194 | | | |

The stress is PV-driven: noon reverse flow through the 160 kVA transformer, and
overvoltage. More load reduces it. No line overloads and no bus goes under-voltage. The
batteries total about 206 kW: enough for x1 and x1.5, not x2. SimBench PV is zero on
11-12 Jan 2016, so the winter week carries little of the stress.

**Do the agents relieve the grid?**

| PV | Policy | VTI | Hours over loading limit | Highest transformer loading |
|---|---|---:|---:|---:|
| x1 | net_position (rule) | 0.30 | 16 | 126 % |
| x1 | ceiling | 1.00 | 12 | 213 % |
| x1 | trained, lr 3e-4 (2 seeds) | 0.59 | 0 | 96 % |
| x1 | trained, lr 1e-3 (2) | 0.64 | 0.5 | 100 % |
| x1.5 | net_position | 0.30 | 62 | 195 % |
| x1.5 | ceiling | 1.00 | 51 | 288 % |
| x1.5 | trained, lr 3e-4 (5) | 0.58 ± 0.10 | 43 | 165 % |
| x1.5 | trained, lr 1e-3 (4) | 0.65 ± 0.02 | 42.5 | 161 % |
| x1.5 | trained, lr 1e-3, 960k (2) | 0.73 | 35 | 160 % |
| x1.5 | CTCE, lr 3e-4 (3) | 0.64 | 27 | 184 % |
| x2 | net_position | 0.30 | 105 | 263 % |
| x2 | ceiling | 1.00 | 84 | 352 % |
| x2 | trained, lr 3e-4 (2) | 0.52 | 90.5 | 233 % |
| x2 | trained, lr 1e-3 (2) | 0.66 | 84 | 223 % |

**Fees on and off** (same seeds)

| | Seeds | Fees | No fees |
|---|---|---|---|
| lr 3e-4 | 0 1 2 3 4 | 0.44 0.62 0.52 0.64 0.67 (0.58) | 0.43 0.55 0.49 0.55 0.61 (0.53) |
| lr 1e-3 | 0 1 2 | 0.64 0.63 0.66 (0.64) | 0.67 0.68 0.63 (0.66) |

The hours over the loading limit are the same with and without fees (43 vs 44 at 3e-4;
42.5 vs 39 at 1e-3): the price signal (cheap midday PV) already steers the agents.

**One fee part at a time** (zone bonus off)

| Fee part | lr 3e-4, 2 seeds: VTI / after fees / h | lr 1e-3, seed 0: VTI / after fees / h |
|---|---|---|
| all fees (reference) | 0.58 / 0.44 / 43 | 0.64 / - / 42.5 (4 seeds: 0.65) |
| all fees x3 (`strong`) | 0.53 / 0.26 / 44.5 | **0.70 / 0.47 / 39** |
| thermal + congestion only | 0.49 / 0.40 / 45.5 | 0.66 / 0.59 / 43 |
| losses only | 0.55 / 0.50 / 43.5 | 0.64 / 0.59 / 43 |
| voltage only | 0.56 / 0.55 / 44.5 | 0.60 / 0.59 / 45 |

At lr 3e-4 no part moves the grid hours. At lr 1e-3 `strong` gives the best energy money
and the fewest overload hours, but the team pays for it (0.47 after fees); one seed, with
a seed spread of about 0.02 at lr 1e-3.

**PPO settings and the MAPPO question.** Updates per sample = epochs x (batch / minibatch).

| Setting | Updates per sample | VTI (seeds) | Mean |
|---|---:|---|---:|
| lr 1e-4 | 80 | 0.28 0.21 | 0.25 |
| full batch, 5 epochs | 5 | 0.23 0.25 | 0.24 |
| batch 16k, minibatch 2000 | 80 | 0.31 | 0.31 |
| 5 epochs | 40 | 0.39 0.45 | 0.42 |
| full batch, 10 epochs | 10 | 0.52 0.48 | 0.50 |
| **reference: 4000 / 500 / 10, lr 3e-4** | 80 | 0.44 0.62 0.52 0.64 0.67 | 0.58 |
| 15 epochs | 120 | 0.58 0.61 0.63 0.66 | 0.62 |
| lr 2e-3, 5 epochs | 40 | 0.62 0.63 | 0.62 |
| lr 1e-3 | 80 | 0.64 0.63 0.66 0.68 | 0.65 |
| lr 1e-3, 15 epochs | 120 | 0.66 0.65 | 0.65 |
| **lr 2e-3** | 80 | 0.66 0.64 0.66 0.71 | **0.67** |
| lr 3e-3 | 80 | 0.51 0.60 | 0.55 |
| lr 5e-3 | 80 | 0.07 0.07 | 0.07 (collapsed) |
| entropy 0 | 80 | 0.49 0.71 | 0.60 |

At 480k with lr 3e-4 the policy is under-trained: anything that lowers the optimisation
per sample lowers the VTI. The MAPPO paper's advice (few epochs, one minibatch) keeps
updates small for long runs; at lr 3e-4 and 480k it hurts, while at lr 2e-3, 5 epochs
work (0.62). At 3e-3 learning degrades; at 5e-3 the policy collapses to doing almost
nothing.

**Paradigms** (480k)

| Paradigm | lr 3e-4 | lr 1e-3 | lr 2e-3 | Hours over loading limit (3e-4 / 1e-3) |
|---|---|---|---|---:|
| CTCE | 0.64 0.63 0.64 (0.64) | 0.58 0.64 (0.61) | | 27 / 30.5 |
| CTDE | 0.58 (5 seeds) | 0.65 (4) | 0.67 (4) | 43 / 42.5 |
| DTDE | 0.63 0.56 0.62 (0.60) | 0.65 0.67 (0.66) | 0.67 0.61 (0.64) | 40 / 39 |

CTCE is the most stable and relieves the transformer most, but does not gain from a
higher learning rate. CTDE and DTDE gain from it and reach CTCE's VTI.

**Observations** (lr 3e-4 unless marked)

| Set | Signals | VTI (seeds) | Mean | Hours over loading limit |
|---|---:|---|---:|---:|
| paper | 42 | 5 seeds | 0.58 ± 0.10 | 43 |
| pruned | 22 | 0.64 0.56 0.61 0.58 | 0.60 ± 0.04 | 43.5 |
| pruned_grid | 24 | 0.61 0.58 0.64 0.59 | 0.60 ± 0.03 | 37.75 |
| minimal_grid | 15 | 0.54 0.53 | 0.53 | 41.5 |
| minimal | 9 | 0.54 0.46 | 0.50 | 45.5 |
| minimal_market | 13 | 0.42 0.51 | 0.46 | 47 |
| paper, lr 1e-3 | 42 | 0.64 0.63 0.66 0.68 | 0.65 ± 0.02 | 42.5 |
| pruned, lr 1e-3 | 22 | 0.63 | 0.63 | 42 |
| pruned_grid, lr 1e-3 | 24 | 0.62 0.62 | 0.62 | 41 |

At lr 1e-3 the reduced sets are 0.02-0.03 below the paper's; their advantage at 3e-4 was
learning speed. Seeing the transformer helps the small sets (minimal_grid vs
minimal_market: +0.07) and gives `pruned_grid` the fewest overload hours of the CTDE sets.

**Budget**

| Setting | 480k | 960k | Hours over loading limit (480k / 960k) |
|---|---|---|---:|
| CTDE lr 3e-4 | 0.58 (5 seeds) | 0.53 0.70 0.61 (0.61) | 43 / 42 |
| **CTDE lr 1e-3** | 0.65 (4) | 0.73 0.72 (**0.73**) | 42.5 / **35** |
| CTDE lr 2e-3 | 0.67 (4) | 0.66 0.65 (0.66) | 41 / 38 |
| **DTDE lr 1e-3** | 0.66 (2) | 0.74 0.74 (**0.74**) | 39 / **34** |

With lr 1e-3, doubling the budget adds 0.08 VTI and removes about 7 overload hours. lr
2e-3 learns faster but stops there.

**`keep_end` in the references.** Both references are LPs with batteries: the ceiling
(the community) and `non_p2p` (each participant alone with its own battery). With
`keep_end` they must end each test week with batteries at least as full as they began.
The played policies have no such rule: net_position and every trained policy end the
four weeks with 610-660 kWh less stored. Turned off, both references may drain too; the
policies' own results do not change. At PV x1.5 the ceiling gains 143 (-35 to 108) and
non_p2p 226 (-3383 to -3157). The floor rises more than the ceiling, so every VTI falls
by about 0.05 (VTI off ≈ 1.025 x VTI on - 0.07):

| | keep_end on | keep_end off |
|---|---:|---:|
| net_position | 0.30 | 0.24 |
| CTDE lr 3e-4 (5 seeds) | 0.58 | 0.52 |
| CTDE lr 1e-3 (4) | 0.65 | 0.60 |
| CTDE lr 2e-3 (4) | 0.67 | 0.62 |
| CTDE lr 1e-3, 960k (2) | 0.73 | 0.68 |
| CTCE lr 3e-4 (3) | 0.64 | 0.58 |
| DTDE lr 3e-4 (3) | 0.60 | 0.55 |

The order of the settings stays the same. With `keep_end` off every policy, reference or
learned, plays by the same rule; the alternative is an end-of-week value for stored
energy for all of them (MP-1c).

**Code changes made during the night, not discussed before** (keep or drop each)

1. Observation sets `minimal` and `minimal_market` (commit 5b70159).
2. Grid observation signals (commit bc3e469): `transformer_loading` (last step's highest
   transformer loading, as a ratio) and `voltage_deviation` (largest |V - V_slack|,
   scaled by 0.05) in a new `GRID_SIGNALS` group outside the paper's 42, used only by
   `minimal_grid` and `pruned_grid`. The paper set is unchanged.
3. Proposed, not in code: `keep_end` off for the references.

Together 4 files, +70 / -6 lines; no market, grid, reward, action or algorithm logic changed.

**Suggested next:** lr 1e-3 as the PPO default with at least 960k steps; PV x1.5 as the
test bed, PV x1 as the fully relievable case; more seeds for `strong` fees; decide
`keep_end` and the observation set.

### Evening: long runs, 2.88M steps (started 20:14)

Question: does training longer change the ranking of the PPO settings, in particular
do the MAPPO paper's settings catch up when given far more samples?

**What the 480k learning curves said beforehand.** Slope of the training return over the
last quarter of training, and how far the policy moves per update (mean KL, last
iterations):

| Setting | Slope, last quarter | KL per update | Reading |
|---|---|---|---|
| full batch, 5 epochs (worst) | +0.075, the steepest | 0.005, the smallest | still climbing, tiny steps |
| 16k batch, minibatch 2000 | about 0, evaluation still rising | 0.008 | slow |
| reference (lr 3e-4) | +0.03 to +0.09 | 0.012 | still learning (960k: 0.58 to 0.61) |
| lr 1e-3 | about +0.02 at 960k | 0.025 | nearly flat, yet 0.65 to 0.73 at 960k |
| lr 2e-3 | slightly negative at 960k | 0.07 | levelled off |
| lr 5e-3 | flat | 0.33-0.46 | collapsed |

The training return comes from random training days and is noisy, so this only
suggests where room is left.

**Experiments** (2 seeds each, 12 evaluation points per run):

- [`long_best`](../../config/experiments/long_best.json): reference (lr 3e-4), lr 1e-3, lr 2e-3.
- [`long_worst`](../../config/experiments/long_worst.json): full batch with 5 epochs, batch
  16k / minibatch 2000, 5 epochs, and `mappo`: the MAPPO paper's own combination (batch
  16000, one minibatch, 5 epochs, lr 5e-4), not run before.

**Where:** blackwell1 is only in the `short` partition (4 h limit), too short for 2.88M
steps, so these run on the `common` partition (green19-21, Skylake, 48 h limit). Green
is about 2.5 times slower than blackwell1 (about 50 env steps per second per run).
Expected to end between about 07:00 and 13:30 on 13 Nov.

**Results:** pending.

## Timeline

| Date | Start | Experiment | Runs | Purpose |
|---|---|---|---:|---|
| 12 Nov | 00:11 | stress_fees | 12 | PV x1 / 1.5 / 2, fees on / off, seeds 0-1 |
| 12 Nov | 00:11 | fee_parts | 4 | one fee part at a time |
| 12 Nov | 00:11 | ppo_batches | 5 | batch / epochs; 2 failed to start (thread limit) |
| 12 Nov | 01:26 | ppo_batches2 | 2 | the 2 failed arms |
| 12 Nov | 01:37 | observations | 6 | pruned, minimal, minimal_market |
| 12 Nov | 03:00 | paradigms_pv15, long_pv15 | 3 | CTCE, DTDE; CTDE 960k |
| 12 Nov | 04:02 | seeds_pv15, observations_grid | 7 | reference seeds 2-4; grid signals |
| 12 Nov | 05:11 | seeds_arms, ppo_batches_s1 | 8 | more seeds |
| 12 Nov | 06:20 | fee_parts_s1, paradigms_pv15_s1 | 6 | more seeds |
| 12 Nov | 06:41 | long_pv15_s12, paradigms_pv15_s2 | 4 | more seeds |
| 12 Nov | 07:33 | ppo_lr_entropy | 6 | lr 1e-3, 1e-4, entropy 0 |
| 12 Nov | 08:45 | combo, nofees_seeds, combo_ctce, pruned_grid_s23 | 10 | combined arms, more seeds |
| 12 Nov | 10:03 | lr_paradigms, ppo_lr3, ppo_lr2 | 10 | learning rate follow-up |
| 12 Nov | 10:43 | lr1e3_long, lr1e3_stress, lr1e3_nofees, lr1e3_pruned_grid | 10 | lr 1e-3 everywhere |
| 12 Nov | 12:43 | lr2e3_s23, lr2e3_dtde, lr_edge | 10 | lr 2e-3 seeds, the lr edge |
| 12 Nov | 13:48 | long_lr2e3, long_dtde_lr1e3 | 4 | 960k |
| 12 Nov | 14:40 | fee_parts_lr1e3, obs_lr1e3 | 6 | fee parts and observations at lr 1e-3 |
| 12 Nov | 20:14 | long_best, long_worst | 14 | 2.88M steps, on `common` |

Between 03:51 and 04:01 nothing started: the runner's `start` takes the experiment's file
path, and the scheduler passed its name.
