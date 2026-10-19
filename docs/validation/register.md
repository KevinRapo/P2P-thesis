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

**IDs.** Each issue has the letter of its part and a number in reading order:
the issues of a part are numbered through its subsections as they appear in this
register, and the [market](market.md) and [RL](rl.md) pages give their details in
the same order. A new issue takes the next free number of its part.

| IDs | Part |
|---|---|
| M-01 to M-46 | [A. Market layer](#a-market-layer) |
| E-01 to E-22 | [B. Environment and cooperation](#b-environment-and-cooperation) |
| L-01 to L-18 | [C. Learning layer](#c-learning-layer) |
| D-01 to D-06 | [D. Experiments, data and repository](#d-experiments-data-and-repository) |

The IDs used until October 2026 (`I-xx`, `N-xx`, `R-xx`) are listed under
[Earlier identifiers](#earlier-identifiers).

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

- **Batteries run backwards** ([M-16](#M-16), [M-18](#M-18)): selling charges the
  battery.
- **Two pricing mechanisms return the buyer's bid** ([M-13](#M-13),
  [M-14](#M-14)), one of them the mechanism of [P1]'s own case study.
- **No money moves** ([M-22](#M-22), [M-27](#M-27), [M-24](#M-24)): profit, fees
  and the DSO balance stay at zero.
- **The grid is not a power flow** ([M-38](#M-38), [M-37](#M-37), [M-35](#M-35)):
  linear estimates on a disconnected graph whose flows pile up over the day.
- **The reward the agents learn from is partly constant** ([E-15](#E-15),
  [E-16](#E-16), [E-13](#E-13)).
- **CTDE never trains the networks that act** ([L-01](#L-01)), and the paradigms
  are not compared like for like ([L-04](#L-04), [L-02](#L-02), [L-03](#L-03)).

## The register

### A. Market layer

#### The market step

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="M-01"></a>M-01 | Only 23 of 24 periods run: termination is checked after the step increment against `max_steps − 1` | Fidelity | Defect | Demo | [lem.py:433–445](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L433-L445) | [market](market.md#m-01-only-23-of-24-periods-run) |
| <a id="M-02"></a>M-02 | Invalid actions raise `ValueError` instead of being dropped (Alg. 1 `ValidateOrder`) | Fidelity | Deviation | Demo | [lem.py:336–343](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L336-L343) | [market](market.md#m-02-an-invalid-order-stops-the-simulation) |
| <a id="M-03"></a>M-03 | Units and time step are inconsistent (W, kW, kWh, Wh; USD/Wh vs USD/kWh), and Δt is implicit | Paper | Decision | Judgment | [der.py:35](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L35)<br>[matching.py:33–36](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L33-L36) | [market](market.md#m-03-units-and-time-step-are-mixed) |
| <a id="M-04"></a>M-04 | Profiles passed to `DERAgent(...)` are overwritten at `reset()` | Code | Deviation | Demo | [lem.py:281–293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L281-L293)<br>[base.py:40–43](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/base.py#L40-L43)<br>[der.py:119–129](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/der.py#L119-L129) | [market](market.md#m-04-m-05-a-reset-cannot-be-told-which-profiles-to-use) |
| <a id="M-05"></a>M-05 | CSV profiles use a random column and random scale per reset. Procedural G is additive, not eq. 17's multiplicative form | Fidelity | Deviation | Read | [lem.py:281–293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L281-L293)<br>[base.py:40–43](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/base.py#L40-L43)<br>[der.py:119–129](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/der.py#L119-L129) | [market](market.md#m-04-m-05-a-reset-cannot-be-told-which-profiles-to-use) |

#### Orders and feasibility

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="M-06"></a>M-06 | Feasibility clipping does not implement eq. 15: it treats the requested `q` as the need | Fidelity | Defect | Demo | [der.py:184–228](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L184-L228) | [market](market.md#m-06-feasibility-clipping-is-not-eq-15) |
| <a id="M-07"></a>M-07 | `is_buy` is truthy in `adjust_action_for_battery` but `> 0.5` in `step`, so the order is sized for the wrong direction | Fidelity | Defect | Demo | [der.py:196](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L196)<br>[lem.py:358](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L358) | [market](market.md#m-07-an-order-can-be-sized-as-a-buy-and-submitted-as-a-sell) |
| <a id="M-08"></a>M-08 | No "submit nothing" action when `q_min > 0` | Paper | Decision | Demo | [der.py:231–232](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L231-L232) | [market](market.md#m-08-no-way-to-submit-nothing) |
| <a id="M-09"></a>M-09 | Orders are mutated in place, so the reward, KPIs and info see residual quantities (0), not submitted ones | Code | Defect | Demo | [matching.py:347–348](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L347-L348)<br>[dso.py:212–253](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L212-L253)<br>[lem.py:424–425](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L424-L425) | [market](market.md#m-09-clearing-overwrites-the-submitted-orders) |

#### Clearing stages

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="M-10"></a>M-10 | Stage 1 clears DSO-preferred orders with the DSO before any P2P matching | Paper | Decision | Demo | [matching.py:608–623](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L608-L623) | [market](market.md#m-10-dso-preferred-orders-are-cleared-before-the-peer-market) |
| <a id="M-11"></a>M-11 | Rule-based partner selection is a lexicographic sort plus a random top-half pick, not a weighted score | Fidelity | Deviation | Demo | [der.py:154–159](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L154-L159)<br>[lem.py:362–365](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L362-L365) | [market](market.md#m-11-partner-choice-is-a-sort-and-a-random-pick-not-a-weighted-score) |
| <a id="M-12"></a>M-12 | The Stage-2 capacity check uses `max_quantity·N` and the current balance, not grid capacity or the projected trade | Code | Defect | Demo | [matching.py:158](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L158) | [market](market.md#m-12-the-stage-2-capacity-check-can-never-trigger) |

#### Pricing mechanisms

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="M-13"></a>M-13 | `SELLER` pricing returns the buyer's price (positional-argument bug) | Fidelity | Defect | Demo | [mechanism.py:69–84](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/mechanism.py#L69-L84)<br>[matching.py:310–312](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L310-L312) | [market](market.md#m-13-seller-pricing-returns-the-buyers-price) |
| <a id="M-14"></a>M-14 | `BID_ASK_SPREAD` pricing receives `market_price` as `factor`, so it returns the buyer's price. The mechanism is also absent from §3.3.3 | Fidelity | Defect | Demo | [mechanism.py:87–111](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/mechanism.py#L87-L111) | [market](market.md#m-14-bid_ask_spread-returns-the-buyers-price-too) |
| <a id="M-15"></a>M-15 | The clearing price is a VWAP that includes DSO trades | Paper | Decision | Demo | [matching.py:368–385](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L368-L385) | [market](market.md#m-15-the-clearing-price-includes-the-dsos-trades) |

#### Settlement, battery and balances

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="M-16"></a>M-16 | Battery dispatch has the trade term's sign reversed: selling charges the battery | Fidelity | Defect | Demo | [der.py:293–305](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L293-L305)<br>[lem.py:392–401](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L392-L401) | [market](market.md#m-16-selling-charges-the-battery) |
| <a id="M-17"></a>M-17 | A charge is refused entirely if it would reach SoC_max; there is no partial fill | Fidelity | Defect | Demo | [battery.py:95–156](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L95-L156) | [market](market.md#m-17-a-charge-that-would-fill-the-battery-is-refused-entirely) |
| <a id="M-18"></a>M-18 | Discharge efficiency is applied in the wrong direction (`·η` instead of `/η`) | Fidelity | Defect | Demo | [battery.py:158–179](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L158-L179) | [market](market.md#m-18-discharge-efficiency-is-applied-the-wrong-way) |
| <a id="M-19"></a>M-19 | Battery model has no charge/discharge power limit (claimed in the text), and eq. 15 ignores efficiency | Paper | Decision | Judgment | [battery.py:205–214](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L205-L214) | [market](market.md#m-19-no-power-limit-and-eq-15-ignores-efficiency) |
| <a id="M-20"></a>M-20 | No household energy-conservation identity is enforced | Paper | Decision | Judgment | [lem.py:392–411](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L392-L411) | [market](market.md#m-20-no-household-energy-balance) |
| <a id="M-21"></a>M-21 | `agent.balance = sold − bought`, not eq. 13 | Fidelity | Deviation | Demo | [lem.py:440](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L440)<br>[matching.py:426–445](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L426-L445)<br>[reward.py:297](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L297) | [market](market.md#m-21-the-agents-balance-is-its-net-trade-in-the-other-sign-convention) |
| <a id="M-22"></a>M-22 | Agent profit (eq. 14) is never updated | Fidelity | Defect | Demo | [der.py:61](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L61)<br>[observation.py:342](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L342) | [market](market.md#m-22-profit-is-never-updated) |
| <a id="M-23"></a>M-23 | Demand satisfaction ignores battery discharge | Code | Deviation | Demo | [der.py:250–262](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L250-L262) | [market](market.md#m-23-demand-satisfied-ignores-battery-discharge) |

#### DSO: balance and grid fees

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="M-24"></a>M-24 | `dso.balance` changes only on Stage-1 DSO-preferred trades and carries across steps, so it is ≡ 0 by default | Fidelity | Defect | Demo | [matching.py:258–374](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L258-L374) | [market](market.md#m-24-the-dso-balance-stays-at-0) |
| <a id="M-25"></a>M-25 | The B_DSO sign convention is inconsistent between `match_orders` and `_match_preferred_partners` | Code | Decision | Read | [matching.py:626–633](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L626-L633) | [market](market.md#m-25-two-opposite-sign-conventions-for-the-dso-balance) |
| <a id="M-26"></a>M-26 | `B_grid` (eq. 20) is never computed. The "grid balance" observation is `dso.balance` | Fidelity | Defect | Demo | [lem.py:472](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L472)<br>[observation.py:285](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L285) | [market](market.md#m-26-the-market-balance-b_textgrid-is-never-computed) |
| <a id="M-27"></a>M-27 | Grid fees are computed but never charged to anyone | Fidelity | Defect | Demo | [dso.py:342–345](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L342-L345)<br>[matching.py:319–332](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L319-L332) | [market](market.md#m-27-grid-fees-are-computed-but-never-charged) |
| <a id="M-28"></a>M-28 | `F_trans` has no formula in the paper; the code uses 0 | Paper | Decision | Judgment | [dso.py:293–314](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L293-L314) | [market](market.md#m-28-f_texttrans-has-no-formula-and-the-code-uses-0) |
| <a id="M-29"></a>M-29 | `F_volt` and `F_thermal` caps (0.2, 0.3) differ from or are undefined in the paper | Fidelity | Deviation | Read | [dso.py:326–333](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L326-L333) | [market](market.md#m-29-f_textvolt-is-gated-by-its-threshold-and-capped-at-02) |
| <a id="M-30"></a>M-30 | `F_imb` is effectively always 0 | Fidelity | Deviation | Read | [dso.py:336–339](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L336-L339)<br>[dso.py:411–442](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L411-L442)<br>[dso.py:219–226](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L219-L226) | [market](market.md#m-30-the-imbalance-fee-can-never-apply) |
| <a id="M-31"></a>M-31 | DSO fallback skips grid feasibility (zero distance, loss and fee), and `validate_grid_constraints` ignores direction | Code | Deviation | Demo | [dso.py:219–226](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L219-L226) | [market](market.md#m-31-dso-trades-skip-the-grid-and-the-grid-check-ignores-direction) |
| <a id="M-32"></a>M-32 | Thermal-fee threshold (20 %) sits below the congestion threshold (80 %) | Paper | Deviation | Judgment | [dso.py:65–67](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L65-L67) | [market](market.md#m-32-the-thermal-fee-starts-far-below-the-congestion-fee) |
| <a id="M-33"></a>M-33 | The same-zone bonus outweighs every grid fee | Paper | Decision | Read | [dso.py:317–319](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L317-L319) | [market](market.md#m-33-the-same-zone-bonus-outweighs-every-fee) |
| <a id="M-34"></a>M-34 | Zones are defined only for the paper's graph topologies | Paper | Decision | Read | [dso.py:317](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L317) | [market](market.md#m-34-zones-exist-only-for-the-papers-graphs) |

#### Grid model used by the market

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="M-35"></a>M-35 | Edge flows start random and accumulate over the episode instead of being per period | Fidelity | Defect | Demo | [network.py:84–85](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L84-L85) | [market](market.md#m-35-edge-flows-start-random-and-pile-up-all-episode) |
| <a id="M-36"></a>M-36 | Only Stage-1 trades update edge flows | Fidelity | Defect | Demo | [matching.py:569–577](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L569-L577)<br>[matching.py:325–332](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L325-L332) | [market](market.md#m-36-only-stage-1-trades-reach-the-grid) |
| <a id="M-37"></a>M-37 | IEEE-34 graph is disconnected (edge 832–888 missing), and the impedance table is unused | Fidelity | Defect | Demo | [config.py:29–39](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/config.py#L29-L39) | [market](market.md#m-37-the-ieee-34-graph-is-disconnected) |
| <a id="M-38"></a>M-38 | Grid physics scope: linear unbounded losses, `V_drop = f·d`, transport flows. "High-fidelity" is an overclaim | Paper | Decision | Demo | [network.py:331–348](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L331-L348)<br>[dso.py:326](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L326) | [market](market.md#m-38-the-grid-physics-is-linear-and-unbounded) |
| <a id="M-39"></a>M-39 | Defensive checks hide bad state (dead capacity check, bare `except`, float-only validators, mutable defaults) | Code | Deviation | Read | [network.py:38](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L38)<br>[base.py:51–57](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/base.py#L51-L57) | [market](market.md#m-39-defensive-code-hides-bad-state) |
| <a id="M-40"></a>M-40 | P2P loss is topped up from the DSO. The buyer's `energy_bought` counts `q + loss` | Fidelity | Deviation | Demo | [matching.py:347](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L347)<br>[lem.py:397–401](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L397-L401) | [market](market.md#m-40-losses-are-topped-up-from-the-dso) |
| <a id="M-41"></a>M-41 | Loss factor κ = 0.03 is hard-coded | Code | Deviation | Read | [network.py:331–334](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L331-L334)<br>[matching.py:316](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L316) | [market](market.md#m-41-the-loss-factor-is-hard-coded) |

#### Reputation

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="M-42"></a>M-42 | Reputation: reliability is always 1, because nothing is ever left unmatched | Fidelity | Defect | Demo | [reputation.py:124–129](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L124-L129)<br>[matching.py:380–382](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L380-L382) | [market](market.md#m-42-reliability-is-always-1) |
| <a id="M-43"></a>M-43 | Reputation: the decay is weighted by the time of day | Fidelity | Deviation | Read | [reputation.py:86–87](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L86-L87)<br>[lem.py:436–441](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L436-L441) | [market](market.md#m-43-the-decay-follows-the-time-of-day) |
| <a id="M-44"></a>M-44 | Reputation: the grid part is always neutral, and fairness mixes in the DSO's trades | Fidelity / Code | Defect | Read | [reputation.py:131–191](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L131-L191) | [market](market.md#m-44-the-grid-part-is-always-neutral-and-fairness-mixes-in-the-dso) |
| <a id="M-45"></a>M-45 | All agents get the same initial reputation (the RNG is reseeded before each draw) | Code | Deviation | Demo | [reputation.py:56–68](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L56-L68)<br>[lem.py:281–283](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L281-L283) | [market](market.md#m-45-every-agent-gets-the-same-random-initial-reputation) |

#### Trade ledger

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="M-46"></a>M-46 | The block hash omits loss and fees, and blocks are forced every step (in-memory PoW, not consensus) | Code | Deviation | Demo | [validation.py:25–34](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/validation.py#L25-L34)<br>[matching.py:395–396](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L395-L396) | [market](market.md#m-46-the-block-hash-leaves-out-losses-and-fees) |

### B. Environment and cooperation

#### Action, observation and reset

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="E-01"></a>E-01 | `is_terminal` is never true, so the terminal unmet-demand penalty never applies | Fidelity | Defect | Demo | [lem.py:430](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L430)<br>[reward.py:207–214](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L207-L214) | — |
| <a id="E-02"></a>E-02 | `reset(seed=None)` falls back to the config seed, so every episode is identical | Code | Deviation | Demo | [lem.py:272–274](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L272-L274) | — |
| <a id="E-03"></a>E-03 | `LocalEnergyMarket.seed()` is shadowed by the `self.seed` attribute | Code | Deviation | Demo | [lem.py:67](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L67)<br>[lem.py:507–514](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L507-L514) | — |
| <a id="E-04"></a>E-04 | β = "no preference" is reachable only at the exact upper bound | Fidelity | Deviation | Demo | [action.py:35–44](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/action.py#L35-L44)<br>[action.py:68–89](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/action.py#L68-L89)<br>[lem.py:359](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L359) | — |
| <a id="E-05"></a>E-05 | Forecast error (`max_error`) is never applied, so the "remaining demand/supply" observations reveal the true future | Fidelity | Defect | Demo | [lem.py:65–66](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L65-L66)<br>[observation.py:338–341](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L338-L341) | — |
| <a id="E-06"></a>E-06 | Observations are raw and unnormalised | Paper | Decision | Demo | [observation.py:333–353](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L333-L353) | — |
| <a id="E-07"></a>E-07 | The reset observation hard-codes G, D, remaining energy and KPIs to 0 | Code | Deviation | Demo | [observation.py:195–257](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L195-L257) | — |

#### KPIs

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="E-08"></a>E-08 | "Supply-demand imbalance" is volume/C, not `\\|Σbuy − Σsell\\|/C`. The coordination score inherits this | Fidelity | Defect | Demo | [implicit_cooperation.py:122–123](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L122-L123)<br>[implicit_cooperation.py:141–142](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L141-L142) | — |
| <a id="E-09"></a>E-09 | Social welfare is turnover `Σ p·q`, not surplus | Paper | Decision | Demo | [implicit_cooperation.py:93](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L93) | — |
| <a id="E-10"></a>E-10 | Price volatility is computed over the whole episode, not a window | Fidelity | Deviation | Demo | [implicit_cooperation.py:104–105](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L104-L105) | — |
| <a id="E-11"></a>E-11 | Imbalance (eq. 24) over trades is ≡ 0 by construction. Needs a definition over orders or physical net positions, and a timing (before or after DSO clearing) for `B_grid` | Paper | Decision | Judgment | [implicit_cooperation.py:122–123](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L122-L123) | — |
| <a id="E-12"></a>E-12 | "DER self-consumption" is defined as P2P share; the label does not match the quantity | Paper | Deviation | Judgment | [implicit_cooperation.py:188](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L188) | — |

#### Reward

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="E-13"></a>E-13 | `f_coop` is not in [0, 1] (≈ 1811) | Fidelity | Defect | Demo | [reward.py:170–192](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L170-L192) | — |
| <a id="E-14"></a>E-14 | The cooperation-boost form differs across [P1] eq. 4, the code and [P2] eq. 3 | Paper | Decision | Demo | [reward.py:218–221](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L218-L221) | — |
| <a id="E-15"></a>E-15 | `r_res ≡ −1.5` and `r_trade ≡ 0` (caused by M-09) | Code | Defect | Demo | [reward.py:406–412](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L406-L412)<br>[reward.py:248–249](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L248-L249) | — |
| <a id="E-16"></a>E-16 | `r_grid`, `γ_DSO` and the grid part of `f_contrib` are inactive (caused by M-24) | Fidelity | Defect | Read | [reward.py:202](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L202)<br>[reward.py:253–309](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L253-L309)<br>[reward.py:472–484](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L472-L484) | — |
| <a id="E-17"></a>E-17 | `_w_local` is overwritten 0.7 → 0.3, so `r_trade = 0.3ρ_local + 0.3ρ_dso` (the paper prints 0.3/0.3) | Code | Deviation | Demo | [reward.py:79](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L79)<br>[reward.py:93](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L93) | — |
| <a id="E-18"></a>E-18 | The unmet-demand penalty uses `p_dso`, not the paper's `p_no_trades = 5` | Fidelity | Deviation | Read | [reward.py:207–214](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L207-L214)<br>[reward.py:226](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L226) | — |
| <a id="E-19"></a>E-19 | The no-trade guard returns a fixed −4.46 before any other term | Paper | Decision | Demo | [reward.py:135–136](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L135-L136) | — |
| <a id="E-20"></a>E-20 | `f_coop` has no normalisation ranges for its unbounded KPIs, so the [0, 1] claim is unsupported | Paper | Decision | Judgment | [reward.py:170–192](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L170-L192)<br>[implicit_cooperation.py:93](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/coordination/implicit_cooperation.py#L93) | — |
| <a id="E-21"></a>E-21 | `R_base` components have no formulas in the paper; the code is the only specification | Paper | Decision | Judgment | [reward.py:148–166](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L148-L166) | — |
| <a id="E-22"></a>E-22 | `f_contrib` grid term is a heuristic, not [P2]'s marginal `−∂\\|B_grid\\|/∂a_i` | Fidelity | Deviation | Read | [reward.py:472–484](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L472-L484) | — |

### C. Learning layer

#### Training paradigms

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="L-01"></a>L-01 | CTDE trains a centralized `pi` but acts with per-agent `pi_heads`, which are never trained | Fidelity | Defect | Test | [ctde.py:46–57](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L46-L57)<br>[ctde.py:86–104](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L86-L104)<br>[ctde.py:121–128](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L121-L128) | [rl](rl.md#l-01-ctde-never-trains-the-policies-that-act) |
| <a id="L-02"></a>L-02 | CTCE is a centralized-information baseline, not a true upper bound. The group reward sum scales with N | Paper | Decision | Test | [train.py:676–687](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L676-L687) | [rl](rl.md#l-02-ctce-is-a-centralised-information-baseline-not-an-upper-bound) |
| <a id="L-03"></a>L-03 | Cross-paradigm return comparability: group sum vs per-agent returns | Paper | Decision | Judgment | [train.py:684](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L684) | [rl](rl.md#l-03-returns-of-the-paradigms-are-compared-across-different-scales) |
| <a id="L-04"></a>L-04 | The paradigms train different networks (custom 2 × 128 ReLU in CTCE and CTDE, RLlib's default in DTDE) | Code | Deviation | Read | [train.py:337–341](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L337-L341)<br>[ctce.py:290–306](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L290-L306) | [rl](rl.md#l-04-the-paradigms-train-different-networks) |

#### Grouping the agents

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="L-05"></a>L-05 | Grouped obs/action tuples may be assigned to the wrong agents: insertion order vs sorted keys | Code | Defect | Demo | [train.py:639–640](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L639-L640)<br>[train.py:702–705](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L702-L705) | [rl](rl.md#l-05-grouped-spaces-are-in-name-order-grouped-data-in-environment-order) |

#### Policy networks and loss

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="L-06"></a>L-06 | The CTCE and CTDE action spread has no upper limit, so it can diverge | Code | Defect | Test | [ctce.py:45](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L45)<br>[ctce.py:309–322](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L309-L322)<br>[ctce.py:365](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L365) | [rl](rl.md#l-06-the-ctce-and-ctde-action-spread-has-no-limit) |
| <a id="L-07"></a>L-07 | `kl_coeff = 0` does not switch off the KL term, and a NaN loss goes unnoticed | Code | Defect | Test | [train.py:216–226](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L216-L226) | [rl](rl.md#l-07-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed) |
| <a id="L-08"></a>L-08 | SAC in CTCE and CTDE uses an unsquashed Gaussian | Code | Defect | Read | [ctce.py:358–373](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L358-L373)<br>[train.py:240](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L240) | [rl](rl.md#l-08-sac-in-ctce-and-ctde-uses-an-unsquashed-gaussian) |
| <a id="L-09"></a>L-09 | SAC's actor in CTCE and CTDE gets no gradient from the critic | Code | Defect | Read | [ctce.py:132–146](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L132-L146)<br>[ctde.py:143–157](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L143-L157) | [rl](rl.md#l-09-sacs-actor-in-ctce-and-ctde-gets-no-gradient-from-the-critic) |

#### Trainer and hyperparameters

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="L-10"></a>L-10 | The PBT lr domain [1e-4, 1e-2] excludes the initial 1e-5, and the entropy domain reaches 10 | Code | Deviation | Read | [train.py:178–189](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L178-L189) | [rl](rl.md#l-10-population-based-training-jumps-the-learning-rate-and-reaches-entropy-10) |
| <a id="L-11"></a>L-11 | Training config defects: positive `evaluation_duration` rejected, CPUs double-allocated, PBT always on, no `finally` around `ray.shutdown` | Code | Deviation | Demo | [train.py:116](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L116)<br>[train.py:285–293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L285-L293)<br>[train.py:426–458](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L426-L458) | [rl](rl.md#l-11-training-configuration-defects) |
| <a id="L-12"></a>L-12 | Evaluation is configured with the replay buffer's `StorageUnit.EPISODES` instead of `"episodes"`: each evaluation completes no episode, so a "best" checkpoint is not chosen by evaluation | Code | Defect | Run | [train.py:285–294](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L285-L294) | — |
| <a id="L-13"></a>L-13 | APPO's `lambda_` has no effect | Code | Defect | Read | [train.py:186–189](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L186-L189)<br>[train.py:229–235](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L229-L235) | [rl](rl.md#l-13-appos-lambda_-has-no-effect) |
| <a id="L-14"></a>L-14 | The budget is counted in training iterations, but the paper says "10 000 episodes" | Paper | Decision | Judgment | [train.py:440](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L440) | [rl](rl.md#l-14-the-budget-is-counted-in-iterations-the-paper-in-episodes) |

#### Inference, evaluation and tests

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="L-15"></a>L-15 | Standalone inference samples and clips actions itself instead of using RLlib's action path, and reads `info` wrongly | Code | Defect | Read | [inference.py:159–174](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/inference.py#L159-L174)<br>[inference.py:229–232](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/inference.py#L229-L232)<br>[lem.py:486](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L486) | [rl](rl.md#l-15-standalone-inference-does-not-act-like-training) |
| <a id="L-16"></a>L-16 | No run manifests, non-learning baselines or multi-seed statistics | Code | Deviation | Read | [train.py:439](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L439)<br>[train.py:391](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L391) | [rl](rl.md#l-16-no-baselines-no-seeds-no-record-of-a-run) |
| <a id="L-17"></a>L-17 | [P2] protocol: one fixed seed, evaluation on the training scenario, ranking by shaped reward | Paper | Decision | Judgment | [train.py:285–293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L285-L293) | [rl](rl.md#l-17-p2s-evaluation-protocol-cannot-show-generalisation-or-variance) |
| <a id="L-18"></a>L-18 | No working test gate: the original suite collects 35 tests, of which 15 pass, 3 fail and 17 error; the tests contain no assertions, fixtures are missing and signatures have drifted | Code | Defect | Run | [test_battery.py:13–62](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/tests/test_battery.py#L13-L62)<br>[test_checkpoint.py](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/tests/test_checkpoint.py) | [rl](rl.md#l-18-the-trainers-test-checks-that-it-runs-not-that-it-learns) |

### D. Experiments, data and repository

#### Experiments, data and repository

| ID | Issue | Origin | Type | Evidence | Original code | Details |
|---|---|---|---|---|---|---|
| <a id="D-01"></a>D-01 | The Case 6 profile-to-agent mapping is unpublished | Paper | Decision | Judgment | [case6_implicit_cooperation.ipynb](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/notebooks/case6_implicit_cooperation.ipynb) | — |
| <a id="D-02"></a>D-02 | The saved env config cannot reconstruct the scenario (seeds, profile sources, rounding) | Code | Deviation | Read | [io.py:111](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/io.py#L111)<br>[io.py:145–146](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/io.py#L145-L146)<br>[io.py:55](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/io.py#L55) | — |
| <a id="D-03"></a>D-03 | `cooperation/metrics` reports welfare, grid and coordination concepts without the required inputs | Code | Defect | Judgment | [market_analytics.py:123–136](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/analytics/market_analytics.py#L123-L136) | — |
| <a id="D-04"></a>D-04 | README, notebooks and examples describe a different repository state: the examples use the author's absolute paths and a checkpoint that a fresh clone does not have, ignore the bundled data and step before reset, and `zero_to_hero.ipynb` fails against the current API | Code | Deviation | Judgment | [README.md](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/README.md)<br>[getting_started.ipynb](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/examples/getting_started.ipynb)<br>[zero_to_hero.ipynb](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/examples/zero_to_hero.ipynb) | — |
| <a id="D-05"></a>D-05 | [P2] evaluation metric `B_index` is undefined in the paper and absent from the code | Paper | Decision | Judgment | — | — |
| <a id="D-06"></a>D-06 | `src` is not an installable package and imports only from the repository root, so Ray's worker processes fail with `ModuleNotFoundError` unless `PYTHONPATH` is set by hand | Code | Deviation | Run | — | — |

## Problems in the papers' method

Whether the papers' method holds up on its own terms, whatever the code does. None
of these prevents building a working model; each needs a recorded decision,
because the papers cannot settle it.

| Topic | The problem | Issues |
|---|---|---|
| Reward form | [P1] eq. 4 as printed reduces to $R_{\text{base}}$ for normalised factors; [P2] eq. 3 has a different form, and the code a third. The papers' central contribution, the cooperation bonus, has no single definition | [E-14](#E-14) |
| Reward components | The parts of $R_{\text{base}}$ are given only as names, weights and ranges; the code is the only specification, and it is partly broken | [E-21](#E-21), [E-15](#E-15), [E-16](#E-16) |
| Cooperation factor | Claimed to lie in [0, 1], but welfare, liquidity, spread and volatility have no stated normalisation | [E-20](#E-20), [E-13](#E-13) |
| Social welfare (eq. 21) | Defined as consumer plus producer surplus but written as $\sum p\,q$, which is turnover | [E-09](#E-09) |
| Imbalance (eq. 24) | Over trades it is 0 by construction (every trade has a buyer and a seller); it only means something over orders or physical positions. $B_{\text{grid}}$ after DSO clearing is 0 for the same reason, so its timing matters | [E-11](#E-11), [E-08](#E-08), [M-26](#M-26) |
| KPI labels | "DER self-consumption" is defined as the peer-to-peer share | [E-12](#E-12) |
| Grid physics | Losses linear in $d\,q$ and unbounded, voltage drop $f\,d$, flows as transport on a graph; called "high-fidelity" | [M-38](#M-38) |
| Grid fees (eq. 8) | $F_{\text{trans}}$ has no formula; no fee factor has a value; the thermal threshold sits below the congestion threshold; the same-zone bonus outweighs every fee | [M-28](#M-28), [M-29](#M-29), [M-32](#M-32), [M-33](#M-33) |
| Battery (eq. 15–16) | No charge or discharge power limit, although the text claims one; eq. 15 ignores efficiency | [M-19](#M-19) |
| Market design | A DSO-preferred sub-stage the paper does not describe; a clearing price that mixes peer prices with the DSO's tariffs; a pricing mechanism used in the case study that §3.3.3 does not list | [M-10](#M-10), [M-15](#M-15), [M-14](#M-14) |
| Reputation (eq. 12) | Weights and decay have no values; fairness and grid contribution have no formulas | [M-42](#M-42), [M-43](#M-43), [M-44](#M-44) |
| Actions | No explicit "submit nothing"; order side and partner are discrete but modelled as continuous numbers | [M-08](#M-08), [E-04](#E-04) |
| Information | Forecasts with 30 % error are specified, but the observation exposes the exact remaining future demand | [E-05](#E-05) |
| Units | USD/MWh in [P1]'s case study, up to 600 "USD/kWh" in [P2]; kWh per implicit 1-hour step | [M-03](#M-03) |
| Paradigms | CTCE is called a theoretical upper bound but is trained by the same approximate learner; [P2] eq. 18 gives CTDE a joint-action critic, which PPO and APPO do not have | [L-02](#L-02), [L-01](#L-01) |
| Comparison | One "mean episode reward" across paradigms whose objectives are a group sum and per-agent returns; the paradigms use different networks | [L-03](#L-03), [L-04](#L-04) |
| Evaluation | One fixed seed, evaluation on the training scenario, ranking by the shaped reward; the budget is given in episodes but counted in iterations; $B_{\text{index}}$ is undefined | [L-17](#L-17), [L-14](#L-14), [D-05](#D-05) |
| Data | The case-study profile-to-agent mapping and scaling are not published | [D-01](#D-01) |

The weak points are **definitions**, not the architecture: a market with a physical
grid layer, KPI-shaped observations and rewards, and three training paradigms
compared is a coherent design worth building on.

## What this means for the published results

The papers' figures cannot be traced to a specific version of the code. **If** they
were produced with the public release:

- **[P1], Case 5 (batteries, zero-intelligence agents).** The case uses the
  bid-ask spread mechanism, which returns the buyer's bid ([M-14](#M-14)), so the
  peer-to-peer prices of Fig. 5 are buyer bids. Selling charged the batteries
  ([M-16](#M-16)), discharge drained less than it delivered ([M-18](#M-18)), and a
  charge reaching the upper limit was refused entirely ([M-17](#M-17)). No money
  moved ([M-22](#M-22), [M-27](#M-27), [M-24](#M-24)). The "imbalance" and
  "coordination score" of Figs. 6–7 measure traded volume ([E-08](#E-08),
  [E-11](#E-11)). The conclusion that batteries stabilise prices is **not
  supported** by this code.
- **[P2], the 3 × 3 MARL experiment.** The reward the agents optimised has
  constant or inactive parts ([E-15](#E-15), [E-16](#E-16)), an unnormalised
  cooperation factor ([E-13](#E-13)) and no terminal penalty ([E-01](#E-01)); the
  observation exposes exact future demand ([E-05](#E-05)) and a profit that is
  always 0 ([M-22](#M-22)). Every CTDE result comes from untrained policies
  ([L-01](#L-01)); the grouped SAC actors never learned from their critics
  ([L-09](#L-09)); CTCE and CTDE trials may have run with NaN losses
  ([L-06](#L-06), [L-07](#L-07), [L-10](#L-10)); APPO's λ search changed nothing
  ([L-13](#L-13)); and the ranking mixes paradigm with network and training
  length on one seed ([L-04](#L-04), [L-02](#L-02), [L-17](#L-17)). [P2]'s
  conclusions about CTDE are **not supported** by this code.

A thesis built on the rebuild is therefore a corrected reimplementation of the
framework the papers describe, not a reproduction of their results.

## Limits of this audit

- `src/analytics/` (the analytics package) and `src/visualization/` were not
  audited line by line; [D-03](#D-03) is a judgment on the analytics as a whole.
- Of the notebooks, only the Case 5 and Case 6 setups and the two examples were
  checked.
- **Read** issues rest on code reading; the RL page lists the tests that would
  confirm its *Read* issues ([rl.md, Not tested yet](rl.md#not-tested-yet)).
- The 48 demonstrations behind the *Demo* evidence were written on an earlier
  branch of this repository and are not yet part of this one.

## Earlier identifiers

Until October 2026 the IDs recorded how an issue was found, not where it sits:
I-01 to I-80 came from the audit of the original code against both papers
(September 2026), I-38a to I-38c split I-38 (reputation) into its three
independent parts, I-81 and I-82 came from running the original's examples and
training as shipped (August 2026), N-05 and N-06 from rebuilding the market on
SimBench networks, and R-01 to R-06 from the RL test bench
([rl.md](rl.md#the-test-bench)). Each maps to one issue here:

| Until October 2026 | Now |
|---|---|
| I-01 | [M-01](#M-01) |
| I-02 | [E-01](#E-01) |
| I-03 | [E-02](#E-02) |
| I-04 | [E-03](#E-03) |
| I-05 | [M-04](#M-04) |
| I-06 | [M-05](#M-05) |
| I-07 | [M-45](#M-45) |
| I-08 | [M-06](#M-06) |
| I-09 | [M-07](#M-07) |
| I-10 | [E-04](#E-04) |
| I-11 | [M-08](#M-08) |
| I-12 | [M-09](#M-09) |
| I-13 | [M-13](#M-13) |
| I-14 | [M-40](#M-40) |
| I-15 | [M-10](#M-10) |
| I-16 | [M-15](#M-15) |
| I-17 | [M-14](#M-14) |
| I-18 | [M-16](#M-16) |
| I-19 | [M-17](#M-17) |
| I-20 | [M-18](#M-18) |
| I-21 | [M-23](#M-23) |
| I-22 | [M-20](#M-20) |
| I-23 | [M-26](#M-26) |
| I-24 | [M-24](#M-24) |
| I-25 | [M-25](#M-25) |
| I-26 | [M-21](#M-21) |
| I-27 | [M-22](#M-22) |
| I-28 | [M-27](#M-27) |
| I-29 | [M-28](#M-28) |
| I-30 | [M-29](#M-29) |
| I-31 | [M-30](#M-30) |
| I-32 | [M-36](#M-36) |
| I-33 | [M-35](#M-35) |
| I-34 | [M-41](#M-41) |
| I-35 | [E-08](#E-08) |
| I-36 | [E-09](#E-09) |
| I-37 | [E-10](#E-10) |
| I-38a | [M-42](#M-42) |
| I-38b | [M-43](#M-43) |
| I-38c | [M-44](#M-44) |
| I-39 | [E-05](#E-05) |
| I-40 | [E-06](#E-06) |
| I-41 | [E-13](#E-13) |
| I-42 | [E-14](#E-14) |
| I-43 | [E-15](#E-15) |
| I-44 | [E-16](#E-16) |
| I-45 | [E-17](#E-17) |
| I-46 | [E-18](#E-18) |
| I-47 | [E-19](#E-19) |
| I-48 | [L-01](#L-01) |
| I-49 | [L-10](#L-10) |
| I-50 | [L-14](#L-14) |
| I-51 | [D-01](#D-01) |
| I-52 | [L-18](#L-18) |
| I-53 | [M-39](#M-39) |
| I-54 | [M-31](#M-31) |
| I-55 | [M-12](#M-12) |
| I-56 | [M-03](#M-03) |
| I-57 | [M-37](#M-37) |
| I-58 | [E-07](#E-07) |
| I-59 | [L-05](#L-05) |
| I-60 | [L-02](#L-02) |
| I-61 | [L-15](#L-15) |
| I-62 | [L-11](#L-11) |
| I-63 | [D-02](#D-02) |
| I-64 | [L-16](#L-16) |
| I-65 | [D-03](#D-03) |
| I-66 | [M-46](#M-46) |
| I-67 | [D-04](#D-04) |
| I-68 | [E-11](#E-11) |
| I-69 | [E-12](#E-12) |
| I-70 | [M-38](#M-38) |
| I-71 | [M-19](#M-19) |
| I-72 | [L-17](#L-17) |
| I-73 | [L-03](#L-03) |
| I-74 | [M-32](#M-32) |
| I-75 | [E-20](#E-20) |
| I-76 | [E-21](#E-21) |
| I-77 | [M-11](#M-11) |
| I-78 | [M-02](#M-02) |
| I-79 | [E-22](#E-22) |
| I-80 | [D-05](#D-05) |
| I-81 | [L-12](#L-12) |
| I-82 | [D-06](#D-06) |
| N-05 | [M-33](#M-33) |
| N-06 | [M-34](#M-34) |
| R-01 | [L-06](#L-06) |
| R-02 | [L-07](#L-07) |
| R-03 | [L-04](#L-04) |
| R-04 | [L-08](#L-08) |
| R-05 | [L-09](#L-09) |
| R-06 | [L-13](#L-13) |

Earlier drafts used the IDs of a first fix plan (P0-xx to P3-xx). Each maps to the
issues here:

| Earlier ID | Issues |
|---|---|
| P0-01 | [M-16](#M-16) |
| P0-02 | [M-06](#M-06), [M-08](#M-08) |
| P0-03 | [M-07](#M-07), [E-04](#E-04) |
| P0-04 | [M-09](#M-09), [E-15](#E-15) |
| P0-05 | [M-13](#M-13), [M-14](#M-14) |
| P0-06 | [M-17](#M-17), [M-18](#M-18), [M-19](#M-19) |
| P0-07 | [M-01](#M-01), [E-01](#E-01) |
| P0-08 | [M-04](#M-04), [M-45](#M-45), [M-21](#M-21) |
| P0-09 | [L-01](#L-01) |
| P0-10 | [L-05](#L-05) |
| P0-11 | [M-22](#M-22), [M-27](#M-27), [M-28](#M-28) |
| P0-12 | [L-18](#L-18) |
| P1-01 | [M-40](#M-40), [M-20](#M-20) |
| P1-02 | [M-36](#M-36), [M-12](#M-12) |
| P1-03 | [M-35](#M-35) |
| P1-04 | [M-37](#M-37), [M-38](#M-38) |
| P1-05 | [M-31](#M-31) |
| P1-06 | [E-13](#E-13), [E-17](#E-17), [E-19](#E-19), [E-20](#E-20) |
| P1-07 | [M-15](#M-15), [E-08](#E-08), [E-09](#E-09), [E-12](#E-12) |
| P1-08 | [D-03](#D-03) |
| P1-09 | [E-05](#E-05), [E-07](#E-07) |
| P1-10 | [M-42](#M-42) |
| P1-11 | [M-03](#M-03) |
| P1-12 | [L-02](#L-02), [L-03](#L-03) |
| P1-13 | [M-10](#M-10), [M-15](#M-15) |
| P2-01 | [E-02](#E-02), [L-17](#L-17) |
| P2-02 | [L-15](#L-15) |
| P2-03 | [M-05](#M-05) |
| P2-04 | [D-02](#D-02) |
| P2-05 | [L-11](#L-11) |
| P2-06 | [L-16](#L-16) |
| P3-01 | [M-46](#M-46) |
| P3-02 | [M-39](#M-39) |
| P3-03 | [D-04](#D-04) |

The earlier repository fix history (RF-xx) maps as follows: RF-002 → [L-18](#L-18);
RF-007, RF-008 → [L-11](#L-11); RF-009 → [D-06](#D-06); RF-011 → [L-12](#L-12);
RF-003 to RF-006, RF-012, RF-013, RF-016 → [D-04](#D-04); RF-014 → [L-08](#L-08).
RF-001, RF-010 and RF-015 concern the local environment (a conda file, a Windows
PyTorch build, an ignore rule), not the original code, and are not issues here.
