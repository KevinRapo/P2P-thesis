# Grid methods

> The thesis's main result: the same market, participants and learning, with the
> grid reaching the fees in four ways. **Status: outline.** The settings are
> listed with where each value comes from; the open ones are decided before the
> run.

## Question and expected result

**Question.** When agents learn under each grid method's fees, which method leads
to less physical stress on the real network, and whose fees follow that stress?

**Expected result.** *To be written by the author before the runs.*

## Scenario

| Setting | Value | Why | Status |
|---|---|---|---|
| Network | `1-LV-rural3--2-sw` ([`thesis_rural3_p13.json`](../../../config/scenarios/thesis_rural3_p13.json)) | Large enough to learn reliably; its 30 background buses are what the graph model cannot see ([Market runs](../market-s3.md), [Consistency](#consistency-between-the-arms)) | Open: the network is lightly loaded (below) |
| Participants | 13, on 13 of the 43 prosumer buses; the rest follow their SimBench profiles | | Set |
| Days | Training on June 2016, held-out test on 1-14 July 2016 | Summer: PV, so surplus to trade | Set |
| Prices | `de_2024`, German day-ahead prices of 2024 ([Prices](../../using/data/prices.md)) | Real prices that change every hour | Set |
| Peer charge | 0, [P1]'s market | MP-4h ([Tariffs](../../methodology/market/tariffs.md#the-decision-mp-4h)) | Set for now |
| Grid stress | Line ratings as in SimBench | Over June and July line loading peaks at 38 % (95th percentile 18 %) and the transformer at 40 %: the congestion fee (threshold 0.8) is never charged | Open: a setting that scales the ratings, at 1.0 and a lower level (not built) |

## Arms

| Arm | Line loading in the fees | Voltage drop in the fees | Fees paid |
|---|---|---|---|
| `no_fees` | power flow | measured | no, recorded only: the reference |
| `powerflow` | the path's measured loading | measured $\lvert V_a - V_b \rvert$ | yes |
| `graph` | trade flows ÷ [P1]'s capacity split (eq. 19) | $f_\text{volt}\, d_{ij}$ (eq. 8f) | yes |
| `graph_ratings` | trade flows ÷ each line's rating | $f_\text{volt}\, d_{ij}$ | yes |

How each input reaches the fees: [Grid methods](../../methodology/market/grid-methods.md).

## Parameters

### How the grid is read

The settings that differ between the arms.

| Setting | Now | Where the value comes from | Options | Decision |
|---|---|---|---|---|
| Capacity rule in the graph arms | Both: [P1]'s split by inverse line length, and each line's rating | [P1] eq. 19 for the split; the ratings are ours | | Set: two arms |
| Total capacity $C_\text{tot}$ of the split (`graph_total_kw`) | The sum of the line ratings | [P1] gives no value; the release uses $10^6$ kW, so no line ever congests | Sum of the ratings; the transformer's rating; a value calibrated on the network | Open |
| Voltage drop per distance $f_\text{volt}$ (`voltage_factor`) | 0.15 per km | The release's `voltage_factor` ([dso.py:73](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L73)), which multiplies a distance in the release's own graph units, not km | Keep 0.15; calibrate per km from the measured drops on this network | Open: on LV paths of 0.1–1 km, 0.15 per km gives 0.015–0.15 pu, around and above the cap |
| Voltage-drop cap $V_\text{threshold}$ | 0.05 | [P1] eq. 8c; the release defines 0.05 but caps at 0.2 in the formula ([dso.py:326–328](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L326-L328)) | 0.05; 0.2 | Open |
| Voltage drop in the power-flow arms | Measured $\lvert V_a - V_b \rvert$ between the path's ends | Ours: "deviation from 1 pu" would mostly measure the transformer's set voltage | | Set; its scale differs from $f_\text{volt}\,d_{ij}$ (see above) |
| The transformer in the fees | Not included: the fees read the lines only | | Add the transformer to the path of trades that cross it | Open (not built) |

### The fees

The same in every arm, so they shape all four alike; their values still set how
much the grid matters next to the price. How each one is calculated:
[The market step, 6. Fees](../../methodology/market/step.md#6-fees).

| Setting | Now | Where the value comes from | Decision |
|---|---|---|---|
| Congestion fee: factor, threshold | 0.5, 0.8 | The release's values | Open with the grid stress |
| Thermal fee: threshold, cap | 0.2, 0.3 | The release's values; the threshold sits below the congestion one, so the thermal fee starts at 20 % loading | Open with the grid stress |
| Loss factor $\kappa$ | 0.03 per km | The release's value | Set |
| Losses in settlement | Recorded, not taken off the energy | Ours | Set |
| Transmission fee $F_\text{trans}$ | The trade's loss $l_{ij}$ at the trade price | Ours: [P1] gives no formula | Set |
| Trades with the DSO | The fees of the participant's path to the transformer, like a peer trade, plus the imbalance fee (factor 0.15); no zone bonus | Ours | Set |
| Zones and the same-zone bonus | Zones are the feeders; bonus factor 0.15 | Ours (zones); the release's factor | Set |
| Buyer's share of a peer trade's fee | 0.5 | Ours | Set |

### Learning

| Setting | Now | Decision |
|---|---|---|
| Paradigm | CTDE | Open: after the RL stage |
| Reward, observation | The bill; the paper's 42 signals | Set |
| Budget | 240k environment steps | Open: L-14 |
| Seeds | 5 (0-4) | Open: L-17 |
| Evaluation | 10 points during training, 5 episodes each; every test day once at the end | Set |

## Consistency between the arms

The two methods do not see the same flows, so the arms can differ for reasons
other than how well each method reads the grid. The power flow takes what every
bus physically did; the graph model only adds up this step's trades, each along
the path its fee uses
([`lem.py:659-675`](../../../core/market/lem.py#L659-L675),
[`graph.py:52-66`](../../../core/grid/graph.py#L52-L66)).

| Difference | Power flow | Graph model | Effect on the graph arms | Decision |
|---|---|---|---|---|
| Background load | The 30 background buses' profiles flow on the lines | Not seen | Lower loading; against the real ratings (`graph_ratings`) the fees may never be charged, as the full power flow only reaches 38 % | Open (below) |
| Energy not traded | A participant's net power from what it physically did | Only its trades | Lower loading wherever a participant's net power exceeds what it traded | Open (below) |
| Direction of flows | Opposite flows on a line cancel | Every trade adds its kW as an amount, whatever its direction | Higher loading where trades run both ways on a line, such as a PV sale downstream while a neighbour imports | Keep, as [P1] |
| Trades with the DSO | Part of each bus's net power | Their kW along the participant's path to the transformer, like a peer trade's | None of note: in both methods they count in the loading and pay the fees of that path | Set |
| Scale of the voltage drop | Measured $\lvert V_a - V_b \rvert$ | $f_\text{volt}\, d_{ij}$ | The voltage fee can differ in size alone | Open with $f_\text{volt}$ (Parameters) |
| The transformer | Loaded in the power flow, left out of the fees | Not modelled | None between the arms: both leave it out | Open (Parameters) |

**The level of the graph model's loading.** The first two rows push the graph
model's loading down, the third pushes it up, and the total capacity sets the
level. Left as it is, the comparison risks becoming fees against almost no fees,
which follows from the setup rather than from learning. The options:

- **Keep [P1]'s model as it is** in `graph_ratings`: trades only, against the real
  ratings. What it fails to see is then part of the result.
- **Calibrate $C_\text{tot}$** in `graph`: the total capacity at which the graph
  model's loading matches the measured one at the same level (for example the 95th
  percentile) with the `net_position` rule. The fees then fire about as often in
  both methods, and what differs is where and when. No new code.
- **Background off as a check**: with `grid.background = "off"` both methods see the
  same buses, so what remains between them is the model itself. A check without
  learning, not more trained runs.
- **Give the graph model the background**: each background bus's net power along
  its path to the transformer, as DSO trades are now. Beyond [P1], so an extra arm
  at most.

**Decision.** Open: proposed are the first three together, with the calibration
and the check run before the trained runs.

## What is measured

The power flow runs in every arm, so the physical outcome is measured the same way:

- **the grid:** hours with an overloaded line or transformer, highest and 95th
  percentile loading, voltage violations, line losses, energy through the
  transformer;
- **the market:** bill per participant, energy traded between peers, trade
  distances, fees by component;
- **how well each fee follows the grid,** without learning: the fee's line loading
  against the measured one, trade by trade, with the `net_position` rule.

## Runs and results

[`thesis_grid_methods.json`](../../../config/experiments/thesis_grid_methods.json):
4 arms × 5 seeds = 20 runs, each with 8 environment runners on TalTech
`blackwell1` (10 CPUs, 12 GB, 4 h).

**Results.** To come.
