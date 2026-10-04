"""The experiment layer: experiment files, runs, the store and worker processes.

See docs_thesis/thesis/architecture/03-experiment-layer.md. Four parts, as in the
layer diagram (architecture README §2.1):

- ``models``: the experiment file and run records, plus reading, hashing,
  expanding and resolving files and building run manifests;
- ``factory``: the only place that turns a file into live MARLEM objects
  (environment, grid) and RLlib configuration;
- ``store``: run folders on disk and the per-episode step recorder;
- ``worker``: what runs (runners), the worker process and the pool that starts
  and watches workers.

Nothing here imports the application layer or the Studio; MARLEM, pandapower
and Ray are only imported inside the functions that need them.
"""
