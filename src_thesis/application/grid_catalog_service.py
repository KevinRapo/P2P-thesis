"""GridCatalogService: networks before any experiment (04 §5).

Backed by the pandapower adapter: the service translates between the API models
the Studio and the CLI use (``application.models``) and the plain grid-contract
records the adapter returns (``marketplace.grid.contract_new``). It never touches
pandapower itself.
"""

from __future__ import annotations

import threading
from pathlib import Path

import src_thesis.marketplace.grid.contract_new as contract
from src_thesis.adapters.grid import simbench_new as adapter
from src_thesis.application.models import (
    ElementInfo,
    NetworkInfo,
    NetworkSource,
    NetworkSummary,
    PowerFlowPreview,
    TopologyView,
)


def _ref(source: NetworkSource) -> contract.NetworkRef:
    return contract.NetworkRef(source.type, source.code)


def _info(info: contract.NetworkInfo) -> NetworkInfo:
    return NetworkInfo(
        source=NetworkSource(type=info.ref.source_type, code=info.ref.code),
        label=info.label,
        voltage_level=info.voltage_level,
        buses=info.buses,
        loads=info.loads,
        sgens=info.sgens,
        storage=info.storage,
        has_profiles=info.has_profiles,
        has_line_ratings=info.has_line_ratings,
        has_geodata=info.has_geodata,
    )


def _violation_text(v: contract.GridViolation) -> str:
    where = f" at {v.element_type} {v.element_id}" if v.element_id else ""
    if v.observed is None:
        return f"{v.code}{where}"
    return f"{v.code}{where}: {v.observed:.3f} (limit {v.limit})"


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

    # ------------------------------------------------------------------ cache
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

    def clear_cache(self) -> None:
        """Delete the cached networks; they are built again when opened."""
        adapter.clear_cache()

    def is_cached(self, source: NetworkSource) -> bool:
        """Whether a network opens at once (in RAM or in the disk cache)."""
        return adapter.is_cached(_ref(source))

    # ------------------------------------------------------------------ catalog

    def list_networks(
        self, source_type: str | None = None, level: str | None = None
    ) -> list[NetworkInfo]:
        """The networks that can be chosen.

        Args:
            source_type: ``"simbench"``, ``"pandapower_builtin"`` or
                ``"pandapower_file"``; ``None`` for all.
            level: Voltage level filter, e.g. ``"LV"``.
        """
        return [_info(n) for n in adapter.list_networks(source_type, level)]

    def summary(self, source: NetworkSource) -> NetworkSummary:
        """Element counts, total load and generation of one network."""
        s = adapter.summary(_ref(source))
        return NetworkSummary(
            info=_info(s.info),
            total_load_kw=s.total_load_kw,
            total_generation_kw=s.total_generation_kw,
            lines=s.lines,
            transformers=s.transformers,
            profile_year=s.profile_year,
        )

    def topology(self, source: NetworkSource) -> TopologyView:
        """Buses with coordinates and branches, as plain data for plotting."""
        t = adapter.topology_view(_ref(source))
        return TopologyView(
            buses=[
                {"id": b.id, "x": b.x, "y": b.y, "kind": b.kind, "vn_kv": b.vn_kv}
                for b in t.buses
            ],
            lines=[
                {
                    "id": br.id,
                    "from": br.from_bus,
                    "to": br.to_bus,
                    "kind": br.kind,
                    "closed": br.closed,
                }
                for br in t.branches
            ],
            external_grid_bus=t.external_grid_bus,
            coordinates=t.coordinates,
        )

    def elements(
        self, source: NetworkSource, bus: str | None = None
    ) -> list[ElementInfo]:
        """Loads, generators and storage, optionally only those on ``bus``."""
        return [
            ElementInfo(
                id=e.id,
                element_type=e.element_type,
                bus=e.bus,
                profile_type=e.profile_type,
                rated_kw=e.rated_kw,
            )
            for e in adapter.elements(_ref(source), bus)
        ]

    def preview_powerflow(
        self, source: NetworkSource, day: str, step: int
    ) -> PowerFlowPreview:
        """One AC power flow of the unmodified network at one hour.

        Args:
            source: The network.
            day: Date (``YYYY-MM-DD``) of the profile values to use.
            step: Hour of that day (0–23).
        """
        a = adapter.preview_powerflow(_ref(source), day, step)
        return PowerFlowPreview(
            converged=a.converged,
            min_voltage_pu=a.min_voltage_pu,
            max_voltage_pu=a.max_voltage_pu,
            max_line_loading_percent=a.max_line_loading_percent,
            # One hour at constant power, so kWh over the hour equals mean kW.
            losses_kw=a.losses_kwh,
            bus_voltage_pu=dict(a.bus_voltage_pu),
            violations=[_violation_text(v) for v in a.violations],
            max_trafo_loading_percent=a.max_trafo_loading_percent,
            external_grid_kw=a.external_grid_kwh,
            notes=list(a.notes),
        )
