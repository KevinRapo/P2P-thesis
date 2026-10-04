"""GridCatalogService: networks before any experiment (04 §5).

Final implementation: ``PandapowerGridCatalogService`` over the pandapower adapter
(it translates the adapter's grid-contract records into the API models and never
touches pandapower itself). Demo: ``DemoGridCatalogService`` (a few sample networks
with generated topology).
"""

from __future__ import annotations

import math
import random
from typing import Protocol
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


# ---------------------------------------------------------------------- protocol
class GridCatalogService(Protocol):
    """Networks before any experiment: what exists, what it looks like, one power flow.

    Real implementation: ``PandapowerGridCatalogService`` (SimBench and pandapower).
    """

    def list_networks(
        self, source_type: str | None = None, level: str | None = None
    ) -> list[NetworkInfo]:
        """The networks that can be chosen.

        Args:
            source_type: ``"simbench"``, ``"pandapower_builtin"`` or
                ``"pandapower_file"``; ``None`` for all.
            level: Voltage level filter, e.g. ``"LV"``.
        """
        ...

    def summary(self, source: NetworkSource) -> NetworkSummary:
        """Element counts, total load and generation of one network."""
        ...

    def topology(self, source: NetworkSource) -> TopologyView:
        """Buses with coordinates and branches, as plain data for plotting."""
        ...

    def elements(
        self, source: NetworkSource, bus: str | None = None
    ) -> list[ElementInfo]:
        """Loads, generators and storage, optionally only those on ``bus``."""
        ...

    def preview_powerflow(
        self, source: NetworkSource, day: str, step: int
    ) -> PowerFlowPreview:
        """One AC power flow of the unmodified network at one hour.

        Args:
            source: The network.
            day: Date (``YYYY-MM-DD``) of the profile values to use.
            step: Hour of that day (0–23).
        """
        ...


# ---------------------------------------------------------------------- final implementation
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


class PandapowerGridCatalogService:
    """Real network catalog: SimBench codes and pandapower built-in networks."""

    def list_networks(
        self, source_type: str | None = None, level: str | None = None
    ) -> list[NetworkInfo]:
        """SimBench codes and pandapower built-ins, filtered by source type and voltage
        level.
        """
        return [_info(n) for n in adapter.list_networks(source_type, level)]

    def summary(self, source: NetworkSource) -> NetworkSummary:
        """Totals of one network (loads it on first use)."""
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
        """Buses and branches as plain data; branches are listed under ``lines``."""
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
        """Loads, static generators and storage, optionally only on one bus."""
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
        """One power flow of the unmodified network at ``day`` / hour ``step``."""
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


# ---------------------------------------------------------------------- demo implementation
_NETWORKS = [
    ("simbench", "1-LV-rural1--0-sw", "LV rural 1", "LV", 15, 13, 4, 0, True, True),
    (
        "simbench",
        "1-LV-semiurb4--0-sw",
        "LV semi-urban 4",
        "LV",
        44,
        41,
        12,
        0,
        True,
        True,
    ),
    ("simbench", "1-LV-urban6--0-sw", "LV urban 6", "LV", 59, 111, 10, 0, True, True),
    (
        "simbench",
        "1-MV-rural--1-sw",
        "MV rural, scenario 1",
        "MV",
        99,
        118,
        102,
        0,
        True,
        True,
    ),
    (
        "pandapower_builtin",
        "case33bw",
        "IEEE 33-bus (Baran & Wu)",
        "MV",
        33,
        32,
        0,
        0,
        False,
        False,
    ),
    (
        "pandapower_builtin",
        "cigre_mv",
        "CIGRE MV with DER",
        "MV",
        15,
        18,
        9,
        2,
        False,
        True,
    ),
    ("pandapower_builtin", "cigre_lv", "CIGRE LV", "LV", 44, 15, 0, 0, False, True),
    (
        "pandapower_builtin",
        "mv_oberrhein",
        "MV Oberrhein",
        "MV",
        179,
        147,
        153,
        0,
        False,
        True,
    ),
]


