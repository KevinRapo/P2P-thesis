# Current settings and limitations

> **Draft (17 Nov 2026).** What the tool does by default today, which of those
> defaults are still to be confirmed before the thesis's final runs, and what the
> model knowingly leaves out. The questions themselves, open or decided, are in
> [open items](../temp/open.md) and the reasons for the larger decisions in the
> [decision log](../temp/decisions.md); this page states the result. When a
> default changes or an item is decided, update the row here.

Every row has a **status**:

- **Fixed**: decided; the reason is in the decision log.
- **Default**: what runs today; to be confirmed before the final runs. Keeping it is a
  valid decision, but it must be made and recorded.
- **Required**: there is no default; a run that needs it must state it.

## The default configuration

### Scenario and network

The thesis scenario is [`thesis_rural1.json`](../../config/scenarios/thesis_rural1.json).

| Setting | Now | Status | ID |
|---|---|---|---|
| Network | SimBench `1-LV-rural1--2-sw`, 13 participants (8 with PV, 5 with a battery), no background | Fixed | |
| Step | 1 h, 24 steps a day | Default | MP-0a |
| PV scale | 1.0 in the scenario; the development runs used ×1.5, the thesis text proposes ×1.25 (not yet run) | Default | MP-0a, MP-4i |
| Batteries | 100.5 kWh, 50.2 kW, 10-90 % state of charge, 95 % efficiencies, start at 50 % | Fixed | MP-0a |
| Tariffs | `de_2024`: utility = spot + 0.3163 EUR/kWh, feed-in = max(spot − 0.004, 0), hourly ([prices](data/prices.md)) | Fixed | MP-0b |
| Voltage and loading limits (reported) | 0.95-1.05 pu, 100 % | Fixed | |

### Market

| Setting | Now | Status | ID |
|---|---|---|---|
| Peer price | Average of bid and ask ([P1] eq. 9) | Fixed | M-13, M-14 |
| Order prices | Whole cents; no bounds of the market's own: the agents and the rule price inside the tariff band | Fixed | MP-2b, MP-2e |
| Minimum order | 0.001 kWh | Fixed | MP-2g |
| Untraded energy | Settled with the DSO at the tariff and charged a DSO trade's fees | Fixed | MP-1e, MP-1f |
| Reputation | Weights 0.3 / 0.2 / 0.5, start 0.5 every day, hourly decay 0.8 | Default | MP-5b, MP-5c |

### Fees and losses

| Setting | Now | Status | ID |
|---|---|---|---|
| Fee form | Not saturating: congestion $f \cdot \max(C_t - 0.8, 0) \cdot qp$ with $C_t$ the loading ratio, uncapped; voltage $\max \lvert V - V_\text{slack}\rvert \cdot qp$, uncapped; no thermal part | Fixed | MP-4f |
| Fee factors | Congestion 2.0 (40 % of the value at rated loading), threshold 0.8; zone bonus 0.15 (never below a zero fee) | Default | MP-4f, MP-4n |
| Imbalance fee | Off (on hold) | Default | MP-4m |
| Peer charge | 0 | Default | MP-4h |
| Losses | Measured, shared by BCDLA, charged at the utility price; no-load loss to the DSO | Fixed | MP-4j, MP-4k |

### Environment

| Setting | Now | Status | ID |
|---|---|---|---|
| Episode | One day; batteries and reputation start fresh | Default | MP-1c |
| Stored energy at midnight | Worth nothing | Default | MP-1c |
| No order | Quantity share below 0.05 | Default | RP-1a |
| Action | Full mixed action: side, partner, quantity, price | Default | RP-5a |
| Observation | `paper` (42 signals + reputations); `pruned` (22) as an option | Default | RP-1i |
| Reward | `bill`, divided by $p_\text{utility} \cdot E$; `salazar` as an option | Default | RP-1d |
| Grid capacity $C$ of the `salazar` reward | None | Required | RP-1g |
| KPIs (observation and the `salazar` reward) | The day so far; raw values; definitions as in the code | Default | E-08, E-09, E-10, E-11, E-12, E-13, MP-6a |
| Discount γ | 0.99 | Default | RP-1j |

