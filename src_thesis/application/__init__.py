"""Application services shared by the Studio, the CLI and notebooks.

Callers use ``container.build_services()`` and the protocols in
``contracts``; they never import MARLEM runtime, grid adapters, pandapower or
Ray directly.

Nothing is re-exported here: import from the module that defines a name
(e.g. ``from src_thesis.application.container import build_services``), so every import names its file.
"""
