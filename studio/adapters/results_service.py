"""ResultsService: what the Results page reads about finished runs.

A thin wrapper over ``core/runner/results.py``: the runs of this PC and of each
cluster's mirror (filled by Sync results on the Runs page), read once and kept until
``refresh``, and the reader's tables for the runs the page names by their key
(``target/experiment/run``). The tables are returned as the reader makes them. Every
method reads files, so the page calls them through ``run.io_bound``.
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
    def refresh(self) -> None:
        """Read the run folders again on the next call (new runs, a new sync)."""
        with self._lock:
            self._runs = None

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

    # The learner's metric groups, as the reader defines them (title, metrics, note).
    learner_groups = LEARNER_GROUPS

    def heldout_days(self, keys: list[str]) -> pd.DataFrame:
        return results.heldout_days(self.results(keys))

    def seed_groups(self, keys: list[str]) -> pd.DataFrame:
        return results.seed_groups(self.results(keys))

    def differing_settings(self, keys: list[str]) -> list[str]:
        return results.differing_settings([r.settings for r in self.results(keys)])

    # --- One run ---------------------------------------------------------------------
    def result(self, key: str) -> RunResult:
        return self._all()[key]

    def participant_days(self, key: str, value: str = "return") -> pd.DataFrame:
        return results.participant_days(self.result(key), value)

    def table(self, key: str, name: str) -> Optional[pd.DataFrame]:
        """One of the run's tables (``RunResult.table``), e.g. ``heldout_episodes``
        or ``heldout_trace_steps``."""
        return self.result(key).table(name)
