"""Application services shared by the Studio, the CLI and notebooks.

Callers use `build_services()` and the protocols in `contracts`; they never
import MARLEM runtime, grid adapters, pandapower or Ray directly.
"""

from .container import Services, build_services

__all__ = ["Services", "build_services"]