class DemoGridCatalogService:
    """Demo ``GridCatalogService``: a few sample networks with generated topology. Shown
    as DEMO DATA in the Studio.
    """

    def list_networks(
        self, source_type: str | None = None, level: str | None = None
    ) -> list[NetworkInfo]:
        """Sample-data version of ``GridCatalogService.list_networks``."""
        out = []
        for (
            t,
            code,
            label,
            lvl,
            buses,
            loads,
            sgens,
            storage,
            profiles,
            ratings,
        ) in _NETWORKS:
            if (source_type and t != source_type) or (level and lvl != level):
                continue
            out.append(
                NetworkInfo(
                    source=NetworkSource(type=t, code=code),
                    label=label,
                    voltage_level=lvl,
                    buses=buses,
                    loads=loads,
                    sgens=sgens,
                    storage=storage,
                    has_profiles=profiles,
                    has_line_ratings=ratings,
                    has_geodata=True,
                )
            )
        return out

    def _info(self, source: NetworkSource) -> NetworkInfo:
        return next(
            (n for n in self.list_networks() if n.source.code == source.code),
            self.list_networks()[1],
        )

    def summary(self, source: NetworkSource) -> NetworkSummary:
        """Sample-data version of ``GridCatalogService.summary``."""
        info = self._info(source)
        return NetworkSummary(
            info=info,
            total_load_kw=round(info.loads * 7.5, 1),
            total_generation_kw=round(info.sgens * 9.0, 1),
            lines=info.buses - 1,
            transformers=1,
        )

    def topology(self, source: NetworkSource) -> TopologyView:
        """A deterministic radial feeder layout sized like the selected network."""
        n = min(self._info(source).buses, 60)
        rng = random.Random(n)
        buses = [{"id": "Bus 0", "x": 0.0, "y": 0.0, "kind": "external_grid"}]
        lines, feeders = [], 4
        for i in range(1, n):
            feeder = (i - 1) % feeders
            depth = (i - 1) // feeders + 1
            angle = (feeder - (feeders - 1) / 2) * 0.55 + rng.uniform(-0.08, 0.08)
            buses.append(
                {
                    "id": f"Bus {i}",
                    "x": depth * math.cos(angle),
                    "y": depth * math.sin(angle) * 2.2,
                    "kind": "load" if i % 3 else "load+pv",
                }
            )
            parent = 0 if depth == 1 else i - feeders
            lines.append({"id": f"Line {i}", "from": f"Bus {parent}", "to": f"Bus {i}"})
        return TopologyView(buses=buses, lines=lines, external_grid_bus="Bus 0")

    def elements(
        self, source: NetworkSource, bus: str | None = None
    ) -> list[ElementInfo]:
        """Sample-data version of ``GridCatalogService.elements``."""
        topo = self.topology(source)
        out = []
        for i, b in enumerate(topo.buses[1:], start=1):
            out.append(
                ElementInfo(
                    id=f"Load {i}",
                    element_type="load",
                    bus=b["id"],
                    profile_type=["H0-A", "H0-B", "G1-A", "L0-A"][i % 4],
                    rated_kw=round(4 + (i % 7) * 1.5, 1),
                )
            )
            if b["kind"] == "load+pv":
                out.append(
                    ElementInfo(
                        id=f"PV {i}",
                        element_type="sgen",
                        bus=b["id"],
                        profile_type=f"PV{1 + i % 8}",
                        rated_kw=round(5 + (i % 5) * 2.0, 1),
                    )
                )
        return [e for e in out if bus is None or e.bus == bus]

    def preview_powerflow(
        self, source: NetworkSource, day: str, step: int
    ) -> PowerFlowPreview:
        """Sample-data version of ``GridCatalogService.preview_powerflow``."""
        topo = self.topology(source)
        load = 0.6 + 0.4 * math.sin(math.pi * step / 24)
        volts = {
            b["id"]: round(1.02 - 0.012 * math.hypot(b["x"], b["y"]) * load, 4)
            for b in topo.buses
        }
        vmin = min(volts.values())
        return PowerFlowPreview(
            converged=True,
            min_voltage_pu=vmin,
            max_voltage_pu=max(volts.values()),
            max_line_loading_percent=round(55 + 40 * load, 1),
            losses_kw=round(12 * load, 2),
            bus_voltage_pu=volts,
            violations=[f"V_LOW at {k}" for k, v in volts.items() if v < 0.95][:5],
        )
