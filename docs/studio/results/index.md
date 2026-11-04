# Results

The Studio's Results page: what a run saves, what is computed from it, and how the four
tabs show it. One of the thesis objectives is to "determine the form in which the tool
must present and output the simulation results" (the task sheet); this section is that
form, built by the [results plan](../../plan/results.md).

| Page | What it covers |
|---|---|
| This page | The page's layout, when results are made, the references, and which number exists at which time resolution |
| [Metrics](metrics.md) | Every metric once, in five groups: definition, resolution, source, where it is shown |
| [Learning](learning.md), [Validation](validation.md), [Market](market.md), [Grid](grid.md) | One page per tab: each panel, its controls, how it is computed, what it cannot show |
| [Saved files](files.md) | Every file a run leaves, with a real record of each |

The notebook [`results.ipynb`](../../../notebooks/runner/results.ipynb) reads the same
tables through [`core/runner/results.py`](../../../core/runner/results.py).

## The page

```text
Results
├── run table        tick the runs to compare; Live follows running ones
└── tabs             share what is selected (run, day, policy, participant)
    ├── Validation   how good is each version on the test days?     (opens first)
    ├── Learning     did it learn?
    ├── Market       what did the market do?
    └── Grid         what did the grid do?
```

Every chart of values along an axis (the test days, environment steps, a day's steps)
with a *Hover* control shows, under the pointer, either **all series** at that x in one
label, or only **one series**, the nearest: with many runs the full label gets long
([`SeriesChart.hover_select`](../../../studio/components/charts.py)).

The run table lists each run's target, experiment, name, algorithm, paradigm, seed,
variant, state and start (click a header to sort), and the held-out team money of the
trained policy and the two baselines. Picking a row in Validation and pressing *Market*
or *Grid* opens that tab on it.

## When results are made

A run produces numbers in three phases, and they answer different questions.

| Phase | When | Days played | Question |
|---|---|---|---|
| Training | Every iteration | Training days, sampled with exploration | Is the learner working? |
| Periodic evaluation | `eval_points` times, and at step 0 | Training days, on seeds training did not use | Is the policy improving? |
| Held-out evaluation | Once, after training | Every test day in order; batteries and reputations carry from day to day | How good is the final policy? |

## Baselines and references

Every run is judged against four yardsticks: two **baselines**, policies the evaluation
plays on the same market and test days as the trained one, and two **references**,
computed from the run's tables without playing the market. Only the played ones have
trades, fees, a power flow and market indicators; the references have money only.

| Name | Played or computed | What it does | Role | Shown |
|---|---|---|---|---|
| **`ceiling`** | Computed | One planner with perfect foresight nets everyone's surplus against everyone's deficit and times every battery, the batteries ending at least as full as they started. Zhou et al. (2018) eq. 14, $\text{value}_{\max}$: peer payments cancel inside the community, so no trade appears in it ([`ceiling_days`](../../../core/runner/ceiling.py), [market_ceiling.ipynb](../../../notebooks/market/market_ceiling.ipynb)) | The top of the VTI: 1 | Overview row |
| **`non_p2p`** | Computed | Their conventional paradigm (§3.1, §4.1): every participant on its own with the retailer, its deficit at the utility price and its surplus at the feed-in tariff, its own battery timed with perfect foresight of its own profiles and the tariffs, ending as full as it started; no netting with anyone. A participant without a battery has nothing to choose ([`alone_days`](../../../core/runner/ceiling.py)) | The bottom of the VTI: 0; each participant's own floor in PI and EI | Overview row |
| **`net_position`** | Played | The market's own bidding rule, read from the observation ([`net_position_policy`](../../../core/env/market_env.py)): the battery first takes the surplus or covers the deficit it can, and what is left is ordered: a surplus offered at $p_\text{FiT} + 0.3\,(p_\text{util} - p_\text{FiT})$, a deficit asked for at $p_\text{util} - 0.3\,(p_\text{util} - p_\text{FiT})$, no partner named, no price jitter. Orders that find no peer clear with the DSO at its tariff and pay the grid fees | A simple, sensible way to use the market: what learning has to beat. `gain_net_position` is measured against it, per run, so it makes different scenarios comparable | Overview row; *Show: against own net position* |
| **`zero`** | Played | No orders at all: each battery passively takes its owner's surplus and covers its deficit, and what is left is settled at retail (MP-1e) | The policy of doing nothing in the market. Since MP-1e it is `non_p2p` with passive instead of timed batteries, so the overview leaves it out; it stays the baseline of `gain_zero`, *Gain per test day* and *Per participant* | Not in the overview |

Two details matter when reading them:

- **`net_position` and `zero` move the same energy.** The rule lets the battery act first,
  so its batteries do what `zero`'s do, and its orders only trade what the batteries leave;
  trades move no energy in this market. Their grid and technical indices are therefore
  identical: the rule differs from doing nothing in money only, through the peer prices
  and the DSO's fees.
- **`net_position` is not the market's rule exactly.** The market's own bidding rule for
  non-RL participants ([`rule_based_bid.net_position`](../../../core/market/agent/rule_based_bid.py),
  [Market step](../../full-cycle/market-step.md)) adds a price jitter and a preferred
  partner from the scenario (`bid_margin`, `bid_jitter`, `partner_preference`); the
  baseline keeps the margin, 0.3, and drops both, so it is the same on every run
  ([Config](../../config/reference.md)).

The periodic evaluation plays the baselines once, at step 0, with `random`; the held-out
evaluation plays them on every test day. Older runs also played `random` on the test
days; the results leave it out.

Each reference exists at two horizons. **Over the test period** the batteries carry from
day to day, as the evaluation plays them, starting where it started them. **Per test
day** every day is its own horizon, as in Zhou et al.'s one-day cases: each battery
starts the day at the scenario's initial charge and ends it at least as full
([`day_references`](../../../core/runner/ceiling.py)). The played policies' batteries
carry over between days, so a day's value for them also holds energy moved between days.

The results the thesis compares come from the held-out evaluation. Its reward is in each
reward's own units, so **money (`bill`), not `team_return`, is the measure that compares
across rewards** (RP-7a): on [`obs_reward`](#an-example-obs_reward), the trained policies
with the highest return were the ones that lost the most money.

## Time resolution

Every number comes from the same step tables, so each could be computed per step. Whether
it *means* anything at a resolution depends on the metric:

| Group | Per step | Per test day | Over the test period |
|---|---|---|---|
| Physical: energy, battery, loading, voltage, exchange | native | sums or extremes | sums or extremes |
| Money: team money, gains, fees | native, additive | sum | sum |
| VTI | only as a contribution: the step's gain over `non_p2p` divided by the period's reach; it adds up to the VTI | its own horizon (`vti_day`) | its definition (`vti`) |
| PI, EI | no: judgements about a whole horizon | `pi_day`, `ei_day` | `pi`, `ei` |
| Technical indices (energy balance, peak-to-average, self-sufficiency) | no | as in the paper | `*_period` |
| Salazar's KPIs | as the observation sees them | the day's | not computed |

A ratio cannot be shown per step: the ceiling deliberately loses money in some hours
(charging at midday, when it could export) to earn more in others, so its step value
minus the reference's is often 0 or negative. The Studio shows the headline indices over
the period in Validation's overview and per day in its *On the test days* chart; per step
it shows the physical and money columns of one run's day (*Step by step* on Market and
Grid). An hour-of-day view and a cumulative VTI curve are parked
([open items](../../plan/open.md), RP-7i).

## What is saved

Everything is in `runs/<experiment>/<run>/`, as CSV and JSON. The sizes are from one run
with 13 participants, hourly steps, 240,000 environment steps and 14 test days.

| File | One row per | Holds | Size | Explained in |
|---|---|---|---|---|
| `experiment.json`, `scenario.json` | | The arm as started; `scenario.json` also gives the references their batteries | 11 KB | [Validation](validation.md) |
| `run.json` | | Settings, versions, commit, timings, outcome | 16 KB | [Validation](validation.md) |
| `status.json` | | State, times, host | 0.3 KB | |
| `metrics.csv` | progress report | The learner | 2 MB | [Learning](learning.md) |
| `evaluation.csv` | policy and point | Return, team and per participant | 5 KB | [Validation](validation.md) |
| `evaluation_episodes.csv` | policy, point, episode | Market and grid amounts of the day | 14 KB | [Market](market.md), [Grid](grid.md) |
| `evaluation_agents.csv` | policy, point, episode, participant | The participant's money and energy | 160 KB | [Market](market.md) |
| `heldout.csv` | policy | Return, team and per participant | 1 KB | [Validation](validation.md) |
| `heldout_episodes.csv` | policy, test day | Market and grid amounts of the day | 8 KB | [Market](market.md), [Grid](grid.md) |
| `heldout_agents.csv` | policy, test day, participant | The participant's money and energy | 90 KB | [Market](market.md) |
| `heldout_steps.csv` | policy, test day, step | Market, grid and tariffs at the step | 25 KB per day | [Market](market.md), [Grid](grid.md) |
| `heldout_agent_steps.csv` | policy, test day, step, participant | The participant at the step | 350 KB per day | [Market](market.md) |

`checkpoint/` holds the trained policy and stays on the cluster unless copied; `sync`
leaves it out.

## Three levels

Each number sits on the lowest level that can hold it, and only the first is permanent:

| Level | What it is | Computed | Where |
|---|---|---|---|
| 1 Saved | Raw tables of one run | During the run | [Saved files](files.md) |
| 2 Indicator | One number per run, policy and test day | When read | [`indicators.py`](../../../core/runner/indicators.py) |
| 3 Comparison | Any runs side by side, or their difference | When read | [`indicators.py`](../../../core/runner/indicators.py), [Validation](validation.md) |

So an indicator added later still applies to runs already made, if the saved tables hold
what it needs. That is why every test day is kept step by step, for every policy: it adds
no time, since the evaluation holds every step in memory anyway, and a run cannot get
step tables afterwards. It costs about 5 MB per run at 13 participants and hourly steps.

## An example: `obs_reward`

The first full experiment shows why this is needed. On its test days, CTDE:

| Version | Team money per day, EUR | `team_return` | Peer kWh | Bought from DSO, kWh |
|---|---|---|---|---|
| `zero` | −13.52 | | 0 | 0 |
| `net_position` | −4.63 | | 8.6 | 25.0 |
| Bill reward, full observation | +0.77 | 0.09 | 41.2 | 5.9 |
| Salazar reward, full observation | −19.44 | 3175 | 82.5 | 59.8 |

On return alone, the Salazar version looks like a success; the Validation tab now leads
with money, so it does not.
