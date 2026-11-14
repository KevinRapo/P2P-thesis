# MARLEM: the configuration of the learning experiment

> Every setting of Salazar-Peña et al.'s learning experiment ([P2] §4, the 3 × 3
> matrix of paradigms and algorithms) on one page, next to what this thesis uses
> now, so the two can be compared at a glance. [P1]'s own case study (zero-intelligence
> agents, no learning) is left out.
>
> Where [P2] gives a value it is used; where [P2] is silent, [P1]'s; where both are
> silent, the original code as [P2]'s experiment ran it: the notebook
> [`case6_implicit_cooperation.ipynb`](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/notebooks/case6_implicit_cooperation.ipynb)
> and the defaults behind it (commit `15d6715`). The **Source** column says which.
> Where the paper and the code disagree, both are given. The definitions and the
> issues behind each value are on [the learning layer](learning.md),
> [the market](methodology.md) and [the two papers](issues/papers.md).
>
> **This thesis now** is the scenario
> [`thesis_rural1.json`](../../config/scenarios/thesis_rural1.json) with the standing
> settings of the [experiment diary](../experiments/diary.md#how-to-read-the-figures)
> (14 Nov 2026).

Sources: **[P2]** Table 6-8 and §4; **[P1]** §3; **nb** the notebook; **code** a
default in the original's `src/`.

## 1. Scenario

| Setting | Salazar | Source | This thesis now |
|---|---|---|---|
| Network | IEEE 34-bus feeder, 8 nodes used | [P2] T6, nb | SimBench `1-LV-rural1--2-sw` (LV, 160 kVA transformer) |
| Grid model | graph: shortest paths, capacity shared over edges by inverse length | [P1], code | AC power flow (pandapower), background loads from SimBench |
| Grid capacity $C$ | 1800 kW | [P2] T7, nb | the network's own ratings |
| Participants | 8 | [P2] T6 | 13, 5 of them with a battery |
| Who they are | [P2]: small industry, hospital, campus, mall, residential complex, apartments, solar farm, parking lot, 75-180 kW. nb: 2 commercial, 2 shopping, 2 industrial, 2 "flexible", 150-400 kW | [P2] T6, nb | SimBench households (rural LV loads and PV) |
| Generation, demand | a random column of `generation_60min.csv` / `demand_60min.csv` × capacity; generation × U(1.0, 1.3) ± 5 % noise, demand × U(0.6, 1.0) ± 10 %; 3-step moving average | nb, code `src/profile/der.py` | SimBench time series of 2016; PV × 1.5 |
| Days | one synthetic day, the same every episode (seed 42) | [P2] §4.3, nb | trained on 2016, tested on 4 held-out weeks (28 days) |
| Step, horizon | 1 h, 24 steps | [P2] T7 | 1 h, 24 steps |
| Forecast error | 30 % ([P2]); the code observes true values | [P2] T7, nb `max_error=0.3` | 0 (true values) |
| Seed | 42 for everything; every reset reseeds NumPy | [P2] §4.3, code | one per run (0-4), `PYTHONHASHSEED` fixed |
| Asynchronous orders | on | [P2] T7, nb | not modelled |

### Batteries

| Setting | Salazar | Source | This thesis now |
|---|---|---|---|
| Size | [P2]: 52.5-180 (printed as kW). nb: capacity × 0.5-1.0 | [P2] T6, nb | 37-147 kWh, 412 kWh in total |
| State of charge limits | 5-95 % | [P2], nb | 10-90 % |
| Efficiency | 95 % charge, 95 % discharge | [P2], nb | 95 %, 95 % |
| Power limit | none | code `battery.py` | half the capacity per hour (18-73 kW, 206 kW in total) |
| Starting SoC | random, U(min, max), at every reset | code `battery.py` | 50 % |

### Prices

| Setting | Salazar | Source | This thesis now |
|---|---|---|---|
| Price range | 20-600 \$/MWh (bounds of orders and tariffs) | [P2] T7, nb | 0-1 EUR/kWh |
| Quantity range | 0-180 kWh ([P2]); 0.1-180 kWh (nb) | [P2] T7, nb | 0.001-100 kWh |
| Utility price | a random column of `utility_60min.csv`, rescaled to 30 + 570 × (normalised value), × U(0.75, 1.25), clipped to 22-600; 3-step moving average | nb, code `src/profile/dso.py` | `de_2024`: German day-ahead price 2024 + a fixed household adder, hourly |
| Feed-in tariff | a random column of `fit_60min.csv`, rescaled to 20 + 348 × (normalised value), × U(0.7, 1.3), clipped to 20-540; 3-step moving average | nb, code | day-ahead price − 0.004 |
| Gap between the two | at least 5 % of the price range (29 \$/MWh) | code | follows from the two series |
| Prices change between episodes | no (`enable_reset_dso_profiles=False`) | [P2] §4.3, nb | yes: every day has its own prices |

## 2. Market

| Setting | Salazar | Source | This thesis now |
|---|---|---|---|
| Clearing price | [P2]: average, $(p_\text{buy} + p_\text{sell})/2$. nb: **proportional surplus** | [P2] §4.1, nb | average |
| Partner preference | on: agents name a partner | [P2] §4.1, nb | on: the partner is a categorical action |
| Reputation weights | reliability 0.3, fairness 0.2, grid 0.5 | code | 0.3, 0.2, 0.5 |
| Reputation decay | the time of day, $(t \bmod T)/T$ | code | 0.8, fixed |
| Reputation start | U(0, 1) at every reset | code | open (MP-5b) |
| Trade ledger | blockchain-style, difficulty 2 | nb | removed: it changes no result |

## 3. DSO fees ([P1] eq. 8)

Fee per trade = rate × quantity × price; [P2] restates none of it.

| Setting | Salazar | Source | This thesis now |
|---|---|---|---|
| $f_\text{cong}$ | 0.5 | code | 0.5 |
| $C_\text{threshold}$ | 0.8 | [P1] | 0.8 |
| $T_\text{threshold}$ (thermal) | 0.2 | [P1] | **0.8** (MP-4f) |
| $f_\text{threshold}$ (thermal cap) | 0.3 | code | 0.3 |
| $V_\text{threshold}$ | 0.05 | [P1] | 0.05 |
| Voltage drop | $f_\text{volt}$ 0.15 × graph distance | code | measured: the largest deviation from the slack voltage on the path (MP-4l) |
| $f_\text{imb}$ | 0.15 | code | **0**: the imbalance fee is off (MP-4m) |
| $f_\text{zone}$ (same-zone bonus) | 0.15 | code | 0.15, capped at the fees it cancels (MP-4n) |
| Transmission fee $F_\text{trans}$ | always 0 | code | 0; losses are charged per participant from the power flow (`bcdla`) |
| Loss factor $\kappa$ | 0.03 per unit of graph distance | code | from the power flow |
| Congestion level $C_t$ | in [0, 1] | [P1] | the highest loading on the trade's path, clipped at 1 (the transformer for DSO trades) |
| Untraded energy | neither settled nor charged | code | settled at the tariffs (MP-1e) and charged the fees of a DSO trade (MP-1f) |
| Peer charge | none | [P1] | 0 (MP-4h open) |

## 4. Reward

**The thesis does not train on this reward.** Every experiment in the diary uses the
net bill (`reward: "bill"`): each agent's own energy money with its fees, divided by
`reward_scale`, the cost of the largest step's energy bought from the DSO at its
dearest price. The original's reward is available as
`reward: "salazar"` with every constant below
([reward.py](../../core/env/reward.py#L63-L105)). The forms of the reward differ
between [P1], [P2] and the code: [The two papers §3](issues/papers.md#3-reward).

| Part | Constant | Salazar | Source |
|---|---|---|---|
| **Form** | final log compression, $\operatorname{sign}(x)\, 20 \ln(1 + \lvert x \rvert / 20)$ | scale 20 ([P2] has none) | [P1] eq. 3, code |
| | cooperation bonus on $R_\text{base}$ | code: $\ln(1 + f_\text{coop} f_\text{contrib}) / 5$; [P2]: $f_\text{coop} f_\text{contrib}$ | [P2] eq. 3, code |
| | penalty scale | $0.3 \max(\lvert \text{boosted } R_\text{base} \rvert, 1)$ | code |
| **$R_\text{base}$ weights** | grid balance | 10 | [P1] §3.2.4, code |
| | resource allocation | 1.5 | [P1], code |
| | trading | 5 | [P1], code |
| | market stability | 2 | [P1], code |
| | economic efficiency | 3 | [P1], code |
| **Inside the parts** | trading: local / DSO fill rate | 0.3 / 0.3 (the code's 0.7 overwritten, E-17) | [P1], code |
| | economic: price efficiency / profit against the DSO | 0.4 / 0.6 | code |
| | stability: volatility / imbalance improvement | 0.3 / 0.7 | code |
| | grid imbalance penalty | 10 | code |
| | price deviation penalty | 2 | code |
| | unused resource penalty | 1.5 | code |
| | volatility penalty | 2 | code |
| **$f_\text{coop}$ KPI weights** (sum 56) | social welfare | 7 | code |
| | liquidity | 1.5 | code |
| | bid-ask spread | 1.5 | code |
| | price volatility | 3 | code |
| | supply-demand imbalance | 10 | code |
| | grid congestion | 9 | code |
| | coordination score | 5 | code |
| | coordination convergence | 8 | code |
| | DER self-consumption | 5 | code |
| | flexibility utilisation | 6 | code |
| **$f_\text{contrib}$ weights** | grid / price / local trading | 0.5 / 0.2 / 0.3, neutral point 0.5 | [P1] eq. 6, code |
| **Penalties** | DSO reliance $p_\text{dso}$ | 15, × DSO share × $\lvert B \rvert / C$ | [P1], code |
| | unmet demand | $p_\text{dso}$ × (unmet share)², last step only | code |
| | no trades $p_\text{no\_trades}$ | 5: an agent without trades gets a fixed $-20 \ln(1.25) \approx -4.46$ | [P1], code |
| **Grid capacity** | $C$ in the grid terms | 1800 kW | nb; here a run must state it (RP-1g) |

## 5. Observation and action

| Setting | Salazar | Source | This thesis now |
|---|---|---|---|
| Observation | 42 signals: 16 market, 16 agent, 10 KPIs | [P1] T2, [P2] T5 | the same 42 (`observation: "paper"`) |
| Scaling | none: raw values | code | scaled by the training days' energy and reward scales |
| KPI window | since the episode started (E-10) | code | as the original; `# OPEN` in `signals.py` |
| Action | price, quantity, side $\alpha$, partner $\beta$, all from one continuous Gaussian; buy if $\alpha > 0.5$, partner `int(β)` | [P1] eq. 2, code | mixed: side and partner categorical, quantity share and price continuous |
| "No order" | none | code | a quantity share below the no-order threshold |

## 6. Training

| Setting | Salazar | Source | This thesis now |
|---|---|---|---|
| Algorithms | PPO, APPO, SAC | [P2] | PPO |
| Paradigms | CTCE, CTDE (central critic on $s, \mathbf{a}$), DTDE | [P2] §3.4 | CTCE, CTDE (MAPPO: per-agent critics on the global state), DTDE |
| CTCE / CTDE objective | the sum of all agents' rewards | [P2] eq. 17, code | CTCE: the sum; CTDE: each agent's own reward (RP-3e) |
| Networks | DTDE: RLlib's 2 × 256 tanh; CTCE, CTDE: custom 2 × 128 ReLU | code | RLlib's 2 × 256 tanh in every paradigm |
| Learning rate | $10^{-5}$ | [P2] T8 | $3 \times 10^{-4}$ |
| Discount $\gamma$ | 0.99 | [P2] T8 | 0.99 |
| GAE $\lambda$ | 0.95 | code | 0.95 |
| Clip $\epsilon$ | 0.2 | [P2] T8 | 0.2 |
| Entropy coefficient | 0.01 | [P2] T8 | 0.01; in CTCE divided by the 13 agents (RP-3a) |
| Gradient clip | 0.5 | [P2] T8 | 0.5 |
| Batch per iteration | 4000 env steps (RLlib default) | code | 4000 |
| Minibatch | 128 | [P2] T8 | 500 |
| Epochs | 30 | code | 10 |
| KL penalty | coefficient 0 | code | 0 |
| Value loss cap | 10 (RLlib default) | code | lifted |
| Population-based training | 10 trials per configuration ([P2]); 100 (nb); mutates lr in loguniform(1e-4, 1e-2), entropy in loguniform(0.01, 10), $\lambda$ in loguniform(0.8, 0.99) | [P2] §4.2, code | off |
| Budget | "10 000 episodes" ([P2]); `iters=10000` training iterations, × 4000 steps (nb) | [P2] §4.2, nb | 480k env steps (20 000 days); 960k and 2.88M in the long runs |
| Evaluation | every iteration, on the training day and seed, 3 episodes | [P2], nb | 10-12 points during training, on training days with seeds training did not use; the held-out test weeks at the end |
| Results reported | mean episode reward ([P2] T9) | [P2] | money: VTI, after fees, grid hours |

[P2]'s results and the hyperparameters PBT ended with (Table 9-10) are in
[the learning layer §7](learning.md#7-the-3--3-experiment-p2-4-5).
