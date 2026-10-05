"""The only place that turns an experiment file into live MARLEM objects.

Why: in the original, the environment was assembled inside ``marl/train.py`` and the
notebooks, each with its own hard-coded values. Here there is exactly one function that
builds an environment from a file, used by the worker, the dry run, notebooks, tests and
every RLlib env runner. So whatever runs is exactly what the file says, and the same
file always gives the same environment.

Everyone builds environments here: the
worker, validation dry runs, notebooks and tests. RLlib env runners call the
factory inside each runner; only the resolved file travels in ``env_config``,
never a network or agents.

Status: interface only. The bodies depend on the rebuilt environment in
``src_thesis`` (R1) and the step-time grid model (R4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src_thesis.platform.experiments.models.records import ExperimentFile, RunCell

if TYPE_CHECKING:  # heavy imports stay out of this module at runtime
    from src_thesis.marlem.grid.contract import GridModel

ENV_CONFIG_KEY = "marlem_resolved_file"


def build_env_config(
    resolved: ExperimentFile, cell: RunCell, episode_seed: int | None = None
) -> dict[str, Any]:
    """The ``env_config`` handed to RLlib: plain data only.

    Contains the resolved file (as a dict), the cell and the episode seed, so
    every env runner can call :func:`build_env` on its own copy.
    """
    return {
        ENV_CONFIG_KEY: resolved.to_data(),
        "cell": cell.model_dump(mode="json"),
        "episode_seed": episode_seed,
    }


def build_env(env_config: dict[str, Any]) -> Any:
    """Build one ``LocalEnergyMarket`` from an ``env_config``.

    Steps (03 §4):
    1. take this episode's day from the resolved train (or eval) day list;
    2. build profiles through the selected profile sources (01 §3);
    3. build agents (with batteries), DSO tariffs and fees, and ``MarketConfig``;
    4. build the grid model from ``grid.source`` and the participant mapping;
    5. set observation, reward, reputation and the assessment mode from
       ``environment``.
    """
    raise NotImplementedError(
        "build_env needs the rebuilt LocalEnergyMarket (R1) and SimBenchGrid (R4)"
    )


def build_grid(resolved: ExperimentFile) -> "GridModel":
    """The step-time ``GridModel`` for ``grid.source`` (01 §5); one per env."""
    raise NotImplementedError("SimBenchGrid is implemented in phase R4")
