# TalTech HPC

The TalTech cluster is used in two ways:

| Use | How | Page |
|---|---|---|
| A notebook on a compute node | `hpc start` submits a Jupyter job and opens a tunnel; VS Code runs the cells there | [Notebook sessions](hpc/notebooks.md) |
| Training experiments | `python -m core.runner ... --target taltech` or the Studio's Runs page: one SLURM job array per experiment | [Training experiments](hpc/experiments.md) |

Both run the cluster's own checkout, `~/marlem-v1`, at the commit pushed from this
PC (`git shipc`), in the conda environment of [environment.yml](../environment.yml).

- **Once:** [setup](hpc/setup.md): access, the environment, the `hpc` helper and the Git aliases.
- **Reference:** [resources and parallelism](hpc/resources.md) (what a run gets and
  what the spec controls), [measurements and costs](hpc/performance.md),
  [monitoring and troubleshooting](hpc/operations.md).
