# MARLEM clean

MARLEM rebuilt step by step on SimBench networks: configure a local energy market,
then step through it by hand and watch the network's power flow. The market and
reinforcement-learning layers now share this repository, with
the RL layer in `core/rl/`. They are validated separately.

| Section | Start with |
|---|---|
| **marlem-v1** | [The working solution](v1.md): the market and the RL layer wired together, what changed, how to train, and the validation results. |
| **Code structure** | [Every folder and script](structure.md): what it does and how far it is built. |
| **MARLEM** | [Methodology](marlem/methodology.md): the market as the paper states it (clearing, pricing, DSO fees, reputation, agents, batteries, grid, one market step), without the reinforcement-learning parts. [Learning layer](marlem/learning.md): observation, action, paradigms, algorithms, hyperparameters, population-based training and the 3 × 3 experiment as the papers state them, with the original code's settings where the papers are silent. |
| **RL** | [Code and running instructions](structure.md#corerl-the-reinforcement-learning-layer). [Training cycle](rl/training.md): the math of one training iteration for PPO, APPO and SAC in each paradigm (CTCE, CTDE, DTDE), and how many steps each takes. [One iteration, step by step](rl/cycle.md): every calculation from the agents' observation to the weight update, with what each paradigm changes. [Worked examples](rl/examples.md): the same cycle with numbers, for the parts our own code defines (what each paradigm's modules receive, CTDE's local actor and central critic, per-agent clipping, settings, evaluation). |
| **Validation** | [Issue register](validation/register.md): every issue in the original MARLEM release and its two papers, one ID each, the list the thesis cites. [Market layer](validation/market.md): everything that was wrong in the original market (code or paper) and what changed. [RL layer](validation/rl.md): what is wrong in the original training paradigms, trainer and inference, and what the tests in `tests/rl/` show. [The two papers](validation/papers.md): where the MARLEM paper and the implicit-cooperation paper agree and differ. |
| **SimBench** | [Overview](simbench/README.md): what SimBench is, its codes, grids, scenarios and study cases. [Network catalogue](simbench/networks.md): every network's size, load, PV and load mix. [Profiles](simbench/profiles.md): the time series of every load and generator class, and where they come from. |
| **HPC** | [Running on the TalTech cluster](hpc.md): Jupyter notebooks on a compute node, training experiments as SLURM jobs, sizing and cost, problems and fixes. |
| **API Reference** | [One page per module](api/index.md), generated from the docstrings, one section per top-level folder. |
| **About these docs** | [How the site is built](about.md): where the source is, how the API pages are made, how to use the diagrams. |
