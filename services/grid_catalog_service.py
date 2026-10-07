"""GridCatalogService: the networks, their facts, topology and cache.

Backed by the pandapower adapter (``grid/simbench.py``). It returns the adapter's
plain contract records (``grid/contract.py``) as they are, and adds the network
cache and its background warming for the Studio. It never touches pandapower itself.
"""

from __future__ import annotations

import threading
from pathlib import Path

from grid import simbench as adapter
from grid.contract import (
    ElementRecord,
    GridAssessment,
    NetworkInfo,
    NetworkRef,
    NetworkSummary,
    TopologyView,
)


# --------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------
class GridCatalogService:
    """Networks before any experiment: what exists, what it looks like, one power flow.

    Real network catalog: SimBench codes and pandapower built-in networks.
    """

    SAMPLE_DATA = False

    def __init__(self, cache: Path | None = None) -> None:
        """Args:
        cache: Folder for built networks (``Workspace.network_cache``); ``None``
            keeps them in RAM only.
        """
        adapter.use_cache(cache)
        self.warming: dict = {"levels": [], "done": 0, "total": 0, "running": False}

    # --- Network cache ----------------------------------------------------------------
    def cache_status(self) -> dict:
        """The network cache: folder, networks cached, size, and the background
        preparation (levels, done, total, running).
        """
        folder, count, size = adapter.cache_status()
        return {"folder": folder, "networks": count, "bytes": size, **self.warming}

    def warm_cache(self, levels: list[str]) -> None:
        """Prepare every network of ``levels`` in a background thread, so they open
        at once later; networks already cached are skipped.
        """
        if self.warming["running"]:
            return
        self.warming.update(levels=list(levels), done=0, total=0, running=True)

        def progress(done: int, total: int) -> None:
            self.warming.update(done=done, total=total)

        def work() -> None:
            try:
                adapter.warm_cache(levels, progress)
            finally:
                self.warming["running"] = False

        threading.Thread(target=work, name="network-cache", daemon=True).start()

    def cache_coverage(self) -> list[dict]:
        """How much of the catalogue is cached, per voltage level and for the
        built-in networks: ``group``, ``cached``, ``total``.
        """
        return [
            {"group": group, "cached": cached, "total": total}
            for group, (cached, total) in adapter.cache_coverage().items()
        ]

    def clear_cache(self) -> None:
        """Delete the cached networks; they are built again when opened."""
        adapter.clear_cache()

    def is_cached(self, source: NetworkRef) -> bool:
        """Whether a network opens at once (in RAM or in the disk cache)."""
        return adapter.is_cached(source)

    # --- Catalog ----------------------------------------------------------------------
    def list_networks(
        self, source_type: str | None = None, level: str | None = None
    ) -> list[NetworkInfo]:
        """The networks that can be chosen.

        Args:
            source_type: ``"simbench"``, ``"pandapower_builtin"`` or
                ``"pandapower_file"``; ``None`` for all.
            level: Voltage level filter, e.g. ``"LV"``.
        """
        return adapter.list_networks(source_type, level)

    def summary(self, source: NetworkRef) -> NetworkSummary:
        """Element counts, total load and generation of one network."""
        return adapter.summary(source)

    def topology(self, source: NetworkRef) -> TopologyView:
        """Buses with coordinates and branches, as plain data for plotting."""
        return adapter.topology_view(source)

    def elements(
        self, source: NetworkRef, bus: str | None = None
    ) -> list[ElementRecord]:
        """Loads, generators and storage, optionally only those on ``bus``."""
        return adapter.elements(source, bus)

    # --- Power flow -------------------------------------------------------------------
    def preview_powerflow(
        self, source: NetworkRef, day: str, step: int
    ) -> GridAssessment:
        """One AC power flow of the unmodified network at one hour.

        Args:
            source: The network.
            day: Date (``YYYY-MM-DD``) of the profile values to use.
            step: Hour of that day (0-23).
        """
        return adapter.preview_powerflow(source, day, step)
