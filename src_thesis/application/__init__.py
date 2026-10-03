"""Application services shared by the Studio, the CLI and notebooks.

Callers use `build_services()` and the protocols in `contracts`; they never
import MARLEM runtime, grid adapters, pandapower or Ray directly.
"""

from src_thesis.env import load_env

load_env()  # MARLEM_HOME and the other settings from .env, for every caller

from .container import Services, build_services  # noqa: E402

__all__ = ["Services", "build_services"]
