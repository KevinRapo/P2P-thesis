# Market runs: three seeds, CTCE's entropy, more agents

> **Status: results of 26-27 October 2026**, TalTech (blackwell1, CTDE with 43
> agents on green20). One budget per experiment, the PPO defaults of RP-6b, no
> tuning. The CTDE runs with 43 agents were still training when this was written.

Three questions after `market_s2` (one seed, 240k steps):

1. Do CTDE and DTDE learn the market reliably, over seeds and a longer budget?
2. Does CTCE learn once its entropy bonus is no longer 13 times one agent's
   (L-02, [probes](../rl/probes.md#why-ctce-misses-probes-4-6-26-october-2026))?
3. What happens with more agents?

Results are in `runs/@taltech/<experiment>/`; every number below is the held-out
evaluation (each test day 1-14 July 2016 once) unless it says otherwise.

## The experiments

| Experiment | Network, participants | Paradigms | Seeds | Budget |
|---|---|---|---|---|
| `market_s3` | 1-LV-rural1--2-sw, all 13 (8 PV, 5 storage) | CTCE, CTDE, DTDE | 0-2 | 480k |
| `market_s3_ctce` | as `market_s3` | CTCE, entropy 0.01 / 13 | 0-2 | 480k |
| `scale_p13`, `_p26`, `_p43` (+ `_ctce`, `scale_p43_ctde`) | 1-LV-rural3--2-sw, 13, 26 or all 43 of its prosumer buses (the PV : storage share kept; the rest of the network as background) | CTCE (entropy 0.01 / N), CTDE, DTDE | 0-1 | 192k |

Each run has 8 environment runners. The scenarios `lv_rural3_p13/26/43` are in
`config/scenarios/`.

## 1. Three seeds on rural1 (`market_s3`)

| | Return | P2P (kWh) | Grid import (kWh) | Violations | Deferred demand (kWh) |
|---|---|---|---|---|---|
| CTCE, entropy 0.01 | −1.45 ± 1.01 | 58 | 217 | 3.6 | 137 |
| CTCE, entropy 0.01 / 13 | 1.07 ± 0.24 | 233 | 102 | 1.2 | 78 |
| CTDE | 1.63 ± 0.12 | 214 | 72 | 2.1 | 57 |
| DTDE | **1.76 ± 0.09** | 251 | 59 | 1.4 | 33 |
| zero (no orders) | −2.30 | 0 | 181 | 3.7 | 188 |
| net_position (heuristic) | 0.53 | 13 | 181 | 3.7 | 0 |

Mean ± standard deviation over 3 seeds, per held-out day.

- **CTDE and DTDE learn reliably**: every seed beats both baselines, with a small
  spread. Their training curves flatten after about 250k steps; `market_s2` at
  240k gave the same held-out returns (1.69, 1.76), so 480k bought little.
- **CTDE is not better than DTDE.** Its critic sees the global state, but each
  agent's reward is its own, so the extra information helps little.
- The trained policies are a step on the physical side: less grid import and
  fewer violations than doing nothing.
- Training-day evaluations are about 0.8 higher than held-out (2.4-2.7 against
  1.6-1.8); the net_position heuristic drops by 0.56 between the same days, so part
  of the gap is the days.

## 2. CTCE: the entropy bonus

At 0.01 CTCE's log σ rises to about +4.3 in all three seeds: the policy becomes
random. Divided by 13 (each agent's continuous parts get what a DTDE agent's
get, measured against the team's weaker signal), CTCE learns in every seed, but
stays below CTDE and DTDE. Its clip fraction is 0.85 against 0.37, the KL per
update 0.3 against 0.04: one joint ratio over 52 action parts.

Per participant, the difference is in the batteries (held-out, 3 seeds):

| | Battery owners: return | profit | PV owners: return | profit |
|---|---|---|---|---|
| DTDE | 0.04 | 1.32 | 0.20 | 5.79 |
| CTCE, 0.01 / 13 | −0.18 | −3.00 | 0.25 | 8.01 |

Under one summed reward, the price between two members is a transfer that leaves
the team's total unchanged, so CTCE has no reason to price fairly: money moves
from battery owners to PV owners. Its battery owners also leave more demand
unserved (6.3 kWh against 1.6), the main reason its team return is lower.

## 3. More agents (rural3, 192k steps)

The team return grows with the number of agents, so the comparison is per agent:
the held-out gain over doing nothing, (trained − zero) / N, mean of 2 seeds.

| N | CTCE | CTDE | DTDE | DTDE − net_position, per agent |
|---|---|---|---|---|
| 13 | 0.170 | 0.213 | 0.200 | +0.008 |
| 26 | 0.124 | 0.174 | 0.177 | +0.017 |
| 43 | 0.072 | *running* | 0.176 | +0.026 |

| N | CTCE: clip fraction, KL | DTDE: clip fraction, KL | Hours per run (blackwell1): CTCE / CTDE / DTDE |
|---|---|---|---|
| 13 | 0.87, 0.33 | 0.35, 0.03 | 0.4 / 1.0 / 0.8 |
| 26 | 0.88, 0.56 | 0.40, 0.03 | 0.6 / 2.4 / 1.5 |
| 43 | 0.91, 0.92 | 0.45, 0.04 | 1.0 / about 5 (11 on green) / 2.4 |

- **DTDE scales**: its gain per agent is almost flat from 26 to 43 agents, and
  it beats the net_position heuristic by more as N grows. Each agent learns from
  its own reward and sees the others only as part of its environment, so more
  agents add non-stationarity but do not dilute its signal.
- **CTCE degrades with N**: the gain per agent falls from 0.170 to 0.124 (26) and
  0.072 (43). From 13 to 26 that is the √N dilution of one agent's signal in the
  team advantage (0.73 against 1/√2 = 0.71); at 43 it falls faster (0.42 against
  0.55), as the joint ratio breaks down: KL 0.92 and 91 % of the samples clipped.
  Its log σ stays near 0 (σ ≈ 1): the per-agent signal no longer shrinks it.
- **CTDE costs the most to train**: N critics, each reading the global state that
  grows with N; about 10 environment steps per second at 43 agents against 56 at
  13.
- **Rural3 is an easy grid**: no violations at all, even without trading, and
  the net_position heuristic is strong (the learned policies beat it by 0.01-0.03
  per agent). Rural1 is the network where the grid binds; the scaling results say
  how learning scales, not how congestion is handled.
- DTDE was still improving at 192k for 26 and 43 agents (its training evaluation
  rose by 0.24-0.28 over the last three points).

## What to expect with more agents

- **DTDE and CTDE**: the learning holds; the cost is compute. DTDE's time grows
  about linearly with N, CTDE's faster (its critics' input grows with N too). At
  43 agents CTDE no longer fits blackwell1's 4 h with 192k steps. Budgets should
  grow somewhat with N (still rising at 192k for 26 and 43).
- **CTCE**: worse with every agent added, in its learning (one advantage, one
  joint ratio) and in what it optimises (the team's sum, blind to prices between
  members). It is not an upper bound in this setup (L-02); with many agents it is
  a lower one. Its entropy coefficient has to shrink with N to learn at all.
- **The cluster**: about 330 threads per run with 8 runners, and 4096 threads per
  user and node ([resources](../hpc/resources.md)): about 10 runs per node at once.
  More start, but hang or fail at start (seen here).
