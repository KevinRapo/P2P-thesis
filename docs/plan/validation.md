# Plan: a Validate section (market probes, market step, RL probes)

> Status: 26 Oct 2026: steps 1-4 done (the Validate group; the RL probes page with
> the Learning tab moved; market probes M1-M4: core, tests, page); M5-M9 and the
> docs (step 5) open. Not in the docs' navigation yet. Goal: one place in the
> Studio to validate the two layers on cases with known answers, with every piece
> of logic in `core/` and the Studio only showing it (AGENTS.md layer rules).

## What exists

| Piece | Where | State |
|---|---|---|
| RL probes 1-10 (8a/8b): environments, exact answers | `core/rl/envs/probes.py` | done |
| RL probe check: presets, variants, training, scoring, `score.csv`/`checks.csv` per run | `core/rl/scripts/probe_check.py`, `probe_ppo.py`, `hpc/probes.slurm` | done |
| Probe descriptions, expected results, results | `docs/rl/probes.md` | done (prose only) |
| Learner metrics of any run (losses, KL, gradient norm, per-part statistics) | `core/runner/results.learner_metrics` | done |
| Learning tab (training curves per run, one action part at a time) | `studio/pages/results.py` | done |
| Step page: one market step played stage by stage | `studio/pages/market/step.py` (nav: Validate → Market, Step tab) | done |
| RL probes page: probe descriptions and a probe run's score (`core/runner/probe_runs.py`, not under `core/rl/`, which loads Ray), the Learning tab moved | `studio/pages/rl_probes.py`, `studio/components/run_table.py` | done |
| Market probes M1-M4: scripted cases with known outcomes, both grid methods | `core/market/probes.py`, `tests/market/test_market_probes.py`, `studio/pages/market/probes.py` | done (M5-M9 open) |

## Target layout in the Studio

Navigation: the "Run" group becomes **"Validate"** with three pages; Results stays
under Experiments for the market experiments.

| Page | Shows | Built on (core) |
|---|---|---|
| **Market probes** (new) | each probe: its setup (participants, profiles, scripted orders), what it should show, the expected values against the market's, PASS/FAIL per check, and its steps played out (trades per stage, prices, battery, balances, fees, reputation) | `core/market/probes.py` (new) |
| **Market step** (the current Step page, moved) | unchanged; the free play of any scenario, one stage at a time | `LocalEnergyMarket` |
| **RL probes** (the Learning tab, moved here) | the runs picked in a run table, as the Learning tab shows them now (training return, the learner's metrics, one action part at a time); for a probe run also its description and checks | `core/runner/results.py`, `core/rl/scripts/probe_check.py` |

## Part 1: RL probes page

Decided 26 Oct: **move the Learning tab** from Results to this page, with the same
run table to pick runs; nothing new to choose (no method selector). For a run
that is a probe run, add what the probe is:

### Core

1. **Probe descriptions as data**, next to each probe (`probes.py`, or the `Probe`
   entry in `probe_check.py`): `tests` (what it isolates), `setup` (observation,
   action, reward), `answer` (the exact answer), `expect` (what a correct learner
   shows, with the known limits: CTCE slow on 4-7 and 9, 8b measured, probe 4's
   overshoot near the bounds), `market` (the market feature it stands for).
   `docs/rl/probes.md` keeps the prose.
2. **A run's probe and checks**: which probe a run is (from its folder name or
   `score.csv`), its `checks.csv` (expected, got, tolerance, ok) and its `score.csv`;
   a small reader in `probe_check.py`.
3. Optional, later: per probe, which learner signals matter (probe 9: the level's
   mean against ±0.5 and its log σ), so the page can draw the target in.

### Studio

1. Move the Learning tab's code (`studio/pages/results.py`) to the new page; its
   figure builders go to `studio/components/` only if Results keeps a copy.
