# Validation: how this implementation is checked

> The market and the learning layer are checked **separately, before they are
> joined**, each on cases whose right answer is known in advance. This page lists
> every check, what it shows and where it is. The issues found in the *original*
> MARLEM are a different list: the [issue register](../validation/register.md).

## The market

Three levels, each catching what the one before cannot. No learning is involved:
the participants bid by fixed rules.

| Level | What it checks | Where |
|---|---|---|
| 1. Formulas | Every equation of the market step on numbers small enough to work out by hand | [market_1_formulas.ipynb](../../notebooks/market/market_1_formulas.ipynb) |
| 2. One step | The wiring: each phase of a real step gets the right inputs from the one before | [market_2_step.ipynb](../../notebooks/market/market_2_step.ipynb), the Studio's Validate → Market → Step |
| 3. Whole days | The 14 test days played through, every step against rules that must always hold: energy and money balance, battery limits, state carried from step to step | [market_3_days.ipynb](../../notebooks/market/market_3_days.ipynb) |
| Probes | Scripted cases with a known outcome (M1–M4), under both grid methods | [probes.py](../../core/market/probes.py), [test_market_probes.py](../../tests/market/test_market_probes.py), Validate → Market → Probes |

Three notebooks set the references the results are read against:

| Notebook | What it gives |
|---|---|
| [grid_methods.ipynb](../../notebooks/market/grid_methods.ipynb) | The two grid methods on the same scenario before any learning. Every difference is the method alone |
| [market_ceiling.ipynb](../../notebooks/market/market_ceiling.ipynb) | The most money the community could make on the test days: the ceiling of the [VTI](../studio/results/metrics.md) |
| [simbench_study_cases.ipynb](../../notebooks/market/simbench_study_cases.ipynb) | How heavily the profiles and SimBench's study cases load each network |

## The learning layer

PPO is checked on **probe environments**: tiny tasks with an exact answer, each
adding one piece of the learning problem. They cover:
- a constant reward;
- an observation;
- discounting;
- an action;
- the paradigms' structure;
- the mixed action;
- small market cases.

The first probe that a paradigm fails names the broken piece.

| What | Where |
|---|---|
| The probes, their expected answers and the results | [How the probes work](../full-cycle/learning/probes.md) |
| The environments | [core/rl/envs/probes.py](../../core/rl/envs/probes.py) |
| The tests, one file per probe | [tests/rl/](../../tests/rl/) |
| All paradigms at once, with plots | [probe_paradigms.ipynb](../../notebooks/rl/probe_paradigms.ipynb), the Studio's Validate → RL probes |

## The tests

| Folder | Covers | Time |
|---|---|---|
| [tests/market/](../../tests/market/) | Market, grid methods, power flow, fees, battery, signals, the environment, and that the Studio shows what the core computes | minutes |
| [tests/rl/](../../tests/rl/) | The probes, the action heads, evaluation tables, training metrics | longer: trains small policies |
| [tests/runner/](../../tests/runner/) | Specs, targets, SLURM, results, indicators, the ceiling | seconds |
| [tests/studio/](../../tests/studio/) | Charts and pages, driven by a simulated user | seconds |

Run one folder at a time from the repository root, for example `pytest tests/market`.
