# Validation

**How good is each version on the test days?** The tab that opens first. Any ticked runs
can be compared, whatever they differ in; the tab says what differs.

Source: `day_indicators` in [`results.py`](../../../core/runner/results.py) and
[`indicators.py`](../../../core/runner/indicators.py), from the held-out tables; drawn
by [`validation.py`](../../../studio/pages/results/validation.py).

## Structure

```text
Validation
├── These runs differ in: ...
├── 1  Overview           a row per · show · difference from
│      the table of headline indicators, with the baselines under it
│      look closer at: a row, then Market or Grid
├── 2  On the test days   the gain per day, as boxes
└── 3  One run's settings
```

## Panels

**1 Overview.** A row per what *A row per* picks: the run, or any setting that differs,
with seeds pooled. Each run is the mean over its test days. A seed is the mean of its
runs, and a cell the mean over seeds, with each seed's value in brackets, or from 5 seeds
a 95% bootstrap interval in square brackets.

| Column | What it is |
|---|---|
| Team money | The participants' `bill` summed, EUR per day; positive is earned |
| Gain over net position | Team money minus the run's own `net_position`, same day |
| Stored change | Energy left in the batteries against the start of the day, kWh. Money alone favours draining them, so it stands next to it |
| Better off than zero | Participants whose `bill` beats `zero` |
| Peer energy | `p2p_kwh` |
| Trading ratio | Energy bought and sold over what participants needed to get or get rid of; above 1 is energy traded back and forth |
| Unmet demand | `deferred_demand_kwh` |
| Highest line loading | Worst step of the day, % |
| Hours over a limit | Hours with a voltage or loading limit broken |

*Show* picks the values, or each value minus the run's own `net_position` or `zero` on
the same day: that makes different scenarios or price sets comparable, because each run
plays its own baselines.

*Difference from* picks a row: every cell becomes that row's difference from it. *Paired*
says how: with the same seeds, days, prices and network, a seed's mean difference over the
days both have, with the spread over seeds; otherwise the difference of the two means,
which keeps the variation between days. `difference(by=..., reference=...)` in the
notebook does the same per factor, inside each combination of the other settings.

Under the table there is one row per baseline and per what it was played on: prices,
peer charge, network, grid method, test days. A warning names steps that did not
converge, because on them loading and limits count nothing and read low.

*Look closer at* picks a row, and *Market* or *Grid* opens that tab on its median seed by
team money.

**2 On the test days.** Per run, a box over the test days of `gain_zero` and
`gain_net_position`: the money above each baseline on the same day.

**3 One run's settings.** For a picked run: what it is, its days, the code, and its
environment, training and model settings.

## Saved, not on this tab

| Column | What it is | Where |
|---|---|---|
| `team_return_mean`, `team_return_std`, `return/<participant>` of `heldout.csv` | Return per policy | Nowhere: it does not compare across rewards |
| `final`, `spaces`, `agents`, `env_contract`, `settings_effective`, `model_effective`, `versions`, `eval_seeds` in `run.json` | The final evaluation, the spaces, every effective setting, library versions | Nowhere |

The other indicators are per test day on Market and Grid; `gain_zero` and
`reachable_share` are in `day_indicators`, for the notebook.

## Missing

| Number | Why it matters | Source |
|---|---|---|
| The best rule of the margin sweep | MP-6b's reference for "good" | New |
| The reachable gain with the peer charge taken off | `reachable_share` assumes netting is free, so it reads low at a peer charge above 0 | The rate is in the scenario, not in the tables |
