# Market layer: what was wrong and what changed

> Every problem found in the **market layer** of MARLEM: in the original code, in
> the paper [P1], or in the method itself. For each one, what was wrong, where it
> came from, and what `marlem-clean` does about it. The reinforcement-learning layer
> (actions, observations, reward, KPIs, training) is validated separately on the RL
> branch and is left out here.

## Scope and sources

**Market layer** means everything that turns orders into trades, money and
energy:

- order validation and the three clearing stages;
- pricing mechanisms;
- the DSO (stage 3, balance, fees);
- transmission losses;
- settlement, the battery and each participant's balance and profit;
- reputation and the trade ledger;
- the grid model as the market uses it.

**Sources.**

- **IDs `I-xx`** are from the validation issue register
  (`docs_thesis/thesis/validation/issues.md` on the refactor branch). It was written
  against the original code, frozen as git tag `marlem-annotated`. Code links to the
  original point there.
- **IDs `N-xx`** are new findings made while rebuilding the market in
  `marlem-clean`. They are not in the register.
- **[P1]** is the MARLEM paper (Salazar-Peña et al., Applied Energy 412, 2026);
  its method is summarised in [methodology.md](../marlem/methodology.md).

**Origin** (as in the register):

| Origin | Meaning |
|---|---|
| Paper | The paper itself is wrong, contradictory or silent where the method needs an answer |
| Fidelity | The original code does not do what the paper says |
| Code | A programming defect that the paper has nothing to say about |

**Status in `marlem-clean`:**

