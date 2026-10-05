"""The services the Studio, CLI and notebooks call: the only door to the code.

Callers use ``container.build_services()``. Each service is one class in its own
module (``config_service``, ``grid_catalog_service``, ``profile_service``,
``validation_service``, ``experiment_service``, ``result_service``); a service
that is not built yet returns sample data from the same class. Callers never import MARLEM runtime, grid adapters, pandapower or
Ray directly.

Nothing is re-exported here: import from the module that defines a name
(e.g. ``from src_thesis.platform.services.container import build_services``), so every
import names its file.
"""