2. For a probe run: a card above its metrics with the description fields, the
   result (PASS/FAIL, worst error / tolerance, or 8b's share) and the checks table.
3. A short summary when several probe runs are picked: probe × paradigm with
   their results (from their `score.csv`), so a whole preset can be read at once.

## Part 2: market probes

Like the RL probes: tiny cases whose outcome is known by hand, each showing one
part of the market step. Not a check of every formula (the tests do that), but a
played-out case where the mechanism is visible.

### Core: `core/market/probes.py`

Decided 26 Oct: **built on the SimBench profiles** (the participants' loads and
generation as the market uses them), and **played on both grid methods** (power
flow and graph), since the thesis compares the two.

- **A probe** = a scenario (3-4 participants on a small SimBench network, chosen
  so the case is obvious: e.g. a PV participant with a surplus at noon, consumers
  with a deficit), a few steps (about 5, e.g. around midday), scripted orders per
  step (`OrderIntent`s, quantities as shares of each participant's eq. 15 bound so
  they follow the profiles), and checks whose expected values are **computed from
  the profiles of those steps** (e.g. "B buys min(A's surplus, B's deficit)"),
  not typed-in numbers.
- **Played with** `LocalEnergyMarket.step(intents)` (the RL agents' path, no bidding
  rule), each step's `StepRecord` kept for display, once with `grid.method =
  "powerflow"` and once with `"graph"`; the checks of the market itself must agree
  between the two, the fee and loading checks show how the two methods differ.
- No core change to the market is needed for this.

Candidate probes (each a few steps, numbers chosen so the answer is obvious):

| # | Shows | Setup | Expected |
|---|---|---|---|
| M1 | Stage 1, mutual preference | A sells 2 kWh naming B, B buys 2 kWh naming A, bid ≥ ask | one stage-1 trade, 2 kWh, at the mechanism's price (e.g. the midpoint) |
| M2 | Stage 1 needs both | A names B, B names nobody | no stage-1 trade; they meet in the double auction |
| M3 | Double auction order and partial fills | 2 sellers, 2 buyers at distinct prices | trades in price order, the right quantities, the clearing price = volume-weighted peer price |
| M4 | The DSO clears the rest | an unmatched buyer and seller | DSO trades at the utility price and FiT |
| M5 | Order bounds (eq. 15) | an order above the surplus + dischargeable energy | cut to the bound, noted |
| M6 | Settlement and the battery | sell beyond the surplus; buy beyond the deficit; trade exactly the net position | discharge / charge / battery untouched; G − D + bought − sold = charge − discharge + external |
| M7 | Grid fees, both methods | one trade across a long path vs a short one; the same trades under the power flow and the graph method | longer path: higher voltage and transmission fee; zone bonus within a feeder; the loading the fees read: the power flow's vs the graph model's from the trades |
| M8 | Reputation over steps | one agent always matched, one never | reputations move apart, by the decay |
| M9 | A day's balance | 5 steps with a battery | the state of charge, profits and untraded energy add up over the steps |

Tests in `tests/market/test_market_probes.py` run every probe and assert its
checks, so the probes are also part of the test suite.

### Studio: Market probes page

Probe list → per probe: its description and expected outcome, the checks table
(PASS/FAIL), and its steps played out with the Step page's existing views (order
book, trades per stage, participants table), read from the kept `StepRecord`s
(no new display logic beyond reusing the Step page's tables).

## Order of work

1. Navigation: a "Validate" group; move Step there (no logic).
2. RL probes page: move the Learning tab, add the probe descriptions and the probe
   run's checks.
3. Market probes core: `core/market/probes.py` with M1-M4 on both grid methods,
   tests.
4. Market probes page.
5. M5-M9, then docs (`docs/rl/probes.md` points to the page; a market probes page
   in the docs).

## Decided (26 Oct 2026)

- Market probes on the SimBench profiles; expected values computed from them.
- Market probes on both grid methods.
- RL probes page: the Learning tab moved here, plus probe descriptions and checks;
  no method selector.
