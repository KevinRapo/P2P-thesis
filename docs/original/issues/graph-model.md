# Why the graph model is not compared

> [P1] models the grid as a graph that carries the trades (§3.5). This version uses
> an AC power flow on SimBench networks instead. Comparing the two grid models was
> considered and dropped. This page explains why, on the thesis network
> `1-LV-rural1--2-sw`.

The decision is recorded as MP-4e in the [decision log](../../temp/decisions.md).
The last version with both models is the tag
[`v2-graph-model`](https://github.com/KevinRapo/P2P-thesis/tree/v2-graph-model).

## The paper's model in short

Each trade adds its quantity to every edge on the shortest path between buyer and
seller. An edge's congestion is that flow divided by its capacity (eq. 19). The
capacity comes from a single total $C$ shared over the edges in inverse proportion
to their length ([methodology §6.2](../methodology.md#62-constraints)):

$$
C_e = C \cdot \frac{1/\ell_e}{\sum_{k} 1/\ell_k}
$$

where $\ell_e$ is the length of edge $e$.

## The capacity split does not fit a real feeder

On a radial feeder, a line's capacity is set by its cable, and the load it carries
is set by its position: the line next to the transformer carries everything
downstream. The split above follows neither. It looks only at length, and real
line lengths vary a lot.

`1-LV-rural1--2-sw` has 13 lines, all the same cable rated 187 kW. Their lengths run
from 2 m to 137 m. Sharing the sum of the ratings (2432 kW) with the paper's rule:

| Line | Length (m) | Lines between it and the transformer | Loads downstream | Rating (kW) | Paper's capacity (kW) |
|---|---:|---:|---:|---:|---:|
| Line 8 | 2 | 1 | 9 | 187 | 832 |
| Line 11 | 3 | 4 | 2 | 187 | 692 |
| Line 7 | 5 | 0 | 12 | 187 | 348 |
| Line 3 | 50 | 0 | 10 | 187 | 36 |
| Line 10 | 132 | 0 | 1 | 187 | 13 |
| Line 9 | 137 | 3 | 4 | 187 | 13 |
| All 13 | 2-137 | | | 187 each | 13-832 |

"Loads downstream" counts the network's load elements (28 in all) beyond the line,
seen from the transformer.

Identical cables get capacities 64 times apart. Line 11, four lines out with two loads beyond it,
gets 692 kW. Line 3, which leaves the transformer and feeds ten loads, gets 36 kW. The congestion fee would then charge trades for crossing a short
line and hardly at all for using a loaded one.

The same holds on the paper's own network. On IEEE-34 with [P2]'s total of 1800 kW,
the split gives 7.5 / 44 / 185 kW per line (min / median / max), while the agents
trade 75-180 kW each. With the release's default total of $10^6$ kW, nothing ever
congests.

## What limits rural1 is outside the graph model

With every participant following the bidding rule over 2016, the network stays
within its limits most of the year. Where it does not, the cause is the transformer
and the voltage, not the lines:

| Over 2016 on `thesis_rural1.json` (bidding rule, 8760 h) | |
|---|---:|
| Hours with a violation | 379 |
| of which overvoltage (max 1.062 pu) | 374 |
| of which transformer overload (max 136 %) | 251 |
| Highest line loading | 40 % |
| Line overloads | 0 |

The graph model has no transformer and no voltage. It also sees only the trades,
not the households' own load and generation or the energy no one trades, and it
adds trades in opposite directions instead of letting them cancel. So it cannot see
the limits that actually bind here.

## Making it comparable would change what is compared

The comparison was meant to show how the paper's grid model differs from a physical
one. To make the graph model meaningful on a SimBench network, it would need:

- the cables' real ratings instead of the length split;
- the background flows of load and generation, not only the trades;
- direction, so that opposite flows cancel;
- a transformer limit, and some voltage estimate.

Each of these is a design choice of this thesis, not of [P1]. With all of them in
place, the comparison would measure those choices against the power flow, not the
paper's method. Without them, it compares the power flow with a model that does not
describe the network.

So the graph model is not compared. The power flow is the only grid the market
reads, and the work goes into what it measures well: losses and their allocation,
and fees from measured loading and voltages. The fee formulas themselves are
[P1]'s and stay ([market step, 5. Grid](../../methodology/market/step.md#5-grid)).
