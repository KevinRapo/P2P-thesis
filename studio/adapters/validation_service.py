"""ValidationService: what the Validate pages read.

A thin wrapper over two parts of the core:

- the market probes (``core/market/probes.py``), played on both grid methods once
  and kept until played again (about 10 s, most of it the first power flow);
- the RL probes' runs: for the runs of ``ResultsService``, which probe each is and
  what it scored (``core/runner/probe_runs.py``, which does not load Ray).

The pages call it through ``run.io_bound``.
"""

from __future__ import annotations

import threading
from typing import Optional

import pandas as pd

from core.market import probes
from core.market.probes import Check, ProbeRun
from core.runner.probe_runs import ProbeRunInfo, read_probe_run
from studio.adapters.results_service import ResultsService


class ValidationService:
    """The market probes' runs, and the RL probe runs among the finished runs.

    Args:
        results: The finished runs (the Results service).
    """

    def __init__(self, results: ResultsService) -> None:
        self.results = results
        self._runs: Optional[list[ProbeRun]] = None
        self._lock = threading.Lock()

    # --- Market probes ---------------------------------------------------------------
    def market_probes(self, again: bool = False) -> list[ProbeRun]:
        """Every market probe on every grid method; played on the first call, or
        with ``again``."""
        with self._lock:
            if self._runs is None or again:
                self._runs = probes.play_all()
            return self._runs

    @property
    def played(self) -> bool:
        return self._runs is not None

    def same_market(self, key: str) -> list[Check]:
        """Probe ``key``'s market outcome on the power flow against the graph
        method (``probes.same_market``)."""
        found = {r.method: r for r in self.market_probes() if r.probe.key == key}
        return probes.same_market(found["powerflow"], found["graph"])

    # --- RL probes -------------------------------------------------------------------
    def probe_runs(self, keys: list[str]) -> dict[str, ProbeRunInfo]:
        """The probe runs among the runs ``keys``, by key (``read_probe_run``)."""
        found = {
            r.key: read_probe_run(r.ref.folder) for r in self.results.results(keys)
        }
        return {k: info for k, info in found.items() if info is not None}

    def rl_overview(self) -> pd.DataFrame:
        """The Results overview with each probe run's ``probe`` and ``result``
        (empty for other runs)."""
        table = self.results.overview()

        if table.empty:
            return table

        found = self.probe_runs(list(table.key))
        table = table.copy()
        table["probe"] = [found[k].probe if k in found else "" for k in table.key]
        table["result"] = [
            (found[k].result or "not scored") if k in found else "" for k in table.key
        ]

        return table
