# Grid-method comparison

> **Status: proposal.** Nothing on this page is in the code yet unless it is marked
> *built*. It describes how the comparison would be implemented, so the design can
> be assessed before it is built.

The thesis compares two ways of letting the grid into the market, on the **same
SimBench network** with the same participants, profiles, days, seeds and learning
setup:

- **Arm A, power flow** (built): the pandapower AC power flow of what the
  participants physically did, as `marlem-v1` runs it now.
- **Arm B, graph model**: Salazar's grid method ([P1] §3.5,
  [methodology §6](../marlem/methodology.md#6-grid-p1-35)) placed on the SimBench
  network: flows of the trades along shortest paths, capacity spread over the lines,
  linear losses and voltage drop.

The question is which grid dynamics each method produces once the agents learn
under it. What is compared is the method, not the published numbers.

## The two arms

![Grid-method experiment: where each input of the DSO fees comes from](diagrams/grid-methods.svg)

[Open the diagram full size](diagrams/grid-methods.svg). Its source is
[`diagrams/grid_methods.drawio`](diagrams/grid_methods.drawio).

Read it from the top. Both arms play the same market step. The grid reaches the
agents only through the **DSO fees** in their reward: the observation holds no grid
state ([market_env.py](../../core/env/market_env.py#L8-L24)). Most fee inputs are
the same in both arms (middle column). Two come from the arm: the line loading
$C_t$ of the trade's path, which sets the congestion and thermal fees, and the
voltage drop $V_\text{drop}$, which sets the voltage fee.

| Fee input | Arm A: power flow | Arm B: graph model |
|---|---|---|
| Line loading $C_t$ (eq. 8a, 8g) | measured loading of the path's lines | trade flows on the path ÷ edge capacity (eq. 19) |
| Voltage drop $V_\text{drop}$ (eq. 8c) | measured $\lvert V_a - V_b \rvert$ (proposed) | $f_\text{volt}\, d_{ij}$ (eq. 8f) |
| Distance $d_{ij}$, path, zones | shared: SimBench lines | shared |
| Loss $l_{ij} = \kappa\, d_{ij}\, q_{ij}$ (eq. 18) | shared | shared |
| Imbalance (eq. 8b, 8h) | shared: the market's balance | shared |

The difference in incentives: in arm A a trade's fee follows the state of the
network at that time and place, which a trade between peers does not change (only a
battery shifting energy does). In arm B the fee follows the trades themselves: more
and longer trades over a line raise its fee, while everything that is not traded
(the network's own loads, untraded imports) is invisible.

## Implementation

1. **Graph model** in `core/grid/` behind the existing
   [`GridModel`](../../core/grid/contract.py#L271) protocol, reusing the topology,
   paths and zones of [`SimBenchGrid`](../../core/grid/powerflow.py). Each step it
   builds the edge flows from the step's trades and reports them in the same form
   as the power flow's line loading, so the DSO's fee code does not change.
2. **A scenario setting** `grid.method` (`"powerflow"` or `"graph"`) with the graph
   model's own parameters (capacity rule, total capacity). `LocalEnergyMarket`
   picks the model that sets the fees from it.
3. **Measurement in both arms.** The AC power flow runs in arm B too and its result
   is recorded with the step, next to the graph model's loading, but it sets no
   fee.
4. **One experiment, both arms.** Experiment variants may override scenario fields
   as well as training settings, e.g.
   `"variants": {"ac": {}, "graph": {"scenario": {"grid": {"method": "graph"}}}}`,
   so both arms share seeds and days and appear side by side on the Results page.
5. **Order of work.** Settle the fee-related market points first (M-28, M-31,
   M-32, M-33, M-34, M-41), since the fees are the only route the comparison runs
   through; then compare the two arms with the baseline policies, which ignore
   fees, so any difference in their fees is the method alone; then train.

## Open decisions

| Decision | Options | Proposed |
|---|---|---|
| Edge capacity in arm B | [P1]'s split by inverse line length of a total $C_\text{tot}$ (no value given; the release uses 1e6 kW, which never congests); or each line's real rating | both as variants: [P1]'s split with $C_\text{tot}$ = sum of the line ratings, and the real ratings |
| $V_\text{drop}$ in arm A | keep [P1]'s $f_\text{volt}\, d_{ij}$; or measured $\lvert V_a - V_b\rvert$ along the path | measured; "deviation from 1 pu" would mostly measure the transformer's set voltage |
| Loss factor $\kappa$ | release's 0.03 per km; or calibrated from the AC line losses | same in both arms; value with M-41 |
| Losses in settlement | deduct from the delivered energy ([P1] eq. 18); or record only | record only, in both arms |
| Network | `validate_market` (lightly loaded); or a loaded SimBench network | a loaded network as well, or the arms hardly differ |
| RL scope | full 3 × 3 matrix; or one or two combinations that train reliably | one or two, with 3–5 seeds |

## A first check

A scratch comparison on `validate_market.json` (`1-LV-rural1`, 5 participants, 13
lines), 14 held-out July days with the net-position baseline (1,467 trades, 944
with the DSO), gives a first idea of the size of the differences. Baseline
behaviour only, one small network: an indication, not a result.

| Quantity | [P1]'s stand-in | Measured (AC) |
|---|---|---|
| Line losses over 14 days | 18.7 kWh ($\kappa d q$) | 7.2 kWh (+ 175 kWh in the transformer, which the stand-in ignores) |
| Voltage drop per trade, median | 2.0 % ($f_\text{volt}\, d_{ij}$) | 0.07 % ($\lvert V_a - V_b \rvert$) |
| Path loading $C_t$, mean / max | 0.27 / 0.75 ([P1]'s capacity split); 0.036 / 0.14 (real ratings) | 0.047 / 0.25 |
| Thermal fee, total | 182.6 ([P1]'s split); 0 (real ratings) | 0.22 |

[P1]'s capacity split gives long lines little capacity, so arm B's thermal fee is
about 800 times arm A's; with real ratings the trade flows come close to the
measured loading. The congestion fee (threshold 0.8) never applies in either arm on
this network.

## Editing the diagram

The `.drawio` file is the source. Edit it with the Draw.io Integration extension in
VS Code (or diagrams.net), then export it to the SVG this page shows:

```
python docs_site/export_drawio.py
```
