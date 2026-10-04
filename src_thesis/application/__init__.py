"""Application services shared by the Studio, the CLI and notebooks.

Callers use ``container.build_services()``. Each service has one module
(``config_service``, ``grid_catalog_service``, ``profile_service``,
``validation_service``, ``experiment_service``, ``result_service``) holding its
protocol, its final implementation and its demo implementation. Callers never import MARLEM runtime, grid adapters, pandapower or
Ray directly.

Nothing is re-exported here: import from the module that defines a name
(e.g. ``from src_thesis.application.container import build_services``), so every
import names its file.
"""
