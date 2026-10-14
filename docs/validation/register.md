# Issue register: the original MARLEM implementation

> Every issue found in the public MARLEM release and in the two papers that
> describe it, in one list with one stable ID each. This is the register the
> thesis cites. It describes the **original**, frozen at the commit below; what
> the rebuild does about each issue is on the detail pages
> ([market layer](market.md), [RL layer](rl.md)), not here.

**Version 1.0, 14 October 2026.** A new finding gets the next free ID; existing IDs
and their descriptions do not change.

## About this register

**What was audited.**

- **The code:** the authors' repository
  [salazarna/marlem](https://github.com/salazarna/marlem/tree/15d6715a7b7ad31700d3758f2a2dd9df053773a7)
  at commit `15d6715` (March 2026), the public release both papers point to. Every
  code link below is pinned to that commit, so its line numbers stay valid.
- **[P1]** Salazar-Peña, Tabares, González-Mancera. *MARLEM: A multi-agent
  reinforcement learning simulation framework for implicit cooperation in
  decentralized local energy markets.* Applied Energy 412 (2026) 127546,
  [doi:10.1016/j.apenergy.2026.127546](https://doi.org/10.1016/j.apenergy.2026.127546).
  Peer reviewed. Defines the market, the agents, the grid and the training
  paradigms; its case studies use zero-intelligence agents.
- **[P2]** Same authors. *Harnessing implicit cooperation: a multi-agent
  reinforcement learning approach towards decentralized local energy markets.*
  SSRN preprint 6685504, not peer reviewed. Gives the paradigms' and algorithms'
  formulas and trains the 3 × 3 matrix of paradigms and algorithms.
- **RLlib** (Ray 2.51.1), where the original relies on its behaviour; checked in
  its installed source.

**How the issues were found: an AI-assisted audit.** The code was reviewed line by
line against the two papers with the help of an AI coding assistant, which
proposed candidate findings together with the lines at fault. No candidate entered
the register on the assistant's word. Each was checked by the author against the
original code: by reading the cited lines and the code that calls them, by a small
executable demonstration on the original code, by a test on the RL test bench, or
by running the original as shipped. The **Evidence** column says which. Findings
about the papers' method itself (origin *Paper*) are judgments that no test can
settle; they are listed because the rebuild has to decide them.

**What an issue is.** A defect in the code, a deviation of the code from the
papers, or a question the papers leave open. It is not necessarily a bug, and the
number of issues is not a measure of the papers' ideas: most of the method holds up
(see [Problems in the papers' method](#problems-in-the-papers-method)). Which
implementation produced the papers' published results is not known; this register
describes the public release only.

## How to read the register

**IDs.**

| IDs | Found |
|---|---|
| I-01 to I-80 | The audit of the original code against both papers (September 2026) |
| I-38a, I-38b, I-38c | I-38 (reputation) split into its three independent parts |
| I-81, I-82 | Running the original's examples and training as shipped (August 2026) |
| N-05, N-06 | Rebuilding the market on SimBench networks |
| R-01 to R-06 | The RL test bench ([rl.md](rl.md#the-test-bench)) |

**Columns.**

| Column | Values |
|---|---|
| **Origin** | **Paper**: the paper is wrong, contradictory or silent where the method needs an answer. **Fidelity**: the code does not do what the paper says. **Code**: a programming defect the paper says nothing about |
| **Type** | **Defect**: the code computes something wrong. **Deviation**: it works, but differs from the paper or from good practice. **Decision**: the papers leave a choice open that has to be made |
| **Evidence** | **Demo**: a small executable demonstration on the original code shows what the paper (or the code's own documentation) expects next to what the code does. **Test**: reproduced on the RL test bench. **Run**: seen when running the original as shipped (its tests, its examples, a training run). **Read**: found by reading the code and its callers, not executed. **Judgment**: a question about the method that no test can settle |
| **Original code** | The lines at fault, at commit `15d6715` |
| **Details** | The issue's section on a detail page: the original lines, why they are wrong, and what the rebuild does. **—**: no detail page yet |

## Summary

| Part | Issues | Paper | Fidelity | Code | Defect | Deviation | Decision |
|---|---|---|---|---|---|---|---|
| [A. Market layer](#a-market-layer) | 46 | 11 | 25 | 10 | 19 | 16 | 11 |
| [B. Environment and cooperation](#b-environment-and-cooperation) | 22 | 8 | 9 | 5 | 6 | 9 | 7 |
| [C. Learning layer](#c-learning-layer) | 18 | 4 | 1 | 13 | 10 | 4 | 4 |
| [D. Experiments, data and repository](#d-experiments-data-and-repository) | 6 | 2 | 0 | 4 | 1 | 3 | 2 |
| **Total** | **92** | **25** | **35** | **32** | **36** | **32** | **24** |

Evidence: 48 Demo, 4 Test, 3 Run, 21 Read, 16 Judgment.

Six issues decide most of what the original can and cannot show:

- **Batteries run backwards** ([I-18](#I-18), [I-20](#I-20)): selling charges the
  battery.
- **Two pricing mechanisms return the buyer's bid** ([I-13](#I-13),
  [I-17](#I-17)), one of them the mechanism of [P1]'s own case study.
- **No money moves** ([I-27](#I-27), [I-28](#I-28), [I-24](#I-24)): profit, fees
  and the DSO balance stay at zero.
- **The grid is not a power flow** ([I-70](#I-70), [I-57](#I-57), [I-33](#I-33)):
  linear estimates on a disconnected graph whose flows pile up over the day.
- **The reward the agents learn from is partly constant** ([I-43](#I-43),
  [I-44](#I-44), [I-41](#I-41)).
- **CTDE never trains the networks that act** ([I-48](#I-48)), and the paradigms
  are not compared like for like ([R-03](#R-03), [I-60](#I-60), [I-73](#I-73)).

## The register

### A. Market layer

#### The market step

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-01"></a>I-01 | Only 23 of 24 periods run: termination is checked after the step increment against `max_steps − 1` | Fidelity | Defect | Demo | [lem.py:433–445](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L433-L445) | [market](market.md#i-01-only-23-of-24-periods-run) |
| <a id="I-05"></a>I-05 | Profiles passed to `DERAgent(...)` are overwritten at `reset()` | Code | Deviation | Demo | [lem.py:281–293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L281-L293)<br>[base.py:40–43](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/base.py#L40-L43)<br>[der.py:119–129](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/der.py#L119-L129) | [market](market.md#i-05-i-06-a-reset-cannot-be-told-which-profiles-to-use) |
| <a id="I-06"></a>I-06 | CSV profiles use a random column and random scale per reset. Procedural G is additive, not eq. 17's multiplicative form | Fidelity | Deviation | Read | [lem.py:281–293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L281-L293)<br>[base.py:40–43](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/base.py#L40-L43)<br>[der.py:119–129](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/der.py#L119-L129) | [market](market.md#i-05-i-06-a-reset-cannot-be-told-which-profiles-to-use) |
| <a id="I-56"></a>I-56 | Units and time step are inconsistent (W, kW, kWh, Wh; USD/Wh vs USD/kWh), and Δt is implicit | Paper | Decision | Judgment | [der.py:35](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L35)<br>[matching.py:33–36](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L33-L36) | [market](market.md#i-56-units-and-time-step-are-mixed) |
| <a id="I-78"></a>I-78 | Invalid actions raise `ValueError` instead of being dropped (Alg. 1 `ValidateOrder`) | Fidelity | Deviation | Demo | [lem.py:336–343](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L336-L343) | [market](market.md#i-78-an-invalid-order-stops-the-simulation) |

#### Orders and feasibility

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-08"></a>I-08 | Feasibility clipping does not implement eq. 15: it treats the requested `q` as the need | Fidelity | Defect | Demo | [der.py:184–228](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L184-L228) | [market](market.md#i-08-feasibility-clipping-is-not-eq-15) |
| <a id="I-09"></a>I-09 | `is_buy` is truthy in `adjust_action_for_battery` but `> 0.5` in `step`, so the order is sized for the wrong direction | Fidelity | Defect | Demo | [der.py:196](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L196)<br>[lem.py:358](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L358) | [market](market.md#i-09-an-order-can-be-sized-as-a-buy-and-submitted-as-a-sell) |
| <a id="I-11"></a>I-11 | No "submit nothing" action when `q_min > 0` | Paper | Decision | Demo | [der.py:231–232](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L231-L232) | [market](market.md#i-11-no-way-to-submit-nothing) |
| <a id="I-12"></a>I-12 | Orders are mutated in place, so the reward, KPIs and info see residual quantities (0), not submitted ones | Code | Defect | Demo | [matching.py:347–348](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L347-L348)<br>[dso.py:212–253](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L212-L253)<br>[lem.py:424–425](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L424-L425) | [market](market.md#i-12-clearing-overwrites-the-submitted-orders) |

#### Clearing stages

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-15"></a>I-15 | Stage 1 clears DSO-preferred orders with the DSO before any P2P matching | Paper | Decision | Demo | [matching.py:608–623](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L608-L623) | [market](market.md#i-15-dso-preferred-orders-are-cleared-before-the-peer-market) |
| <a id="I-55"></a>I-55 | The Stage-2 capacity check uses `max_quantity·N` and the current balance, not grid capacity or the projected trade | Code | Defect | Demo | [matching.py:158](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L158) | [market](market.md#i-55-the-stage-2-capacity-check-can-never-trigger) |
| <a id="I-77"></a>I-77 | Rule-based partner selection is a lexicographic sort plus a random top-half pick, not a weighted score | Fidelity | Deviation | Demo | [der.py:154–159](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L154-L159)<br>[lem.py:362–365](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L362-L365) | [market](market.md#i-77-partner-choice-is-a-sort-and-a-random-pick-not-a-weighted-score) |

#### Pricing mechanisms

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-13"></a>I-13 | `SELLER` pricing returns the buyer's price (positional-argument bug) | Fidelity | Defect | Demo | [mechanism.py:69–84](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/mechanism.py#L69-L84)<br>[matching.py:310–312](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L310-L312) | [market](market.md#i-13-seller-pricing-returns-the-buyers-price) |
| <a id="I-16"></a>I-16 | The clearing price is a VWAP that includes DSO trades | Paper | Decision | Demo | [matching.py:368–385](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L368-L385) | [market](market.md#i-16-the-clearing-price-includes-the-dsos-trades) |
| <a id="I-17"></a>I-17 | `BID_ASK_SPREAD` pricing receives `market_price` as `factor`, so it returns the buyer's price. The mechanism is also absent from §3.3.3 | Fidelity | Defect | Demo | [mechanism.py:87–111](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/mechanism.py#L87-L111) | [market](market.md#i-17-bid_ask_spread-returns-the-buyers-price-too) |

#### Settlement, battery and balances

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-18"></a>I-18 | Battery dispatch has the trade term's sign reversed: selling charges the battery | Fidelity | Defect | Demo | [der.py:293–305](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L293-L305)<br>[lem.py:392–401](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L392-L401) | [market](market.md#i-18-selling-charges-the-battery) |
| <a id="I-19"></a>I-19 | A charge is refused entirely if it would reach SoC_max; there is no partial fill | Fidelity | Defect | Demo | [battery.py:95–156](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L95-L156) | [market](market.md#i-19-a-charge-that-would-fill-the-battery-is-refused-entirely) |
| <a id="I-20"></a>I-20 | Discharge efficiency is applied in the wrong direction (`·η` instead of `/η`) | Fidelity | Defect | Demo | [battery.py:158–179](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L158-L179) | [market](market.md#i-20-discharge-efficiency-is-applied-the-wrong-way) |
| <a id="I-21"></a>I-21 | Demand satisfaction ignores battery discharge | Code | Deviation | Demo | [der.py:250–262](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L250-L262) | [market](market.md#i-21-demand-satisfied-ignores-battery-discharge) |
| <a id="I-22"></a>I-22 | No household energy-conservation identity is enforced | Paper | Decision | Judgment | [lem.py:392–411](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L392-L411) | [market](market.md#i-22-no-household-energy-balance) |
| <a id="I-26"></a>I-26 | `agent.balance = sold − bought`, not eq. 13 | Fidelity | Deviation | Demo | [lem.py:440](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L440)<br>[matching.py:426–445](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L426-L445)<br>[reward.py:297](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L297) | [market](market.md#i-26-the-agents-balance-is-its-net-trade-in-the-other-sign-convention) |
| <a id="I-27"></a>I-27 | Agent profit (eq. 14) is never updated | Fidelity | Defect | Demo | [der.py:61](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L61)<br>[observation.py:342](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L342) | [market](market.md#i-27-profit-is-never-updated) |
| <a id="I-71"></a>I-71 | Battery model has no charge/discharge power limit (claimed in the text), and eq. 15 ignores efficiency | Paper | Decision | Judgment | [battery.py:205–214](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L205-L214) | [market](market.md#i-71-no-power-limit-and-eq-15-ignores-efficiency) |

#### DSO: balance and grid fees

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-23"></a>I-23 | `B_grid` (eq. 20) is never computed. The "grid balance" observation is `dso.balance` | Fidelity | Defect | Demo | [lem.py:472](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L472)<br>[observation.py:285](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L285) | [market](market.md#i-23-the-market-balance-b_textgrid-is-never-computed) |
| <a id="I-24"></a>I-24 | `dso.balance` changes only on Stage-1 DSO-preferred trades and carries across steps, so it is ≡ 0 by default | Fidelity | Defect | Demo | [matching.py:258–374](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L258-L374) | [market](market.md#i-24-the-dso-balance-stays-at-0) |
| <a id="I-25"></a>I-25 | The B_DSO sign convention is inconsistent between `match_orders` and `_match_preferred_partners` | Code | Decision | Read | [matching.py:626–633](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L626-L633) | [market](market.md#i-25-two-opposite-sign-conventions-for-the-dso-balance) |
| <a id="I-28"></a>I-28 | Grid fees are computed but never charged to anyone | Fidelity | Defect | Demo | [dso.py:342–345](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L342-L345)<br>[matching.py:319–332](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L319-L332) | [market](market.md#i-28-grid-fees-are-computed-but-never-charged) |
| <a id="I-29"></a>I-29 | `F_trans` has no formula in the paper; the code uses 0 | Paper | Decision | Judgment | [dso.py:293–314](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L293-L314) | [market](market.md#i-29-f_texttrans-has-no-formula-and-the-code-uses-0) |
| <a id="I-30"></a>I-30 | `F_volt` and `F_thermal` caps (0.2, 0.3) differ from or are undefined in the paper | Fidelity | Deviation | Read | [dso.py:326–333](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L326-L333) | [market](market.md#i-30-f_textvolt-is-gated-by-its-threshold-and-capped-at-02) |
| <a id="I-31"></a>I-31 | `F_imb` is effectively always 0 | Fidelity | Deviation | Read | [dso.py:336–339](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L336-L339)<br>[dso.py:411–442](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L411-L442)<br>[dso.py:219–226](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L219-L226) | [market](market.md#i-31-the-imbalance-fee-can-never-apply) |
| <a id="I-54"></a>I-54 | DSO fallback skips grid feasibility (zero distance, loss and fee), and `validate_grid_constraints` ignores direction | Code | Deviation | Demo | [dso.py:219–226](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L219-L226) | [market](market.md#i-54-dso-trades-skip-the-grid-and-the-grid-check-ignores-direction) |
| <a id="I-74"></a>I-74 | Thermal-fee threshold (20 %) sits below the congestion threshold (80 %) | Paper | Deviation | Judgment | [dso.py:65–67](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L65-L67) | [market](market.md#i-74-the-thermal-fee-starts-far-below-the-congestion-fee) |
| <a id="N-05"></a>N-05 | The same-zone bonus outweighs every grid fee | Paper | Decision | Read | [dso.py:317–319](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L317-L319) | [market](market.md#n-05-the-same-zone-bonus-outweighs-every-fee) |
| <a id="N-06"></a>N-06 | Zones are defined only for the paper's graph topologies | Paper | Decision | Read | [dso.py:317](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L317) | [market](market.md#n-06-zones-exist-only-for-the-papers-graphs) |

#### Grid model used by the market

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-14"></a>I-14 | P2P loss is topped up from the DSO. The buyer's `energy_bought` counts `q + loss` | Fidelity | Deviation | Demo | [matching.py:347](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L347)<br>[lem.py:397–401](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L397-L401) | [market](market.md#i-14-losses-are-topped-up-from-the-dso) |
| <a id="I-32"></a>I-32 | Only Stage-1 trades update edge flows | Fidelity | Defect | Demo | [matching.py:569–577](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L569-L577)<br>[matching.py:325–332](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L325-L332) | [market](market.md#i-32-only-stage-1-trades-reach-the-grid) |
| <a id="I-33"></a>I-33 | Edge flows start random and accumulate over the episode instead of being per period | Fidelity | Defect | Demo | [network.py:84–85](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L84-L85) | [market](market.md#i-33-edge-flows-start-random-and-pile-up-all-episode) |
| <a id="I-34"></a>I-34 | Loss factor κ = 0.03 is hard-coded | Code | Deviation | Read | [network.py:331–334](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L331-L334)<br>[matching.py:316](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L316) | [market](market.md#i-34-the-loss-factor-is-hard-coded) |
| <a id="I-53"></a>I-53 | Defensive checks hide bad state (dead capacity check, bare `except`, float-only validators, mutable defaults) | Code | Deviation | Read | [network.py:38](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L38)<br>[base.py:51–57](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/base.py#L51-L57) | [market](market.md#i-53-defensive-code-hides-bad-state) |
| <a id="I-57"></a>I-57 | IEEE-34 graph is disconnected (edge 832–888 missing), and the impedance table is unused | Fidelity | Defect | Demo | [config.py:29–39](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/config.py#L29-L39) | [market](market.md#i-57-the-ieee-34-graph-is-disconnected) |
| <a id="I-70"></a>I-70 | Grid physics scope: linear unbounded losses, `V_drop = f·d`, transport flows. "High-fidelity" is an overclaim | Paper | Decision | Demo | [network.py:331–348](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L331-L348)<br>[dso.py:326](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L326) | [market](market.md#i-70-the-grid-physics-is-linear-and-unbounded) |

#### Reputation

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-07"></a>I-07 | All agents get the same initial reputation (the RNG is reseeded before each draw) | Code | Deviation | Demo | [reputation.py:56–68](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L56-L68)<br>[lem.py:281–283](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L281-L283) | [market](market.md#i-07-every-agent-gets-the-same-random-initial-reputation) |
| <a id="I-38a"></a>I-38a | Reputation: reliability is always 1, because nothing is ever left unmatched | Fidelity | Defect | Demo | [reputation.py:124–129](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L124-L129)<br>[matching.py:380–382](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L380-L382) | [market](market.md#i-38a-reliability-is-always-1) |
| <a id="I-38b"></a>I-38b | Reputation: the decay is weighted by the time of day | Fidelity | Deviation | Read | [reputation.py:86–87](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L86-L87)<br>[lem.py:436–441](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L436-L441) | [market](market.md#i-38b-the-decay-follows-the-time-of-day) |
| <a id="I-38c"></a>I-38c | Reputation: the grid part is always neutral, and fairness mixes in the DSO's trades | Fidelity / Code | Defect | Read | [reputation.py:131–191](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L131-L191) | [market](market.md#i-38c-the-grid-part-is-always-neutral-and-fairness-mixes-in-the-dso) |

#### Trade ledger

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-66"></a>I-66 | The block hash omits loss and fees, and blocks are forced every step (in-memory PoW, not consensus) | Code | Deviation | Demo | [validation.py:25–34](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/validation.py#L25-L34)<br>[matching.py:395–396](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L395-L396) | [market](market.md#i-66-the-block-hash-leaves-out-losses-and-fees) |

### B. Environment and cooperation

#### Action, observation and reset

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-02"></a>I-02 | `is_terminal` is never true, so the terminal unmet-demand penalty never applies | Fidelity | Defect | Demo | [lem.py:430](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L430)<br>[reward.py:207–214](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L207-L214) | — |
| <a id="I-03"></a>I-03 | `reset(seed=None)` falls back to the config seed, so every episode is identical | Code | Deviation | Demo | [lem.py:272–274](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L272-L274) | — |
| <a id="I-04"></a>I-04 | `LocalEnergyMarket.seed()` is shadowed by the `self.seed` attribute | Code | Deviation | Demo | [lem.py:67](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L67)<br>[lem.py:507–514](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L507-L514) | — |
| <a id="I-10"></a>I-10 | β = "no preference" is reachable only at the exact upper bound | Fidelity | Deviation | Demo | [action.py:35–44](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/action.py#L35-L44)<br>[action.py:68–89](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/action.py#L68-L89)<br>[lem.py:359](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L359) | — |
| <a id="I-39"></a>I-39 | Forecast error (`max_error`) is never applied, so the "remaining demand/supply" observations reveal the true future | Fidelity | Defect | Demo | [lem.py:65–66](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L65-L66)<br>[observation.py:338–341](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L338-L341) | — |
| <a id="I-40"></a>I-40 | Observations are raw and unnormalised | Paper | Decision | Demo | [observation.py:333–353](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L333-L353) | — |
| <a id="I-58"></a>I-58 | The reset observation hard-codes G, D, remaining energy and KPIs to 0 | Code | Deviation | Demo | [observation.py:195–257](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L195-L257) | — |

#### KPIs

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-35"></a>I-35 | "Supply-demand imbalance" is volume/C, not `\\|Σbuy − Σsell\\|/C`. The coordination score inherits this | Fidelity | Defect | Demo | [implicit_cooperation.py:122–123](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L122-L123)<br>[implicit_cooperation.py:141–142](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L141-L142) | — |
| <a id="I-36"></a>I-36 | Social welfare is turnover `Σ p·q`, not surplus | Paper | Decision | Demo | [implicit_cooperation.py:93](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L93) | — |
| <a id="I-37"></a>I-37 | Price volatility is computed over the whole episode, not a window | Fidelity | Deviation | Demo | [implicit_cooperation.py:104–105](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L104-L105) | — |
| <a id="I-68"></a>I-68 | Imbalance (eq. 24) over trades is ≡ 0 by construction. Needs a definition over orders or physical net positions, and a timing (before or after DSO clearing) for `B_grid` | Paper | Decision | Judgment | [implicit_cooperation.py:122–123](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L122-L123) | — |
| <a id="I-69"></a>I-69 | "DER self-consumption" is defined as P2P share; the label does not match the quantity | Paper | Deviation | Judgment | [implicit_cooperation.py:188](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L188) | — |

#### Reward

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-41"></a>I-41 | `f_coop` is not in [0, 1] (≈ 1811) | Fidelity | Defect | Demo | [reward.py:170–192](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L170-L192) | — |
| <a id="I-42"></a>I-42 | The cooperation-boost form differs across [P1] eq. 4, the code and [P2] eq. 3 | Paper | Decision | Demo | [reward.py:218–221](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L218-L221) | — |
| <a id="I-43"></a>I-43 | `r_res ≡ −1.5` and `r_trade ≡ 0` (caused by I-12) | Code | Defect | Demo | [reward.py:406–412](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L406-L412)<br>[reward.py:248–249](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L248-L249) | — |
| <a id="I-44"></a>I-44 | `r_grid`, `γ_DSO` and the grid part of `f_contrib` are inactive (caused by I-24) | Fidelity | Defect | Read | [reward.py:202](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L202)<br>[reward.py:253–309](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L253-L309)<br>[reward.py:472–484](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L472-L484) | — |
| <a id="I-45"></a>I-45 | `_w_local` is overwritten 0.7 → 0.3, so `r_trade = 0.3ρ_local + 0.3ρ_dso` (the paper prints 0.3/0.3) | Code | Deviation | Demo | [reward.py:79](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L79)<br>[reward.py:93](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L93) | — |
| <a id="I-46"></a>I-46 | The unmet-demand penalty uses `p_dso`, not the paper's `p_no_trades = 5` | Fidelity | Deviation | Read | [reward.py:207–214](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L207-L214)<br>[reward.py:226](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L226) | — |
| <a id="I-47"></a>I-47 | The no-trade guard returns a fixed −4.46 before any other term | Paper | Decision | Demo | [reward.py:135–136](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L135-L136) | — |
| <a id="I-75"></a>I-75 | `f_coop` has no normalisation ranges for its unbounded KPIs, so the [0, 1] claim is unsupported | Paper | Decision | Judgment | [reward.py:170–192](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L170-L192)<br>[implicit_cooperation.py:93](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L93) | — |
| <a id="I-76"></a>I-76 | `R_base` components have no formulas in the paper; the code is the only specification | Paper | Decision | Judgment | [reward.py:148–166](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L148-L166) | — |
| <a id="I-79"></a>I-79 | `f_contrib` grid term is a heuristic, not [P2]'s marginal `−∂\\|B_grid\\|/∂a_i` | Fidelity | Deviation | Read | [reward.py:472–484](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L472-L484) | — |

### C. Learning layer

#### Training paradigms

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-48"></a>I-48 | CTDE trains a centralized `pi` but acts with per-agent `pi_heads`, which are never trained | Fidelity | Defect | Test | [ctde.py:46–57](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L46-L57)<br>[ctde.py:86–104](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L86-L104)<br>[ctde.py:121–128](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L121-L128) | [rl](rl.md#i-48-ctde-never-trains-the-policies-that-act) |
| <a id="I-60"></a>I-60 | CTCE is a centralized-information baseline, not a true upper bound. The group reward sum scales with N | Paper | Decision | Test | [train.py:676–687](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L676-L687) | [rl](rl.md#i-60-ctce-is-a-centralised-information-baseline-not-an-upper-bound) |
| <a id="I-73"></a>I-73 | Cross-paradigm return comparability: group sum vs per-agent returns | Paper | Decision | Judgment | [train.py:684](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L684) | [rl](rl.md#i-73-returns-of-the-paradigms-are-compared-across-different-scales) |
| <a id="R-03"></a>R-03 | The paradigms train different networks (custom 2 × 128 ReLU in CTCE and CTDE, RLlib's default in DTDE) | Code | Deviation | Read | [train.py:337–341](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L337-L341)<br>[ctce.py:290–306](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L290-L306) | [rl](rl.md#r-03-the-paradigms-train-different-networks) |

#### Grouping the agents

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-59"></a>I-59 | Grouped obs/action tuples may be assigned to the wrong agents: insertion order vs sorted keys | Code | Defect | Demo | [train.py:639–640](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L639-L640)<br>[train.py:702–705](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L702-L705) | [rl](rl.md#i-59-grouped-spaces-are-in-name-order-grouped-data-in-environment-order) |

#### Policy networks and loss

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="R-01"></a>R-01 | The CTCE and CTDE action spread has no upper limit, so it can diverge | Code | Defect | Test | [ctce.py:45](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L45)<br>[ctce.py:309–322](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L309-L322)<br>[ctce.py:365](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L365) | [rl](rl.md#r-01-the-ctce-and-ctde-action-spread-has-no-limit) |
| <a id="R-02"></a>R-02 | `kl_coeff = 0` does not switch off the KL term, and a NaN loss goes unnoticed | Code | Defect | Test | [train.py:216–226](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L216-L226) | [rl](rl.md#r-02-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed) |
| <a id="R-04"></a>R-04 | SAC in CTCE and CTDE uses an unsquashed Gaussian | Code | Defect | Read | [ctce.py:358–373](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L358-L373)<br>[train.py:240](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L240) | [rl](rl.md#r-04-sac-in-ctce-and-ctde-uses-an-unsquashed-gaussian) |
| <a id="R-05"></a>R-05 | SAC's actor in CTCE and CTDE gets no gradient from the critic | Code | Defect | Read | [ctce.py:132–146](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L132-L146)<br>[ctde.py:143–157](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L143-L157) | [rl](rl.md#r-05-sacs-actor-in-ctce-and-ctde-gets-no-gradient-from-the-critic) |

#### Trainer and hyperparameters

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-49"></a>I-49 | The PBT lr domain [1e-4, 1e-2] excludes the initial 1e-5, and the entropy domain reaches 10 | Code | Deviation | Read | [train.py:178–189](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L178-L189) | [rl](rl.md#i-49-population-based-training-jumps-the-learning-rate-and-reaches-entropy-10) |
| <a id="I-50"></a>I-50 | The budget is counted in training iterations, but the paper says "10 000 episodes" | Paper | Decision | Judgment | [train.py:440](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L440) | [rl](rl.md#i-50-the-budget-is-counted-in-iterations-the-paper-in-episodes) |
| <a id="I-62"></a>I-62 | Training config defects: positive `evaluation_duration` rejected, CPUs double-allocated, PBT always on, no `finally` around `ray.shutdown` | Code | Deviation | Demo | [train.py:116](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L116)<br>[train.py:285–293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L285-L293)<br>[train.py:426–458](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L426-L458) | [rl](rl.md#i-62-training-configuration-defects) |
| <a id="I-81"></a>I-81 | Evaluation is configured with the replay buffer's `StorageUnit.EPISODES` instead of `"episodes"`: each evaluation completes no episode, so a "best" checkpoint is not chosen by evaluation | Code | Defect | Run | [train.py:285–294](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L285-L294) | — |
| <a id="R-06"></a>R-06 | APPO's `lambda_` has no effect | Code | Defect | Read | [train.py:186–189](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L186-L189)<br>[train.py:229–235](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L229-L235) | [rl](rl.md#r-06-appos-lambda_-has-no-effect) |

#### Inference, evaluation and tests

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-52"></a>I-52 | No working test gate: the original suite collects 35 tests, of which 15 pass, 3 fail and 17 error; the tests contain no assertions, fixtures are missing and signatures have drifted | Code | Defect | Run | [test_battery.py:13–62](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/tests/test_battery.py#L13-L62)<br>[test_checkpoint.py](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/tests/test_checkpoint.py) | [rl](rl.md#i-52-the-trainers-test-checks-that-it-runs-not-that-it-learns) |
| <a id="I-61"></a>I-61 | Standalone inference samples and clips actions itself instead of using RLlib's action path, and reads `info` wrongly | Code | Defect | Read | [inference.py:159–174](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/inference.py#L159-L174)<br>[inference.py:229–232](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/inference.py#L229-L232)<br>[lem.py:486](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L486) | [rl](rl.md#i-61-standalone-inference-does-not-act-like-training) |
| <a id="I-64"></a>I-64 | No run manifests, non-learning baselines or multi-seed statistics | Code | Deviation | Read | [train.py:439](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L439)<br>[train.py:391](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L391) | [rl](rl.md#i-64-no-baselines-no-seeds-no-record-of-a-run) |
| <a id="I-72"></a>I-72 | [P2] protocol: one fixed seed, evaluation on the training scenario, ranking by shaped reward | Paper | Decision | Judgment | [train.py:285–293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L285-L293) | [rl](rl.md#i-72-p2s-evaluation-protocol-cannot-show-generalisation-or-variance) |

### D. Experiments, data and repository

#### Experiments, data and repository

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="I-51"></a>I-51 | The Case 6 profile-to-agent mapping is unpublished | Paper | Decision | Judgment | [case6_implicit_cooperation.ipynb](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/notebooks/case6_implicit_cooperation.ipynb) | — |
| <a id="I-63"></a>I-63 | The saved env config cannot reconstruct the scenario (seeds, profile sources, rounding) | Code | Deviation | Read | [io.py:111](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/io.py#L111)<br>[io.py:145–146](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/io.py#L145-L146)<br>[io.py:55](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/io.py#L55) | — |
| <a id="I-65"></a>I-65 | `cooperation/metrics` reports welfare, grid and coordination concepts without the required inputs | Code | Defect | Judgment | [market_analytics.py:123–136](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/analytics/market_analytics.py#L123-L136) | — |
| <a id="I-67"></a>I-67 | README, notebooks and examples describe a different repository state: the examples use the author's absolute paths and a checkpoint that a fresh clone does not have, ignore the bundled data and step before reset, and `zero_to_hero.ipynb` fails against the current API | Code | Deviation | Judgment | [README.md](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/README.md)<br>[getting_started.ipynb](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/examples/getting_started.ipynb)<br>[zero_to_hero.ipynb](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/examples/zero_to_hero.ipynb) | — |
| <a id="I-80"></a>I-80 | [P2] evaluation metric `B_index` is undefined in the paper and absent from the code | Paper | Decision | Judgment | — | — |
| <a id="I-82"></a>I-82 | `src` is not an installable package and imports only from the repository root, so Ray's worker processes fail with `ModuleNotFoundError` unless `PYTHONPATH` is set by hand | Code | Deviation | Run | — | — |

## Problems in the papers' method

Whether the papers' method holds up on its own terms, whatever the code does. None
of these prevents building a working model; each needs a recorded decision,
because the papers cannot settle it.

| Topic | The problem | Issues |
|---|---|---|
| Reward form | [P1] eq. 4 as printed reduces to $R_{\text{base}}$ for normalised factors; [P2] eq. 3 has a different form, and the code a third. The papers' central contribution, the cooperation bonus, has no single definition | [I-42](#I-42) |
| Reward components | The parts of $R_{\text{base}}$ are given only as names, weights and ranges; the code is the only specification, and it is partly broken | [I-76](#I-76), [I-43](#I-43), [I-44](#I-44) |
| Cooperation factor | Claimed to lie in [0, 1], but welfare, liquidity, spread and volatility have no stated normalisation | [I-75](#I-75), [I-41](#I-41) |
| Social welfare (eq. 21) | Defined as consumer plus producer surplus but written as $\sum p\,q$, which is turnover | [I-36](#I-36) |
| Imbalance (eq. 24) | Over trades it is 0 by construction (every trade has a buyer and a seller); it only means something over orders or physical positions. $B_{\text{grid}}$ after DSO clearing is 0 for the same reason, so its timing matters | [I-68](#I-68), [I-35](#I-35), [I-23](#I-23) |
| KPI labels | "DER self-consumption" is defined as the peer-to-peer share | [I-69](#I-69) |
| Grid physics | Losses linear in $d\,q$ and unbounded, voltage drop $f\,d$, flows as transport on a graph; called "high-fidelity" | [I-70](#I-70) |
| Grid fees (eq. 8) | $F_{\text{trans}}$ has no formula; no fee factor has a value; the thermal threshold sits below the congestion threshold; the same-zone bonus outweighs every fee | [I-29](#I-29), [I-30](#I-30), [I-74](#I-74), [N-05](#N-05) |
| Battery (eq. 15–16) | No charge or discharge power limit, although the text claims one; eq. 15 ignores efficiency | [I-71](#I-71) |
| Market design | A DSO-preferred sub-stage the paper does not describe; a clearing price that mixes peer prices with the DSO's tariffs; a pricing mechanism used in the case study that §3.3.3 does not list | [I-15](#I-15), [I-16](#I-16), [I-17](#I-17) |
| Reputation (eq. 12) | Weights and decay have no values; fairness and grid contribution have no formulas | [I-38a](#I-38a), [I-38b](#I-38b), [I-38c](#I-38c) |
| Actions | No explicit "submit nothing"; order side and partner are discrete but modelled as continuous numbers | [I-11](#I-11), [I-10](#I-10) |
| Information | Forecasts with 30 % error are specified, but the observation exposes the exact remaining future demand | [I-39](#I-39) |
| Units | USD/MWh in [P1]'s case study, up to 600 "USD/kWh" in [P2]; kWh per implicit 1-hour step | [I-56](#I-56) |
| Paradigms | CTCE is called a theoretical upper bound but is trained by the same approximate learner; [P2] eq. 18 gives CTDE a joint-action critic, which PPO and APPO do not have | [I-60](#I-60), [I-48](#I-48) |
| Comparison | One "mean episode reward" across paradigms whose objectives are a group sum and per-agent returns; the paradigms use different networks | [I-73](#I-73), [R-03](#R-03) |
| Evaluation | One fixed seed, evaluation on the training scenario, ranking by the shaped reward; the budget is given in episodes but counted in iterations; $B_{\text{index}}$ is undefined | [I-72](#I-72), [I-50](#I-50), [I-80](#I-80) |
| Data | The case-study profile-to-agent mapping and scaling are not published | [I-51](#I-51) |

The weak points are **definitions**, not the architecture: a market with a physical
grid layer, KPI-shaped observations and rewards, and three training paradigms
compared is a coherent design worth building on.

## What this means for the published results

The papers' figures cannot be traced to a specific version of the code. **If** they
were produced with the public release:

- **[P1], Case 5 (batteries, zero-intelligence agents).** The case uses the
  bid-ask spread mechanism, which returns the buyer's bid ([I-17](#I-17)), so the
  peer-to-peer prices of Fig. 5 are buyer bids. Selling charged the batteries
  ([I-18](#I-18)), discharge drained less than it delivered ([I-20](#I-20)), and a
  charge reaching the upper limit was refused entirely ([I-19](#I-19)). No money
  moved ([I-27](#I-27), [I-28](#I-28), [I-24](#I-24)). The "imbalance" and
  "coordination score" of Figs. 6–7 measure traded volume ([I-35](#I-35),
  [I-68](#I-68)). The conclusion that batteries stabilise prices is **not
  supported** by this code.
- **[P2], the 3 × 3 MARL experiment.** The reward the agents optimised has
  constant or inactive parts ([I-43](#I-43), [I-44](#I-44)), an unnormalised
  cooperation factor ([I-41](#I-41)) and no terminal penalty ([I-02](#I-02)); the
  observation exposes exact future demand ([I-39](#I-39)) and a profit that is
  always 0 ([I-27](#I-27)). Every CTDE result comes from untrained policies
  ([I-48](#I-48)); the grouped SAC actors never learned from their critics
  ([R-05](#R-05)); CTCE and CTDE trials may have run with NaN losses
  ([R-01](#R-01), [R-02](#R-02), [I-49](#I-49)); APPO's λ search changed nothing
  ([R-06](#R-06)); and the ranking mixes paradigm with network and training
  length on one seed ([R-03](#R-03), [I-60](#I-60), [I-72](#I-72)). [P2]'s
  conclusions about CTDE are **not supported** by this code.

A thesis built on the rebuild is therefore a corrected reimplementation of the
framework the papers describe, not a reproduction of their results.

## Limits of this audit

- `src/analytics/` (the analytics package) and `src/visualization/` were not
  audited line by line; [I-65](#I-65) is a judgment on the analytics as a whole.
- Of the notebooks, only the Case 5 and Case 6 setups and the two examples were
  checked.
- **Read** issues rest on code reading; the RL page lists the tests that would
  confirm its *Read* issues ([rl.md, Not tested yet](rl.md#not-tested-yet)).
- The 48 demonstrations behind the *Demo* evidence were written on an earlier
  branch of this repository and are not yet part of this one.

## Earlier identifiers

Earlier drafts used the IDs of a first fix plan (P0-xx to P3-xx). Each maps to the
issues here:

| Earlier ID | Issues |
|---|---|
| P0-01 | [I-18](#I-18) |
| P0-02 | [I-08](#I-08), [I-11](#I-11) |
| P0-03 | [I-09](#I-09), [I-10](#I-10) |
| P0-04 | [I-12](#I-12), [I-43](#I-43) |
| P0-05 | [I-13](#I-13), [I-17](#I-17) |
| P0-06 | [I-19](#I-19), [I-20](#I-20), [I-71](#I-71) |
| P0-07 | [I-01](#I-01), [I-02](#I-02) |
| P0-08 | [I-05](#I-05), [I-07](#I-07), [I-26](#I-26) |
| P0-09 | [I-48](#I-48) |
| P0-10 | [I-59](#I-59) |
| P0-11 | [I-27](#I-27), [I-28](#I-28), [I-29](#I-29) |
| P0-12 | [I-52](#I-52) |
| P1-01 | [I-14](#I-14), [I-22](#I-22) |
| P1-02 | [I-32](#I-32), [I-55](#I-55) |
| P1-03 | [I-33](#I-33) |
| P1-04 | [I-57](#I-57), [I-70](#I-70) |
| P1-05 | [I-54](#I-54) |
| P1-06 | [I-41](#I-41), [I-45](#I-45), [I-47](#I-47), [I-75](#I-75) |
| P1-07 | [I-16](#I-16), [I-35](#I-35), [I-36](#I-36), [I-69](#I-69) |
| P1-08 | [I-65](#I-65) |
| P1-09 | [I-39](#I-39), [I-58](#I-58) |
| P1-10 | [I-38a](#I-38a) |
| P1-11 | [I-56](#I-56) |
| P1-12 | [I-60](#I-60), [I-73](#I-73) |
| P1-13 | [I-15](#I-15), [I-16](#I-16) |
| P2-01 | [I-03](#I-03), [I-72](#I-72) |
| P2-02 | [I-61](#I-61) |
| P2-03 | [I-06](#I-06) |
| P2-04 | [I-63](#I-63) |
| P2-05 | [I-62](#I-62) |
| P2-06 | [I-64](#I-64) |
| P3-01 | [I-66](#I-66) |
| P3-02 | [I-53](#I-53) |
| P3-03 | [I-67](#I-67) |

The earlier repository fix history (RF-xx) maps as follows: RF-002 → [I-52](#I-52);
RF-007, RF-008 → [I-62](#I-62); RF-009 → [I-82](#I-82); RF-011 → [I-81](#I-81);
RF-003 to RF-006, RF-012, RF-013, RF-016 → [I-67](#I-67); RF-014 → [R-04](#R-04).
RF-001, RF-010 and RF-015 concern the local environment (a conda file, a Windows
PyTorch build, an ignore rule), not the original code, and are not issues here.