### Learning

| Setting | Now | Status | ID |
|---|---|---|---|
| Algorithm | RLlib PPO, all three paradigms | Fixed | |
| Networks | 2 × 256 tanh, actor and critic separate, same in every paradigm | Fixed | L-04 |
| PPO | lr 3e-4, batch 4000, minibatch 500, 10 epochs, clip 0.2, entropy 0.01, grad clip 0.5, λ 0.95 | Default | RP-6b |
| CTCE | Entropy coefficient divided by N; one joint ratio | Default | RP-3a, RP-3g, RP-8a |
| CTDE critic | Reads its own and all others' observations | Default | L-01, RP-3f |
| Budget | 480k environment steps (development runs) | Default | |

### Evaluation

| Setting | Now | Status | ID |
|---|---|---|---|
| Training days | All of 2016 except the test weeks | Default | RP-7c |
| Test weeks | 11-17 Jan, 11-17 Apr, 11-17 Jul, 10-16 Oct 2016; now validation data, as settings were chosen on them | Default | RP-7c, L-17 |
| Within a test week | Batteries and reputation carry from day to day (training resets them daily) | Default | MP-1c, L-17 |
| Seeds | 2-3 in development runs; five planned | Default | L-17 |
| References | `net_position` (played), `non_p2p` and `ceiling` (calculated) | Fixed | |

## Limitations

What the model knowingly does not do. Each is a choice that stands, unless an
experiment shows it matters.

### Market and grid

- **Reputation** has little time to mean anything within one day (MP-5b); its weights and
  formulas are [P1]'s, untuned (MP-5c).
- **Power flow**: steady state, active power only; one feeder, one year of synthetic profiles.
- **Pricing options**: bid-ask spread and Nash bargaining give the same price as the
  average at factor 0.5 (MP-3d).

### What an agent sees

- **The grid where it is**: nothing local; only the mean loading of all lines and the
  order book's balance (RP-1k).
- **Its peers**: only their reputations, not who has a surplus now (RP-1l).
- **Duplicated and ambiguous signals**: `coordination_score` is 1 − `supply_demand_imbalance`
  (RP-1m); a signal with nothing to measure enters as 0, also a real value (E-07);
  social welfare is turnover, not surplus (E-09).

### Learning

- **Factorised policy**: the partner cannot depend on the side chosen in the same
  step (RP-2b).
- **No value normalisation**; one optimiser and one gradient clip over actor and
  critic (RP-3c, RP-3d).
- **CTCE** is a centralised-controller reference, not an upper bound (L-02).
- **PPO only**; settings chosen on the validation weeks, not tuned exhaustively.

## Known issues in the tool

Not modelling choices: things to fix.

| Issue | Effect | Fix |
|---|---|---|
| The tariff money of untraded energy is added only in `net_bill`, not in the market step | The participants' bills and the DSO's account do not add up; `Participant.profit` and the `mean_profit` signal miss it | Settle it in phase 4 (MP-1g, proposed) |
| `run.json` always says `uncommitted_changes: true` | Provenance cannot tell a clean run from a changed one | Record tracked changes and untracked files separately |
| Evaluation carries state through a week, training resets daily | Learned policies are tested on a horizon they were not trained for | Decide with MP-1c |
| Docs for the days, the tariffs and the PPO settings are out of date | Pages disagree with what the runs use | Update RP-7c, MP-0b, RP-6b |
| Evaluation always unsquashes the action | None with the current settings; wrong for other action bounds | Note it, or follow the training setting |
| Ray occasionally fails to start under low memory | A run shows `failed` or `lost` and is restarted | Fewer runs in parallel (RP-6c) |

## Not in scope now

SAC with the mixed action (RP-9a); a shared central critic or parameter sharing
(RP-9b); market probes M5-M9 (MP-6d); replaying a run from its checkpoint (RP-7m); the
Results page's extra views (RP-7i, RP-7j, RP-7k).
