# MARLEM v2

A tool for studying **local energy markets with multi-agent reinforcement
learning** on real low-voltage networks.

- Households with loads, PV and batteries trade energy with each other and with the
  distribution system operator (DSO), one hour at a time.
- The DSO charges grid fees from the network's state, computed by an AC power flow
  on a [SimBench](simbench/README.md) network or by the paper's graph model.
- The agents learn their orders with PPO, in three paradigms: centralised (CTCE),
  centralised training with decentralised execution (CTDE), and independent (DTDE).

The tool reconstructs and extends **MARLEM** (Salazar-Peña et al.). The market and
the learning method are theirs. This version:
- checks every part of the market and the learning layer, against the papers and on
  cases with known answers;
- corrects the defects found in the published code;
- states every modelling choice the papers leave open;
- adds the SimBench networks with a power flow;
- adds the Studio, an interface for the whole workflow, and a runner for local and
  cluster experiments.

## Start here

| You want to… | Go to |
|---|---|
| Install it and run it once | [Getting started](getting-started/index.md), then [First steps](getting-started/first-steps.md) |
| Understand what the model computes | [Methodology](overview.md): the market step, tariffs, environment and learning |
| Know what the original MARLEM states, and what was wrong with its release | [Original MARLEM](marlem/methodology.md) and its [issue register](validation/register.md) |
| Find or change code | [Implementation](structure.md): the code structure and the full cycle |
| Trust a result | [Validation](checks/index.md): every check on the market and the learner |
| Configure and run experiments, here or on the cluster | [Using it](studio/index.md) |
| Look up a term | [Glossary](getting-started/glossary.md) |

The **Workspace** tab holds plans and open items of the work in progress; it is
removed when the work is finished.

The pages are built locally, not published ([About](about.md)).
