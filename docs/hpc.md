# TalTech HPC

Use the **HPC sidebar** to open a separate document for each topic:

- **Getting started:** setup, access and the Windows helper scripts.
- **Running work:** notebook sessions or unattended training experiments.
- **Reference:** resources and parallelism, measurements and cost estimates,
  monitoring and troubleshooting.

Notebook sessions use `hpc start` and `hpc stop`. Training experiments use
`python -m core.runner` or the Studio's Runs page; they do not need a Jupyter job.

The active code and documentation are in `marlem-v1`, and the cluster checkout
is `~/marlem-v1`.
