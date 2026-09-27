"""GridCatalogService backed by the pandapower adapter (04-services.md §2.2).

The service translates between the API models the Studio and CLI use
(``application.models``) and the plain grid contract the adapter returns
(``marketplace.grid.contract_new``). It never touches pandapower itself.
"""

import src_thesis_reference.marketplace.grid.contract_new as contract
from src_thesis_reference.adapters.grid import simbench_new as adapter

from .models import (
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


class PandapowerGridCatalogService:
    """Real network catalog: SimBench codes and pandapower built-in networks."""

    def list_networks(
        self, source_type: str | None = None, level: str | None = None
    ) -> list[NetworkInfo]:
        return [_info(n) for n in adapter.list_networks(source_type, level)]

    def summary(self, source: NetworkSource) -> NetworkSummary:
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