| Status | Meaning |
|---|---|
| **Fixed** | Rebuilt to match the paper; the wrong behaviour is gone |
| **Replaced** | The part was replaced by the SimBench network and its AC power flow, so the problem no longer exists |
| **Decided** | The paper is silent or contradictory; a rule was chosen and recorded (see [structure.md, Choices](../structure.md#choices-in-the-rebuilt-market-step)) |
| **Open** | Known, not resolved yet |
| **Flagged** | Kept as in the original on purpose, but worth questioning |

## Summary

| Part of the market | Issues | Fixed | Replaced | Decided | Open | Flagged |
|---|---|---|---|---|---|---|
| [1. The market step](#1-the-market-step) | 4 | 3 | 1 | 0 | 0 | 0 |
| [2. Orders and feasibility](#2-orders-and-feasibility) | 4 | 4 | 0 | 0 | 0 | 0 |
| [3. Clearing stages](#3-clearing-stages) | 4 | 1 | 0 | 1 | 2 | 0 |
| [4. Pricing mechanisms](#4-pricing-mechanisms) | 3 | 2 | 0 | 1 | 0 | 0 |
| [5. Settlement, battery and balances](#5-settlement-battery-and-balances) | 8 | 6 | 0 | 1 | 1 | 0 |
| [6. DSO: balance and grid fees](#6-dso-balance-and-grid-fees) | 11 | 4 | 0 | 3 | 1 | 3 |
| [7. Grid model used by the market](#7-grid-model-used-by-the-market) | 7 | 1 | 5 | 1 | 0 | 0 |
| [8. Reputation](#8-reputation) | 4 | 3 | 0 | 1 | 0 | 0 |
| [9. Trade ledger](#9-trade-ledger) | 1 | 0 | 0 | 0 | 1 | 0 |
| **Total** | **46** | **24** | **6** | **8** | **5** | **3** |

The most consequential ones for any result produced with the original:

- **Batteries ran backwards.** Selling energy *charged* the battery (I-18), and
  the discharge efficiency was applied the wrong way round (I-20).
- **Two pricing mechanisms returned the buyer's bid.** One was `SELLER` (I-13). The
  other was `BID_ASK_SPREAD` (I-17), which the paper's own case study uses.
- **The money and the DSO balance never moved.** Profit was never updated (I-27),
  fees were never charged (I-28), and the DSO balance stayed at 0 (I-24).
- **Reputation only ever measured one thing.** Reliability was always 1 and the
  grid part was always neutral, so only price fairness moved. The decay was weighted
  by the time of day (I-38).
- **The grid's edge flows** started random and piled up over the day (I-33). Only
  stage-1 trades fed them (I-32).

## 1. The market step

| ID | What was wrong | Origin | Status in `marlem-clean` |
|---|---|---|---|
| [I-01](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/lem.py#L459-L469) | Only 23 of 24 periods ran: termination was checked after the step counter moved, against `max_steps − 1` | Fidelity | **Fixed.** A day is `24 / step_hours` steps and all of them run ([lem.py](../../core/market/lem.py#L252-L259)) |
| [I-78](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/lem.py#L349-L350) | An invalid order raised `ValueError` instead of being dropped (`ValidateOrder` in [P1] Algorithm 1) | Fidelity | **Fixed.** Orders are clipped to the market bounds and to eq. 15, or dropped, and each change is noted ([lem.py](../../core/market/lem.py#L454)) |
| [I-56](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/der.py#L36) | Units and time step mixed W/kW/kWh/Wh and $/Wh vs $/kWh, with no explicit Δt. [P1] uses $/MWh (35–280) | Paper | **Fixed.** Energy is kWh per step, power is kW, prices are per kWh, and the step length `step_hours` (1 h or 15 min) is explicit ([scenario.py](../../core/config/scenario.py#L33)) |
| [I-05](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/lem.py#L285-L299), [I-06](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/adapters/profiles/der.py#L120-L132) | Profiles passed to an agent were overwritten at reset. CSV profiles took a random column at a random scale. The procedural generation was additive, not eq. 17's multiplicative form | Code / Fidelity | **Replaced.** Generation and demand come from the SimBench profiles of the network elements a participant owns, the same at every reset ([der.py](../../core/market/agent/der.py)). Eq. 17 is not used |

## 2. Orders and feasibility

| ID | What was wrong | Origin | Status in `marlem-clean` |
|---|---|---|---|
| [I-08](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/der.py#L202-L234) | Feasibility clipping did not implement eq. 15: it treated the requested quantity as the need | Fidelity | **Fixed.** `max_sell_kwh` / `max_buy_kwh` are eq. 15a-b, using the battery's room (eq. 15c-d) ([der.py](../../core/market/agent/der.py#L154-L161)) |
| [I-09](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/der.py#L202) | The order side was read as truthy when sizing but as `> 0.5` when submitting. An order could be sized as a buy and submitted as a sell | Fidelity | **Fixed by design.** The side is a boolean in the order intent; decoding a continuous action is RL-layer work |
| [I-11](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/der.py#L238-L239) | No way to submit nothing when `q_min > 0` | Paper | **Fixed at the market layer.** A participant with nothing to trade places no order, and orders at or below `q_min` are dropped. Whether an RL action can say "nothing" is left to the RL layer |
| [I-12](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/matching.py#L370-L371) | Orders were changed in place during clearing. Everything read afterwards (reward, KPIs, info) saw residual quantities of 0 instead of what was submitted (T3) | Code | **Fixed.** Every stage works on copies; the submitted orders are never changed ([clearing.py](../../core/market/clearing.py#L113)) |

## 3. Clearing stages

| ID | What was wrong | Origin | Status in `marlem-clean` |
|---|---|---|---|
| [I-15](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/matching.py#L635-L663) | Orders naming the DSO as partner were cleared with the DSO in stage 1, before any peer matching. [P1] §3.3.2 has no such sub-stage | Paper | **Decided.** Orders that prefer the DSO skip stages 1 and 2 and are cleared in stage 3 ([clearing.py](../../core/market/clearing.py#L118)) |
| [I-77](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/der.py#L140-L163) | The rule-based partner choice was a sort (reputation first, then distance) followed by a random pick from the top half. [P1] §3.4 says it is "a weighted score of high reputation and short grid distance" | Fidelity | **Fixed.** Weighted score: 0.5 · reputation + 0.5 · closeness ([der.py](../../core/market/agent/der.py#L163)) |
| [I-55](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/matching.py#L317-L318) | The stage-2 capacity check compared `max_quantity · N` with the current balance, not grid capacity with the projected trade | Code | **Open.** The check is gone, and the power flow reports violations without blocking trades. [P1] says violating trades "can be penalized or disallowed by the DSO" but does not choose; no policy is set yet |
| N-01 | `marlem-clean`'s stage 1 lets mutually preferred partners trade **whatever their prices**, even when the bid is below the ask. The original checked bid ≥ ask first (`DSOAgent.validate_grid_constraints`, called in `_match_preferred_partners`). [P1] does not say | Rebuild | **Open.** Found by the notebook check "peer price between ask and bid" at bid margin 0.6. To decide: require bid ≥ ask in stage 1 (as the original) or keep the preference absolute ([clearing.py](../../core/market/clearing.py#L109)) |

## 4. Pricing mechanisms

| ID | What was wrong | Origin | Status in `marlem-clean` |
|---|---|---|---|
| [I-13](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/mechanism.py#L70-L85) | `SELLER` pricing returned the **buyer's** price: each mechanism named its own arguments, and the caller passed them by position (T6: buy 200, sell 50 → 200) | Fidelity | **Fixed.** Every mechanism has one fixed signature (buy order, sell order, reference price) ([clearing_price.py](../../core/market/clearing_price.py#L58)) |
| [I-17](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/mechanism.py#L89-L113) | `BID_ASK_SPREAD` received the market price as its `factor`, so it also returned the buyer's bid (T12). This is the mechanism of [P1]'s case study, and §3.3.3 does not define it | Fidelity | **Fixed.** `factor` is its own argument (0.5 = the midpoint) ([clearing_price.py](../../core/market/clearing_price.py#L67-L79)). That it is undefined in [P1] stays noted |
| [I-16](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/matching.py#L410) | The step's clearing price was a volume-weighted average that **included the DSO's trades** at its tariffs, so it was not a peer-to-peer price | Paper | **Decided.** Volume-weighted price of the peer trades only; the previous price when there were none ([lem.py](../../core/market/lem.py#L513)) |

## 5. Settlement, battery and balances

| ID | What was wrong | Origin | Status in `marlem-clean` |
|---|---|---|---|
| [I-18](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/der.py#L302-L314) | **Battery dispatch had the trade term's sign reversed: selling charged the battery** (T7: selling 10 kWh with G = D took the battery from 50 to 60) | Fidelity | **Fixed.** After its trades a participant has `(G − D) + (bought − sold)` left (eq. 13); a surplus charges the battery and a deficit discharges it ([der.py](../../core/market/agent/der.py#L196-L219)) |
| [I-19](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/battery.py#L96-L112) | A charge was refused entirely if it would pass SoC_max; there was no partial fill | Fidelity | **Fixed.** The battery takes what it can ([battery.py](../../core/market/agent/battery.py#L121)) |
| [I-20](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/battery.py#L162-L180) | **Discharge efficiency was applied the wrong way** (`· η` instead of `/ η`), so delivering energy drained *less* than was delivered | Fidelity | **Fixed.** Eq. 16: `E ← E − E_out / η_discharge` ([battery.py](../../core/market/agent/battery.py#L130)) |
| [I-71](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/battery.py#L134-L180) | [P1] mentions charge/discharge rate limits, but eq. 16 has none, and eq. 15c-d ignores the efficiencies, so it overstates what the battery can take or give | Paper | **Decided.** The room includes the efficiencies, `(E_max − E) / η_charge` and `(E − E_min) · η_discharge`, plus an optional power limit `max_power_kw` ([battery.py](../../core/market/agent/battery.py#L107-L119)) |
| [I-22](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/lem.py#L402-L423) | No household energy balance was enforced: trades, battery and demand were not tied together | Paper | **Fixed.** Eq. 13 → battery → whatever is left goes upstream untraded. The power flow uses what each participant physically did, never its trades ([der.py](../../core/market/agent/der.py#L236)) |
| [I-26](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/lem.py#L455) | The agent's balance was `sold − bought`, not eq. 13 | Fidelity | **Fixed.** `balance_kwh` is eq. 13 ([der.py](../../core/market/agent/der.py#L214)) |
| [I-27](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/der.py#L63) | **Agent profit (eq. 14) was never updated:** it stayed 0 all episode (T5) | Fidelity | **Fixed.** Profit adds each step's revenue minus cost minus grid fees. The participants' and the DSO's money adds up to 0 every step (notebook check "money adds up") |
| [I-21](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marl/agents/der.py#L258-L270) | Demand satisfied ignored battery discharge | Code | **Open.** The "demand satisfied vs deferred" counters of [P1] §3.4.1 are not rebuilt yet; demand is always met (battery, trades or upstream) |

## 6. DSO: balance and grid fees

| ID | What was wrong | Origin | Status in `marlem-clean` |
|---|---|---|---|
| [I-24](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/matching.py#L275-L283) | **The DSO balance (eq. 7) stayed at 0** (T4). It changed only on stage-1 trades with the DSO, and carried over between steps | Fidelity | **Fixed.** `Dso.settle`: energy sold minus bought per step and over the day, with the DSO's revenue and fees ([dso.py](../../core/market/dso/dso.py#L225)) |
| [I-25](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/matching.py#L656-L663) | Two functions used opposite sign conventions for the DSO balance | Code | **Fixed.** One convention: sold − bought (+ the market imports) |
| [I-23](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/lem.py#L489) | The market balance B_grid (eq. 20) was never computed; "grid balance" meant the DSO balance | Fidelity | **Fixed.** `grid_balance_kwh`: energy offered minus energy asked in the step's orders ([lem.py](../../core/market/lem.py#L177)). That this is taken *before* stage 3 is a decision: after the DSO clears, B_grid is always 0 |
| [I-28](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/dso/dso.py#L350-L351) | **Grid fees were computed but never charged to anyone** | Fidelity | **Fixed.** The DSO puts the fee on every trade (`Dso.assess`). It is split 50/50 between peers, paid in full by the participant on a DSO trade, and taken from profit ([dso.py](../../core/market/dso/dso.py#L178-L204)) |
| [I-29](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/dso/dso.py#L297) | `F_trans` is named in eq. 8 but has no formula; the code used 0, although it computed the distance | Paper | **Decided.** The lost energy at the trade price, `l_ij · p_ij` ([P1] §3.5.2: losses are "included in the DSO fees") ([dso.py](../../core/market/dso/dso.py#L137)) |
| [I-30](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/dso/dso.py#L332-L339) | `F_volt` was charged only *above* the threshold and then capped at 0.2. Eq. 8c is `min(V_drop, V_threshold)`, which uses the threshold as the cap. The `F_thermal` cap (0.3) is undefined in [P1] | Fidelity | **Decided.** `F_volt` as eq. 8c; the thermal cap kept at the original's 0.3 as `f_threshold` |
| [I-31](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/dso/dso.py#L343-L346) | `F_imb` was always 0. Eq. 8h defines the balance impact only for trades **with the DSO**, but the original made DSO trades fee-free, so the imbalance fee could never apply (N-04) | Fidelity / Paper | **Decided.** Charged on DSO trades that worsen B_grid (the DSO buying in excess demand or selling in excess supply); a trade that helps pays nothing ([dso.py](../../core/market/dso/dso.py#L163)) |
| [I-54](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/dso/dso.py#L192-L275) | The DSO fallback skipped grid feasibility (zero distance, loss and fee), and the grid check ignored direction | Code | **Open.** DSO trades are at no distance and lose nothing, as before. No trade is blocked for grid reasons; see I-55 |
| [I-74](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/dso/dso.py#L66-L68) | The thermal-fee threshold (20 % loading) sits far below the congestion threshold (80 %) | Paper | **Flagged.** Kept as the original's defaults |
| N-05 | With the original's fee factors, the same-zone bonus (15 % of the trade's value) is larger than all other fees together (about 3 % on a low-voltage feeder). Fees come out **negative** overall, so the DSO pays peers to trade locally. [P1] gives no factor values | Paper | **Flagged.** Factors kept; `zone_factor` is one setting |
| N-06 | Zones ([P1] §3.5.4) are defined only for the paper's graph topologies; a real feeder network needs its own definition | Paper | **Flagged.** A zone is a feeder: the branch leaving the transformer's low-voltage busbar ([powerflow.py](../../core/grid/powerflow.py#L190)) |

## 7. Grid model used by the market

| ID | What was wrong | Origin | Status in `marlem-clean` |
|---|---|---|---|
| [I-33](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/adapters/grid/network.py#L87) | Edge flows started random and **accumulated over the whole episode** instead of being per period, so congestion never went down (T10) | Fidelity | **Replaced.** One AC power flow per step on a fresh state ([powerflow.py](../../core/grid/powerflow.py#L105)) |
| [I-32](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/matching.py#L603) | Only stage-1 trades updated the edge flows | Fidelity | **Replaced.** The flow comes from each participant's physical injection, whichever stage its trades came from |
| [I-57](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/grid/config.py#L38-L48) | The IEEE-34 graph was disconnected (edge 832–888 missing; T13), and its impedance table was unused | Fidelity | **Replaced.** SimBench networks |
| [I-70](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/adapters/grid/network.py#L338-L355) | The physics is linear and unbounded: losses grow with `d · q` (unbounded once `d · κ > 1`), voltage drop is `f · d`, and flows are transport on a graph. [P1] calls this "high-fidelity" | Paper | **Replaced** for the physics (pandapower AC power flow). The paper's linear forms remain only inside the market's fee formulas (eq. 8f, eq. 18) |
| [I-53](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/adapters/grid/network.py#L98-L99) | Defensive code hid bad state: a dead capacity check, a bare `except`, mutable defaults | Code | **Replaced.** The grid code is new; elements reject impossible settings (e.g. `Battery._check`, `Scenario.problems`) |
| [I-14](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/matching.py#L370) | P2P losses were topped up from the DSO, and the buyer's energy bought counted `q + loss` | Fidelity | **Decided.** The market is lossless. Each trade **records** its loss (eq. 18) and pays for it in the fee; the physical losses are the power flow's |
| [I-34](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/adapters/grid/network.py#L338-L355) | The loss factor κ = 0.03 was hard-coded | Code | **Fixed.** `loss_factor` is a DSO setting, per km of line ([scenario.py](../../core/config/scenario.py#L172)). Trades also record their distance d_ij, which the original never filled in |

## 8. Reputation

| ID | What was wrong | Origin | Status in `marlem-clean` |
|---|---|---|---|
| [I-38](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/reputation.py#L132) | **Reliability was always 1.** Eq. 12 calls it "matched to total order volume". The code counted trades against unmatched orders, and the DSO clears every order, so nothing was ever unmatched | Fidelity | **Fixed.** Order volume matched by peers ÷ order volume (STEP 1 of `_calculate_reputation`, [reputation.py](../../core/market/reputation.py#L193)) |
| [I-38](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/reputation.py#L89) | **The decay was weighted by the time of day.** At the first step the old reputation was thrown away; in the last hours new behaviour counted almost nothing (weight ≈ 0.04). [P1] asks for a decay that weighs recent behaviour *more* | Fidelity | **Fixed.** A constant decay, `r ← decay · r + (1 − decay) · score`, with `decay = 0.8`, in `update_reputation` ([reputation.py](../../core/market/reputation.py#L119)) |
| [I-38](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/reputation.py#L132), N-02, N-03 | **The grid part was always neutral.** It was measured against the DSO balance, which stayed 0 (I-24). A trade with the DSO also returned 0.5 on the −1 to 1 scale, so it counted as helping (N-03). Fairness compared trade prices with a clearing price that included the DSO's tariffs (N-02, see I-16) | Fidelity / Code | **Fixed.** The grid part uses the step's B_grid, and DSO trades are neutral (0). Fairness uses the agent's peer trades against the peer clearing price (STEP 2-3, [reputation.py](../../core/market/reputation.py#L199-L230)) |
| [I-07](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/reputation.py#L57-L69) | Every agent got the same "random" initial reputation, because the random generator was reseeded before each draw. A random start is not in [P1] | Code | **Decided.** Everyone starts at 0.5. `ReputationHandler.reset` is kept, now with its own random generator, but not used |

The weights (0.3 / 0.2 / 0.5) and the decay value are not given in [P1]. The
weights are the original's and the decay value is a choice. All the dials sit in
`ReputationHandler`, as in the original.

## 9. Trade ledger

| ID | What was wrong | Origin | Status in `marlem-clean` |
|---|---|---|---|
| [I-66](https://github.com/KevinRapo/P2P-thesis/blob/marlem-annotated/src_thesis/marketplace/market/validation.py#L26-L35) | The block hash covers buyer, seller, price, quantity and time, but not losses or fees. A block is forced every step, and the proof of work runs in memory, not as a consensus | Code | **Open.** Original code, off by default (`ledger_difficulty = 0`). Now that fees are charged, the hash should cover them |

## Problems in the paper's market method

What the paper itself leaves wrong or open, whatever the code does. Each row needs a
recorded decision, because the paper cannot settle it.

| Topic | The problem in [P1] | Issues |
|---|---|---|
| Battery (eq. 15–16) | Eq. 15c-d ignores the efficiencies; the text claims rate limits that eq. 16 does not have | I-71 |
| Grid fees (eq. 8) | `F_trans` has no formula. No fee factor has a value. The thermal threshold sits below the congestion threshold. Eq. 8c uses the "threshold" as a cap | I-29, I-30, I-74, N-05 |
| Imbalance fee (eq. 8b, 8h) | Defined only for trades with the DSO; whether those pay fees is not said | I-31 |
| B_grid (eq. 20) | Its timing is not given. After the DSO clears every order it is 0 by construction, so it only means something before stage 3 | I-23 |
| Clearing price | Not defined. The original mixed peer prices with the DSO's tariffs | I-16 |
| Stage 1 | Whether mutually preferred partners must still have bid ≥ ask is not said. Neither is the DSO-preferred sub-stage the original added | I-15, N-01 |
| Pricing | The case study's bid-ask spread mechanism is not among the mechanisms of §3.3.3 | I-17 |
| Reputation (eq. 12) | Weights and decay factor have no values; "fairness" and "grid contribution" have no formulas | I-38 |
| Grid physics | Linear, unbounded losses and voltage drop, called "high-fidelity". Capacity violations "can be penalized or disallowed", with no choice made | I-70, I-55 |
| Zones | Defined for graph topologies only | N-06 |
| Units | $/MWh in the case study, kWh per implicit 1-hour step | I-56 |

## What this means for the published results

[P1]'s Case 5 (batteries with zero-intelligence agents) ran on this market. If the
paper's figures were produced with the original code, which cannot be confirmed
independently:

- **The P2P prices in Fig. 5 are the buyers' bids.** The case uses `BID_ASK_SPREAD`,
  which returned the buyer's price (I-17).
- **The batteries did not behave as described.** Selling charged them (I-18),
  discharge drained less than it delivered (I-20), and a charge reaching SoC_max was
  refused entirely (I-19).
- **No money moved:** no profit (I-27), no fees (I-28), no DSO balance (I-24).

So the paper's conclusion that batteries stabilise prices is **not supported** by the
original market. A thesis built on `marlem-clean` is a corrected reimplementation
of the paper's market, not a reproduction of its results.

## Outside this document

The register's other IDs belong to the RL layer and are validated on the RL branch:

- **Actions and observations:** I-10, I-39, I-40, I-58
- **Reward:** I-02, I-41 to I-47, I-75, I-76, I-79
- **KPIs:** I-35 to I-37, I-65, I-68, I-69
- **Paradigms, training and inference:** I-48 to I-50, I-59 to I-62, I-73
- **Experiments and reproducibility:** I-03, I-04, I-51, I-63, I-64, I-72, I-80
- **Tests and docs:** I-52, I-67
