"""ResultsService: what the Results page reads about runs.

A thin wrapper over ``core/runner/results.py``: the runs of this PC and of each
cluster's mirror (filled by Sync results on the Runs page, or kept up to date by
the Results page's live view), found once and kept until ``refresh``, and the
reader's tables for the runs the page names by their key
(``target/experiment/run``). The tables are returned as the reader makes them; a
file is read again only when it has changed. Every method reads files, so the page
calls them through ``run.io_bound``.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import pandas as pd

from core.runner import results
from core.runner.results import LEARNER_GROUPS, RunResult


class ResultsService:
    """The finished runs and their results.

    Args:
        where: Where to read runs from, ``{target: folder}``; default
            ``results.sources()`` (this PC's runs root and the clusters' mirrors).
    """

    def __init__(self, where: Optional[dict[str, Path]] = None) -> None:
        self._where = where
        self._runs: Optional[dict[str, RunResult]] = None
        self._lock = threading.Lock()

    # --- The runs --------------------------------------------------------------------
    def refresh(self, experiments: Optional[list[tuple[str, str]]] = None) -> None:
        """Read the run folders again: all on the next call (new runs, a new sync),
        or now only those of ``experiments`` (``(target, experiment)`` pairs: what a
        live refresh followed), keeping every other run as it was read."""
        with self._lock:
            if experiments is None or self._runs is None:
                self._runs = None
                return

            wanted = set(experiments)
            fresh = results.load_runs(results.find_runs(self._where, list(wanted)))
            kept = {
                key: r
                for key, r in self._runs.items()
                if (r.ref.target, r.ref.experiment) not in wanted
            }
            order = {target: i for i, target in enumerate(self._sources())}
            merged = kept | {r.key: r for r in fresh}
            self._runs = dict(
                sorted(
                    merged.items(),
                    key=lambda item: (
                        order.get(item[1].ref.target, len(order)),
                        item[1].ref.experiment,
                        item[1].ref.run,
                    ),
                )
            )

    def _sources(self) -> dict[str, Path]:
        return self._where or results.sources()

    def _all(self) -> dict[str, RunResult]:
        with self._lock:
            if self._runs is None:
                refs = results.find_runs(self._where)
                self._runs = {r.key: r for r in results.load_runs(refs)}
            return self._runs

    def results(self, keys: Optional[list[str]] = None) -> list[RunResult]:
        """The runs named by ``keys`` (all without), in the order given."""
        found = self._all()
        return list(found.values()) if keys is None else [found[k] for k in keys]

    def overview(self) -> pd.DataFrame:
        """One row per run (``results.overview``)."""
        return results.overview(self.results())

    # --- Comparing runs --------------------------------------------------------------
    def learning_curves(self, keys: list[str]) -> pd.DataFrame:
        return results.learning_curves(self.results(keys))

    def training_curves(self, keys: list[str]) -> pd.DataFrame:
        return results.training_curves(self.results(keys))

    def learner_metrics(self, keys: list[str]) -> pd.DataFrame:
        return results.learner_metrics(self.results(keys))

    def iteration_timing(self, keys: list[str]) -> pd.DataFrame:
        return results.iteration_timing(self.results(keys))

    def run_timings(self, keys: list[str]) -> pd.DataFrame:
        return results.run_timings(self.results(keys))

    # The learner's metric groups, as the reader defines them (title, metrics, note).
    learner_groups = LEARNER_GROUPS

    def day_indicators(self, keys: list[str]) -> pd.DataFrame:
        return results.day_indicators(self.results(keys))

    def participant_metrics(self, keys: list[str]) -> pd.DataFrame:
        return results.participant_metrics(self.results(keys))

    def participant_gains(self, keys: list[str]) -> pd.DataFrame:
        return results.participant_gains(self.results(keys))

    def differing_settings(self, keys: list[str]) -> list[str]:
        return results.differing_settings([r.settings for r in self.results(keys)])

    # --- One run ---------------------------------------------------------------------
    def result(self, key: str) -> RunResult:
        return self._all()[key]

    def participant_days(self, key: str, value: str = "return") -> pd.DataFrame:
        return results.participant_days(self.result(key), value)

    def participant_groups(self, key: str) -> dict[str, str]:
        return results.participant_groups(self.result(key))

    def trade_table(self, keys: list[str]) -> pd.DataFrame:
        return results.trade_table(self.results(keys))

    def network(self, key: str) -> tuple[Optional[str], dict[str, str]]:
        """The run's grid code and its participants' buses, from its saved scenario
        (None and empty when it saved only the file's name)."""
        scenario = self.result(key).settings["scenario"]

        if not isinstance(scenario, dict):
            return None, {}

        buses = {p["id"]: p["bus"] for p in scenario.get("participants", [])}

        return scenario.get("grid", {}).get("code"), buses

    def voltage_limits(self, key: str) -> tuple[float, ...]:
        """The run's lowest and highest allowed bus voltage (pu), from its saved
        scenario; empty when it saved only the file's name."""
        scenario = self.result(key).settings["scenario"]

        if not isinstance(scenario, dict):
            return ()

        grid = scenario.get("grid", {})

        return tuple(grid[k] for k in ("v_min_pu", "v_max_pu") if k in grid)

    def table(self, key: str, name: str) -> Optional[pd.DataFrame]:
        """One of the run's tables (``RunResult.table``), e.g. ``heldout_episodes``
        or ``heldout_steps``."""
        return self.result(key).table(name)
