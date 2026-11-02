# Results

What a run saves, what the Studio shows of it, and what is still missing. One of the
thesis objectives is to "determine the form in which the tool must present and output
the simulation results" (the task sheet); this section is that form, built by the
[results plan](../../plan/results.md).

This page is the overview. Each tab of the Studio's Results page has its own page, with
every panel and every saved number, and what the tab lacks:

| Tab | Question | Page |
|---|---|---|
| Validation | How good is each version on the test days? | [Validation](validation.md) |
| Learning | Did it learn? | [Learning](learning.md) |
| Market | What did the market do? | [Market](market.md) |
| Grid | What did the grid do? | [Grid](grid.md) |

[Saved files](files.md) lists every file with a template of its contents.

The notebook [`results.ipynb`](../../../notebooks/runner/results.ipynb) reads the same
tables through [`core/runner/results.py`](../../../core/runner/results.py). Above the
tabs, the run table lists each run's target, experiment, name, algorithm, paradigm, seed,
variant and state, and the held-out team money of the trained policy and the two
baselines. The tabs share what is selected: picking a row in Validation opens it in
Market or Grid.

## When results are made

A run produces numbers in three phases, and they answer different questions.

| Phase | When | Days played | Question |
|---|---|---|---|
| Training | Every iteration | Training days, sampled with exploration | Is the learner working? |
| Periodic evaluation | `eval_points` times, and at step 0 | Training days, on seeds training did not use | Is the policy improving? |
| Held-out evaluation | Once, after training | Every test day in order; batteries and reputations carry from day to day | How good is the final policy? |

The baselines are `zero` (no orders) and `net_position` (the market's own bidding rule).
The periodic evaluation plays them once, at step 0, with `random`, and the trained
policy at every point; the held-out evaluation plays all but `random` on every test day.

The results the thesis compares come from the held-out evaluation. Its reward is in each
reward's own units, so **money (`bill`), not `team_return`, is the measure that compares
across rewards** (RP-7a): on [`obs_reward`](#an-example-obs_reward), the trained policies
with the highest return were the ones that lost the most money.

## What is saved

Everything is in `runs/<experiment>/<run>/`, as CSV and JSON. The sizes are from one run
with 13 participants, hourly steps, 240,000 environment steps and 14 test days.

| File | One row per | Holds | Size | Explained in |
|---|---|---|---|---|
| `experiment.json`, `scenario.json` | | The arm as started | 11 KB | [Validation](validation.md) |
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
