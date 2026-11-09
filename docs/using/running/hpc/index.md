# TalTech HPC

The TalTech cluster is used in two ways:

| Use | How | Page |
|---|---|---|
| A notebook on a compute node | `hpc start` submits a Jupyter job and opens a tunnel; VS Code runs the cells there | [Notebook sessions](../../../getting-started/notebooks.md) |
| Training experiments | `python -m core.runner ... --target taltech` or the Studio's Runs page: one SLURM job array per experiment | [Starting and following runs](../runs.md) |

Both run the cluster's own checkout of this branch, `~/marlem-v2`, at the commit pushed from this PC
(`git shipc`), in the conda environment of [environment.yml](../../../../environment.yml).
Your own values (account, SSH host, port) are in a git-ignored `.env`
([.env.example](../../../../.env.example)).

- **Once:** [setup](../../../getting-started/hpc-setup.md): access, the environment, the `hpc` helper and the Git aliases.
- **Reference:** [resources and parallelism](resources.md) (what a run gets and
  what the spec controls), [measurements and costs](performance.md),
  [monitoring and troubleshooting](operations.md).
