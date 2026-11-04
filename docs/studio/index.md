# The Studio

> The NiceGUI interface to the whole workflow: build a scenario, check the market and
> the learner, start runs, and read their results. Every page reads and writes the same
> files as the CLI and the notebooks, so nothing exists only in the Studio.

Start it from a checkout, in the `marlem` environment, and open
http://127.0.0.1:8091:

```
python run_studio.py
```

## The pages

The left navigation groups the pages by what they are for
([`navigation.py`](../../studio/navigation.py)).

| Group | Page | What it answers | Explained in |
|---|---|---|---|
| Build | Inspect | What do the SimBench networks, profiles and price files look like? Read only | |
| Build | Scenario | Which network, day, participants, market and DSO settings? Writes the scenario | [Config](../config/reference.md) |
| Build | Experiments | What will a training experiment run, and is it valid? | [Training experiments](../hpc/experiments.md) |
| Build | Summary | The scenario and the experiment in one look, before they run | |
| Validate | Market | Does one market step do what the equations say? Step through it, or play scripted probes | [Market step](../full-cycle/market-step.md) |
| Validate | RL probes | Does the learner solve problems with a known answer? | [The probes](../full-cycle/learning/probes.md) |
| Experiments | Runs | What is running, here and on the cluster? Start, stop, sync | [Training experiments](../hpc/experiments.md) |
| Experiments | **Results** | Did it learn, how good is it, what did the market and the grid do? | [Results](results/index.md) |

The rules for the Studio's code (the core first, the page only draws what the core
computes) are in [AGENTS.md](https://github.com/KevinRapo/P2P-thesis/blob/marlem-v2/AGENTS.md).

## From a run to the Results page

```text
runs/<experiment>/<run>/          saved by the run: settings and tables      (level 1)
        │
        ▼
core/runner/results.py            reads them, cached by file time and size
core/runner/indicators.py         one number per run, policy and test day    (level 2)
core/runner/ceiling.py            the references: ceiling and non-P2P
        │
        ▼
studio/adapters/results_service   the runs of the ticked rows
studio/pages/results/             one file per tab: Learning, Validation,
                                  Market, Grid                               (level 3)
```

Only level 1 is recorded. Everything after it is computed when it is read, so a new
indicator applies to every run already made, as long as the saved tables hold what it
needs. The [Results](results/index.md) section explains each level, every metric, and
every panel of the four tabs.
